"""Internal dataclasses for the scheduling engine.

These are NOT Pydantic models — they live only inside the engine and are
converted to Pydantic output schemas by engine.py before returning to callers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, time


@dataclass
class FreeInterval:
    """A contiguous window during which a provider is available."""
    start_minutes: int   # minutes since midnight
    end_minutes: int     # minutes since midnight (exclusive)

    @property
    def duration_minutes(self) -> int:
        return self.end_minutes - self.start_minutes


@dataclass
class StationOccupancy:
    """Tracks how many stations of each type are already occupied at any slot."""
    # station_type -> list[occupied_intervals] where each is (start_min, end_min)
    occupied: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    # total counts per type from tenant_stations
    totals: dict[str, int] = field(default_factory=dict)

    def is_available(self, station_type: str, start_min: int, end_min: int) -> bool:
        total = self.totals.get(station_type, 0)
        if total == 0:
            return True  # no station count configured → don't restrict
        occupied_intervals = self.occupied.get(station_type, [])
        concurrent = sum(
            1
            for (s, e) in occupied_intervals
            if s < end_min and e > start_min
        )
        return concurrent < total

    def claim(self, station_type: str, start_min: int, end_min: int) -> None:
        self.occupied.setdefault(station_type, []).append((start_min, end_min))

    def release(self, station_type: str, start_min: int, end_min: int) -> None:
        intervals = self.occupied.get(station_type, [])
        try:
            intervals.remove((start_min, end_min))
        except ValueError:
            pass


@dataclass
class ServiceCapability:
    """A provider's ability and timing overrides for one service."""
    provider_id: uuid.UUID
    service_id: uuid.UUID
    duration_minutes: int
    processing_offset_minutes: int
    processing_duration_minutes: int


@dataclass
class CandidateAssignment:
    """A candidate (service, provider, start_time) triple."""
    service_id: uuid.UUID
    service_name: str
    provider_id: uuid.UUID
    provider_name: str
    start_minutes: int          # minutes since midnight
    duration_minutes: int
    station_type_required: str | None
    # processing window if applicable (relative to start)
    processing_offset_minutes: int = 0
    processing_duration_minutes: int = 0


@dataclass
class ScheduledItem:
    """A confirmed assignment that forms part of a Recommendation."""
    service_id: uuid.UUID
    service_name: str
    provider_id: uuid.UUID
    provider_name: str
    start_minutes: int
    duration_minutes: int
    station_type_required: str | None

    @property
    def end_minutes(self) -> int:
        return self.start_minutes + self.duration_minutes

    def start_hhmm(self) -> str:
        h, m = divmod(self.start_minutes, 60)
        return f"{h:02d}:{m:02d}"

    def end_hhmm(self) -> str:
        h, m = divmod(self.end_minutes, 60)
        return f"{h:02d}:{m:02d}"


@dataclass
class EngineRequest:
    """Parsed internal representation of a StructuredRequest."""
    tenant_id: uuid.UUID
    target_date: date
    services: list[tuple[uuid.UUID, uuid.UUID | None]]  # (service_id, preferred_provider_id|None)
    earliest_start_minutes: int = 0      # minutes since midnight
    latest_end_minutes: int = 23 * 60    # default: very late


@dataclass
class EngineRecommendation:
    """Internal recommendation before conversion to Pydantic output."""
    items: list[ScheduledItem]
    score: float
    rationale: str
    requires_consent: bool

    @property
    def total_duration_minutes(self) -> int:
        if not self.items:
            return 0
        start = min(i.start_minutes for i in self.items)
        end = max(i.end_minutes for i in self.items)
        return end - start
