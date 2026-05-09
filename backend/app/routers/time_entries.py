"""
Staff time entries — clock-in / clock-out tracking.

POST   /time-entries                — clock in a provider (staff+)
POST   /time-entries/{id}/check-out — clock out (staff+)
GET    /time-entries?date=YYYY-MM-DD — list entries for a date (default today)
PATCH  /time-entries/{id}           — edit times or notes (admin)
DELETE /time-entries/{id}           — delete entry (admin)
"""
import uuid
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import AdminUser, StaffUser, CurrentUser
from app.models.provider import Provider
from app.models.staff_time_entry import StaffTimeEntry

router = APIRouter(prefix="/time-entries", tags=["time-entries"])


# ── Response / request models ─────────────────────────────────────────────────

class TimeEntryOut(BaseModel):
    id: str
    provider_id: str
    provider_name: str
    date: str              # YYYY-MM-DD
    check_in_at: str       # ISO datetime
    check_out_at: str | None
    hours: float | None    # null if still checked in
    notes: str | None


class CheckInBody(BaseModel):
    provider_id: str
    check_in_at: datetime | None = None   # defaults to now()
    check_out_at: datetime | None = None  # optional — set immediately for manual entries
    notes: str | None = None


class CheckOutBody(BaseModel):
    check_out_at: datetime | None = None  # defaults to now()


class TimeEntryPatch(BaseModel):
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    notes: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hours(entry: StaffTimeEntry) -> float | None:
    if entry.check_out_at is None:
        return None
    delta = entry.check_out_at - entry.check_in_at
    return round(delta.total_seconds() / 3600, 2)


async def _serialize(entry: StaffTimeEntry, db: AsyncSession) -> TimeEntryOut:
    provider = (
        await db.execute(select(Provider).where(Provider.id == entry.provider_id))
    ).scalar_one_or_none()
    name = provider.display_name if provider else str(entry.provider_id)
    return TimeEntryOut(
        id=str(entry.id),
        provider_id=str(entry.provider_id),
        provider_name=name,
        date=entry.date.isoformat(),
        check_in_at=entry.check_in_at.isoformat(),
        check_out_at=entry.check_out_at.isoformat() if entry.check_out_at else None,
        hours=_hours(entry),
        notes=entry.notes,
    )


async def _load(entry_id: str, tenant_id: uuid.UUID, db: AsyncSession) -> StaffTimeEntry:
    entry = (
        await db.execute(
            select(StaffTimeEntry).where(
                StaffTimeEntry.id == uuid.UUID(entry_id),
                StaffTimeEntry.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time entry not found")
    return entry


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[TimeEntryOut])
async def list_entries(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    date: date | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    provider_id: str | None = Query(default=None),
) -> list[TimeEntryOut]:
    from app.models.user import UserRole
    tid = current_user.tenant_id
    is_admin = current_user.role in (UserRole.tenant_admin, UserRole.super_admin)

    filters = [StaffTimeEntry.tenant_id == tid]

    if provider_id:
        if not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required to filter by provider")
        filters.append(StaffTimeEntry.provider_id == uuid.UUID(provider_id))

    if date_from and date_to:
        filters.append(StaffTimeEntry.date >= date_from)
        filters.append(StaffTimeEntry.date <= date_to)
    else:
        target = date or datetime.now(timezone.utc).date()
        filters.append(StaffTimeEntry.date == target)

    entries = (
        await db.execute(
            select(StaffTimeEntry).where(*filters).order_by(StaffTimeEntry.date, StaffTimeEntry.check_in_at)
        )
    ).scalars().all()
    return [await _serialize(e, db) for e in entries]


@router.post("", response_model=TimeEntryOut, status_code=status.HTTP_201_CREATED)
async def check_in(
    body: CheckInBody,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TimeEntryOut:
    tid = current_user.tenant_id
    provider_id = uuid.UUID(body.provider_id)

    provider = (
        await db.execute(
            select(Provider).where(Provider.id == provider_id, Provider.tenant_id == tid)
        )
    ).scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provider not found")

    # Prevent double check-in on the same date
    check_in_time = body.check_in_at or datetime.now(timezone.utc)
    work_date = check_in_time.date() if hasattr(check_in_time, 'date') else check_in_time

    already_in = (
        await db.execute(
            select(StaffTimeEntry).where(
                StaffTimeEntry.tenant_id == tid,
                StaffTimeEntry.provider_id == provider_id,
                StaffTimeEntry.date == work_date,
                StaffTimeEntry.check_out_at == None,  # noqa: E711
            )
        )
    ).scalar_one_or_none()
    if already_in is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{provider.display_name} is already checked in",
        )

    entry = StaffTimeEntry(
        tenant_id=tid,
        provider_id=provider_id,
        date=work_date,
        check_in_at=check_in_time,
        check_out_at=body.check_out_at,
        notes=body.notes,
        created_by_user_id=current_user.id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return await _serialize(entry, db)


@router.post("/{entry_id}/check-out", response_model=TimeEntryOut)
async def check_out(
    entry_id: str,
    body: CheckOutBody,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TimeEntryOut:
    entry = await _load(entry_id, current_user.tenant_id, db)
    if entry.check_out_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already checked out")
    entry.check_out_at = body.check_out_at or datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(entry)
    return await _serialize(entry, db)


@router.patch("/{entry_id}", response_model=TimeEntryOut)
async def edit_entry(
    entry_id: str,
    body: TimeEntryPatch,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TimeEntryOut:
    entry = await _load(entry_id, current_user.tenant_id, db)
    if body.check_in_at is not None:
        entry.check_in_at = body.check_in_at
        entry.date = body.check_in_at.date()
    if body.check_out_at is not None:
        entry.check_out_at = body.check_out_at
    if "notes" in body.model_fields_set:
        entry.notes = body.notes
    await db.commit()
    await db.refresh(entry)
    return await _serialize(entry, db)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: str,
    current_user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    entry = await _load(entry_id, current_user.tenant_id, db)
    await db.delete(entry)
    await db.commit()
