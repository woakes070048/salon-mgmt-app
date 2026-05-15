"""Weighted cost function for the scheduling engine.

Lower score = better recommendation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.scheduling.types import ScheduledItem


# Canonical service name fragments for sequence checking.
# Lower index = earlier in sequence.
_CANONICAL_SEQUENCE = ["colour", "cut", "blowdry", "blow dry", "blowout"]


@dataclass
class ScorerWeights:
    w_idle: float = 1.0        # minutes of idle time introduced
    w_pref: float = 30.0       # per provider preference mismatch
    w_time: float = 0.5        # per minute distance from preferred window
    w_seq: float = 1000.0      # per sequencing violation
    w_overflow: float = 500.0  # per overflow minute
    w_consent: float = 30.0    # per item that requires provider consent
    w_pack: float = 0.3        # packing bonus (subtracted)


_DEFAULT_WEIGHTS = ScorerWeights()


def score_partial(
    assigned: list[ScheduledItem],
    preferred_providers: dict[uuid.UUID, uuid.UUID | None],
    earliest_start: int,
    latest_end: int,
    weights: ScorerWeights = _DEFAULT_WEIGHTS,
) -> float:
    """Score a partial or complete set of assigned items.

    Used both for pruning (partial) and final ranking (complete).
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
    """Return the canonical position of a service name (lower = earlier)."""
    name_lower = name.lower()
    for i, fragment in enumerate(_CANONICAL_SEQUENCE):
        if fragment in name_lower:
            return i
    return len(_CANONICAL_SEQUENCE)  # unknown → comes last (no violation)


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
