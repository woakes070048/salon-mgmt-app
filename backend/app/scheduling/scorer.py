"""Weighted cost function for the scheduling engine.

Lower score = better recommendation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.scheduling.types import FreeInterval, ScheduledItem


# Ordered list of (substring, rank) tuples — first matching substring on the
# (lowercased) service name wins. Lower rank = earlier in the sequence.
# Camo is checked BEFORE "colour" so "Camo Colour" gets the camo rank, which
# sits between cut and blowdry per Salon Lyol convention.
_SEQUENCE_RULES: list[tuple[str, int]] = [
    ("camo", 3),         # post-cut colour refresh — after cut, before blowdry
    ("colour", 0),       # regular colour services come first
    ("color", 0),        # US spelling
    ("cut", 2),          # haircut
    ("blowdry", 5),      # finishing styling
    ("blow dry", 5),
    ("blowout", 5),
]
_SEQUENCE_UNKNOWN_RANK = 99


@dataclass
class ScorerWeights:
    w_idle: float = 1.0        # minutes of idle time introduced
    w_pref: float = 150.0      # per provider preference mismatch — explicit pref dominates
    w_time: float = 0.5        # per minute distance from preferred window
    w_seq: float = 1000.0      # per sequencing violation
    w_overflow: float = 500.0  # per overflow minute
    w_consent: float = 30.0    # per item that requires provider consent
    w_pack: float = 0.3        # packing bonus (subtracted)
    w_lead_gap: float = 1.0    # minutes between booking start and prior appt for provider


_DEFAULT_WEIGHTS = ScorerWeights()


def score_partial(
    assigned: list[ScheduledItem],
    preferred_providers: dict[uuid.UUID, uuid.UUID | None],
    earliest_start: int,
    latest_end: int,
    weights: ScorerWeights = _DEFAULT_WEIGHTS,
    provider_free: dict[uuid.UUID, list[FreeInterval]] | None = None,
) -> float:
    """Score a partial or complete set of assigned items.

    Used both for pruning (partial) and final ranking (complete).

    If `provider_free` is supplied, an extra penalty is applied for booking
    a provider with a gap between the start of their free interval (which is
    typically the end of a prior appointment) and the start of the booking.
    This rewards tight packing against the provider's existing schedule.
    """
    if not assigned:
        return 0.0

    w = weights
    total = 0.0

    # ── Idle time (gaps between consecutive items across all providers) ─────
    # For each provider, sort their items and sum gaps between them.
    by_provider: dict[uuid.UUID, list[ScheduledItem]] = {}
    for item in assigned:
        by_provider.setdefault(item.provider_id, []).append(item)

    idle_minutes = 0
    for items in by_provider.values():
        items_sorted = sorted(items, key=lambda i: i.start_minutes)
        for a, b in zip(items_sorted, items_sorted[1:]):
            gap = b.start_minutes - a.end_minutes
            if gap > 0:
                idle_minutes += gap

    total += w.w_idle * idle_minutes

    # ── Lead-in gap (idle time between booking and prior appt for provider) ──
    # Penalise leaving a useless gap between the provider's previous
    # appointment (= start of their current free interval) and the booking.
    # Booking at 1:00 after a 1:00 ending appt = 0 gap; booking at 1:30 = 30.
    if provider_free is not None:
        for pid, items in by_provider.items():
            intervals = provider_free.get(pid)
            if not intervals:
                continue
            for item in items:
                # Find the free interval that contains this item
                containing = next(
                    (
                        iv for iv in intervals
                        if iv.start_minutes <= item.start_minutes <= iv.end_minutes
                    ),
                    None,
                )
                if containing is None:
                    continue
                lead_gap = item.start_minutes - containing.start_minutes
                # Only penalise if the prior booking is THIS one's start, not the
                # natural start of the day. Heuristic: skip if interval start ==
                # operating start (lead_gap from open isn't waste).
                if lead_gap > 0 and containing.start_minutes > earliest_start:
                    total += w.w_lead_gap * lead_gap

    # ── Provider preference mismatches ────────────────────────────────────────
    mismatches = 0
    for item in assigned:
        preferred = preferred_providers.get(item.service_id)
        if preferred is not None and item.provider_id != preferred:
            mismatches += 1
    total += w.w_pref * mismatches

    # ── Distance from preferred window ────────────────────────────────────────
    window_mid = (earliest_start + latest_end) / 2
    for item in assigned:
        item_mid = (item.start_minutes + item.end_minutes) / 2
        total += w.w_time * abs(item_mid - window_mid)

    # ── Sequencing violations (colour before cut before blowdry) ─────────────
    violations = _count_sequence_violations(assigned)
    total += w.w_seq * violations

    # ── Overflow (items extending past latest_end) ────────────────────────────
    overflow = 0
    for item in assigned:
        if item.end_minutes > latest_end:
            overflow += item.end_minutes - latest_end
    total += w.w_overflow * overflow

    # ── Client wait gap (penalise dead time the client spends waiting) ───────
    # Sort all items by start time and sum gaps between consecutive services
    # from the client's perspective (regardless of provider).
    if len(assigned) > 1:
        by_start = sorted(assigned, key=lambda i: i.start_minutes)
        client_wait = 0
        for a, b in zip(by_start, by_start[1:]):
            gap = b.start_minutes - a.end_minutes
            if gap > 0:
                client_wait += gap
        total += w.w_idle * client_wait

    # ── Packing bonus (reward tight, non-overlapping schedules) ──────────────
    if len(assigned) > 1:
        earliest = min(i.start_minutes for i in assigned)
        latest = max(i.end_minutes for i in assigned)
        span = latest - earliest
        total_service_mins = sum(i.duration_minutes for i in assigned)
        packing_bonus = max(0, total_service_mins - idle_minutes)
        total -= w.w_pack * packing_bonus

    return total


def score_requires_consent(
    assigned: list[ScheduledItem],
    provider_windows: dict[uuid.UUID, tuple[int, int]],  # pid -> (start, end)
) -> tuple[bool, int]:
    """Return (requires_consent, consent_count).

    An item requires consent if it starts before or ends after the provider's
    scheduled window. The score penalty is applied separately in the engine.
    """
    count = 0
    for item in assigned:
        window = provider_windows.get(item.provider_id)
        if window is None:
            continue
        ws, we = window
        if item.start_minutes < ws or item.end_minutes > we:
            count += 1
    return count > 0, count


def _service_sequence_rank(name: str) -> int:
    """Return the canonical position of a service name (lower = earlier).

    Matches against _SEQUENCE_RULES in order — first substring match wins.
    Unknown service names get a high rank, which means they don't trigger
    violations against any known service.
    """
    name_lower = name.lower()
    for fragment, rank in _SEQUENCE_RULES:
        if fragment in name_lower:
            return rank
    return _SEQUENCE_UNKNOWN_RANK


def _count_sequence_violations(items: list[ScheduledItem]) -> int:
    """Count pairs of items that violate canonical sequence order."""
    ranked = [(item, _service_sequence_rank(item.service_name)) for item in items]
    # Sort by start time
    by_start = sorted(ranked, key=lambda x: x[0].start_minutes)

    violations = 0
    for i in range(len(by_start)):
        for j in range(i + 1, len(by_start)):
            # Item i starts before item j
            rank_i = by_start[i][1]
            rank_j = by_start[j][1]
            if rank_i > rank_j:
                violations += 1
    return violations
