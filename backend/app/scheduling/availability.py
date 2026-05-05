"""Availability queries for the scheduling engine.

Returns per-provider free intervals and station occupancy for a given date.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import AppointmentItem, AppointmentItemStatus
from app.models.provider import Provider
from app.models.provider_service_price import ProviderServicePrice
from app.models.schedule import (
    ProviderSchedule,
    ProviderScheduleException,
    TenantOperatingHours,
)
from app.models.scheduling import TenantStation
from app.models.service import Service
from app.models.tenant import Tenant
from app.models.time_block import TimeBlock
from app.scheduling.types import (
    FreeInterval,
    ServiceCapability,
    StationOccupancy,
)

_SLOT = 10  # granularity in minutes


def _time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _subtract_busy(
    free: list[FreeInterval],
    busy_start: int,
    busy_end: int,
) -> list[FreeInterval]:
    """Remove a busy span from a list of free intervals."""
    result: list[FreeInterval] = []
    for iv in free:
        if busy_end <= iv.start_minutes or busy_start >= iv.end_minutes:
            result.append(iv)
        else:
            if iv.start_minutes < busy_start:
                result.append(FreeInterval(iv.start_minutes, busy_start))
            if busy_end < iv.end_minutes:
                result.append(FreeInterval(busy_end, iv.end_minutes))
    return result


async def get_tenant_operating_minutes(
    db: AsyncSession, tenant_id: uuid.UUID, target_date: date
) -> FreeInterval | None:
    """Return the tenant's operating window for target_date, or None if closed."""
    day_of_week = target_date.weekday()  # 0=Mon … 6=Sun
    result = await db.execute(
        select(TenantOperatingHours).where(
            and_(
                TenantOperatingHours.tenant_id == tenant_id,
                TenantOperatingHours.day_of_week == day_of_week,
                TenantOperatingHours.is_open == True,  # noqa: E712
            )
        )
    )
    row = result.scalar_one_or_none()
    if row is None or row.open_time is None or row.close_time is None:
        return None
    return FreeInterval(
        _time_to_minutes(row.open_time),
        _time_to_minutes(row.close_time),
    )


async def get_provider_working_windows(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    target_date: date,
) -> dict[uuid.UUID, list[FreeInterval]]:
    """Return per-provider free intervals after schedule + exceptions + busy spans."""
    day_of_week = target_date.weekday()

    # 1. Regular schedules that cover target_date
    sched_result = await db.execute(
        select(ProviderSchedule).where(
            and_(
                ProviderSchedule.tenant_id == tenant_id,
                ProviderSchedule.day_of_week == day_of_week,
                ProviderSchedule.is_working == True,  # noqa: E712
                ProviderSchedule.effective_from <= target_date,
                (ProviderSchedule.effective_to == None)  # noqa: E711
                | (ProviderSchedule.effective_to >= target_date),
            )
        )
    )
    schedules = sched_result.scalars().all()

    # Build raw free intervals per provider from regular schedule
    provider_free: dict[uuid.UUID, list[FreeInterval]] = {}
    for s in schedules:
        if s.start_time is None or s.end_time is None:
            continue
        iv = FreeInterval(_time_to_minutes(s.start_time), _time_to_minutes(s.end_time))
        provider_free.setdefault(s.provider_id, []).append(iv)

    # 2. Apply exceptions (overrides)
    exc_result = await db.execute(
        select(ProviderScheduleException).where(
            and_(
                ProviderScheduleException.tenant_id == tenant_id,
                ProviderScheduleException.exception_date == target_date,
            )
        )
    )
    exceptions = exc_result.scalars().all()
    for exc in exceptions:
        if not exc.is_working:
            # Provider has day off — remove entirely
            provider_free.pop(exc.provider_id, None)
        else:
            if exc.start_time and exc.end_time:
                provider_free[exc.provider_id] = [
                    FreeInterval(
                        _time_to_minutes(exc.start_time),
                        _time_to_minutes(exc.end_time),
                    )
                ]

    # 3. Subtract existing appointment items, respecting processing availability
    day_start = datetime.combine(target_date, time(0, 0))
    day_end = datetime.combine(target_date + timedelta(days=1), time(0, 0))

    # Load tenant default and per-provider processing availability
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    tenant_processing_default = tenant.providers_available_during_processing if tenant else True

    provider_ids_in_schedule = list(provider_free.keys())
    prov_result = await db.execute(
        select(Provider).where(
            and_(
                Provider.tenant_id == tenant_id,
                Provider.id.in_(provider_ids_in_schedule),
            )
        )
    )
    # effective: provider override if set, else tenant default
    provider_processing: dict[uuid.UUID, bool] = {
        p.id: (
            p.available_during_processing
            if p.available_during_processing is not None
            else tenant_processing_default
        )
        for p in prov_result.scalars().all()
    }

    items_result = await db.execute(
        select(AppointmentItem, Service).where(
            and_(
                AppointmentItem.tenant_id == tenant_id,
                AppointmentItem.start_time >= day_start,
                AppointmentItem.start_time < day_end,
                AppointmentItem.status.notin_([AppointmentItemStatus.cancelled]),
                AppointmentItem.service_id == Service.id,
            )
        )
    )
    for item, svc in items_result.all():
        start_min = item.start_time.hour * 60 + item.start_time.minute
        dur = item.duration_override_minutes or item.duration_minutes
        end_min = start_min + dur
        proc_offset = svc.processing_offset_minutes or 0
        proc_dur = svc.processing_duration_minutes or 0

        for pid in [item.provider_id, item.second_provider_id]:
            if pid is None or pid not in provider_free:
                continue
            avail_during = provider_processing.get(pid, tenant_processing_default)
            if avail_during and proc_dur > 0:
                # Subtract only the active spans, leaving the processing window free
                pre_end = start_min + proc_offset
                post_start = start_min + proc_offset + proc_dur
                if pre_end > start_min:
                    provider_free[pid] = _subtract_busy(provider_free[pid], start_min, pre_end)
                if post_start < end_min:
                    provider_free[pid] = _subtract_busy(provider_free[pid], post_start, end_min)
            else:
                provider_free[pid] = _subtract_busy(provider_free[pid], start_min, end_min)

    # 4. Subtract time blocks
    blocks_result = await db.execute(
        select(TimeBlock).where(
            and_(
                TimeBlock.tenant_id == tenant_id,
                TimeBlock.start_time >= day_start,
                TimeBlock.start_time < day_end,
            )
        )
    )
    for block in blocks_result.scalars().all():
        start_min = block.start_time.hour * 60 + block.start_time.minute
        end_min = start_min + block.duration_minutes
        if block.provider_id in provider_free:
            provider_free[block.provider_id] = _subtract_busy(
                provider_free[block.provider_id], start_min, end_min
            )

    return provider_free


