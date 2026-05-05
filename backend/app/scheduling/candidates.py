"""Candidate enumeration for the scheduling engine.

For each service in the request, for each qualified provider, enumerate
candidate start times in 10-minute granularity within their free intervals.
Checks station availability before yielding each candidate.
"""

from __future__ import annotations

import uuid
from typing import Generator

from app.scheduling.types import (
    CandidateAssignment,
    FreeInterval,
    ServiceCapability,
    StationOccupancy,
)

_SLOT = 10  # minutes


def enumerate_candidates(
    service_id: uuid.UUID,
    service_name: str,
    capabilities: list[ServiceCapability],
    provider_free: dict[uuid.UUID, list[FreeInterval]],
    provider_names: dict[uuid.UUID, str],
    station_occupancy: StationOccupancy,
    station_type_required: str | None,
    earliest_start: int,
    latest_end: int,
) -> Generator[CandidateAssignment, None, None]:
    """Yield CandidateAssignment for (service_id, provider_id, start_minute).

    Granularity: 10-minute slots.
    Station availability is checked but not claimed — the engine claims
    during DFS and releases on backtrack.
    """
    for cap in capabilities:
        pid = cap.provider_id
        free_intervals = provider_free.get(pid)
        if not free_intervals:
            continue

        dur = cap.duration_minutes
        pname = provider_names.get(pid, str(pid))

        for iv in free_intervals:
            # Clamp interval to [earliest_start, latest_end - dur]
            win_start = max(iv.start_minutes, earliest_start)
            win_end = min(iv.end_minutes, latest_end)
            if win_start + dur > win_end:
                continue

            # Snap to 10-minute grid
            t = _snap_up(win_start, _SLOT)
            while t + dur <= win_end:
                if station_type_required is None or station_occupancy.is_available(
                    station_type_required, t, t + dur
                ):
                    yield CandidateAssignment(
                        service_id=service_id,
                        service_name=service_name,
                        provider_id=pid,
                        provider_name=pname,
                        start_minutes=t,
                        duration_minutes=dur,
                        station_type_required=station_type_required,
                        processing_offset_minutes=cap.processing_offset_minutes,
                        processing_duration_minutes=cap.processing_duration_minutes,
                    )
                t += _SLOT


def _snap_up(minutes: int, slot: int) -> int:
    """Round minutes up to the nearest slot boundary."""
    remainder = minutes % slot
    if remainder == 0:
        return minutes
    return minutes + (slot - remainder)