async def get_station_occupancy(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    target_date: date,
) -> StationOccupancy:
    """Return a StationOccupancy loaded with existing appointment occupancy."""
    # Load tenant station totals
    ts_result = await db.execute(
        select(TenantStation).where(TenantStation.tenant_id == tenant_id)
    )
    totals: dict[str, int] = {}
    for ts in ts_result.scalars().all():
        totals[ts.station_type.value] = totals.get(ts.station_type.value, 0) + ts.count

    occ = StationOccupancy(totals=totals)

    # Load existing items that require stations (join to get required_station_type)
    day_start = datetime.combine(target_date, time(0, 0))
    day_end = datetime.combine(target_date + timedelta(days=1), time(0, 0))

    items_result = await db.execute(
        select(AppointmentItem, Service).where(
            and_(
                AppointmentItem.tenant_id == tenant_id,
                AppointmentItem.start_time >= day_start,
                AppointmentItem.start_time < day_end,
                AppointmentItem.status.notin_([AppointmentItemStatus.cancelled]),
                AppointmentItem.service_id == Service.id,
                Service.required_station_type != None,  # noqa: E711
            )
        )
    )
    for item, svc in items_result.all():
        start_min = item.start_time.hour * 60 + item.start_time.minute
        dur = item.duration_override_minutes or item.duration_minutes
        end_min = start_min + dur
        occ.claim(svc.required_station_type.value, start_min, end_min)

    return occ


async def get_service_capabilities(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    service_ids: list[uuid.UUID],
    target_date: date,
) -> dict[uuid.UUID, list[ServiceCapability]]:
    """Return per-service lists of capable providers with their timing overrides.

    Returns: {service_id -> [ServiceCapability, ...]}
    """
    result = await db.execute(
        select(ProviderServicePrice).where(
            and_(
                ProviderServicePrice.tenant_id == tenant_id,
                ProviderServicePrice.service_id.in_(service_ids),
                ProviderServicePrice.is_active == True,  # noqa: E712
                ProviderServicePrice.effective_from <= target_date,
                (ProviderServicePrice.effective_to == None)  # noqa: E711
                | (ProviderServicePrice.effective_to >= target_date),
            )
        )
    )
    prices = result.scalars().all()

    # Load base service durations
    svc_result = await db.execute(
        select(Service).where(
            and_(
                Service.tenant_id == tenant_id,
                Service.id.in_(service_ids),
            )
        )
    )
    svc_by_id = {s.id: s for s in svc_result.scalars().all()}

    capabilities: dict[uuid.UUID, list[ServiceCapability]] = {}
    for p in prices:
        svc = svc_by_id.get(p.service_id)
        if svc is None:
            continue
        cap = ServiceCapability(
            provider_id=p.provider_id,
            service_id=p.service_id,
            duration_minutes=p.duration_minutes or svc.duration_minutes,
            processing_offset_minutes=(
                p.processing_offset_minutes
                if p.processing_offset_minutes is not None
                else svc.processing_offset_minutes
            ),
            processing_duration_minutes=(
                p.processing_duration_minutes
                if p.processing_duration_minutes is not None
                else svc.processing_duration_minutes
            ),
        )
        capabilities.setdefault(p.service_id, []).append(cap)

    return capabilities
