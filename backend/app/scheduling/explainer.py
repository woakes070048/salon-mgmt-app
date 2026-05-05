"""Template-based rationale generator for recommendations.

No LLM — pure string interpolation based on the dominant cost factor.
"""

from __future__ import annotations

import uuid

from app.scheduling.types import EngineRecommendation, ScheduledItem


def build_rationale(
    rec: EngineRecommendation,
    preferred_providers: dict[uuid.UUID, uuid.UUID | None],
    provider_windows: dict[uuid.UUID, tuple[int, int]],
) -> str:
    """Return a one-line rationale string for the recommendation."""
    items = rec.items
    if not items:
        return "No services scheduled."

    # Check for dominant factors
    if rec.requires_consent:
        consent_items = _consent_items(items, provider_windows)
        if consent_items:
            names = " and ".join(i.provider_name for i in consent_items[:2])
            return f"Requires {names}'s approval to extend their schedule."

    # Check for preferred provider honours
    pref_honoured = [
        i for i in items
        if preferred_providers.get(i.service_id) == i.provider_id
    ]
    if pref_honoured and len(pref_honoured) == len(items):
        return "Honours your preferred provider for all services."
    if pref_honoured:
        names = " and ".join(i.provider_name for i in pref_honoured[:2])
        return f"Honours preferred provider ({names})."

    # Check for gap-filling (low idle time implies tight packing)
    by_provider: dict[uuid.UUID, list[ScheduledItem]] = {}
    for item in items:
        by_provider.setdefault(item.provider_id, []).append(item)

    total_idle = 0
    for prov_items in by_provider.values():
        sorted_items = sorted(prov_items, key=lambda i: i.start_minutes)
        for a, b in zip(sorted_items, sorted_items[1:]):
            total_idle += max(0, b.start_minutes - a.end_minutes)

    if total_idle == 0 and len(items) > 1:
        # Find the provider with the tightest packed day
        busiest = max(by_provider.keys(), key=lambda p: len(by_provider[p]))
        name = next(i.provider_name for i in items if i.provider_id == busiest)
        return f"Fills a gap in {name}'s day."

    # Default: earliest available
    earliest = min(items, key=lambda i: i.start_minutes)
    return f"Earliest available slot starting at {earliest.start_hhmm()}."


def build_summary_line(items: list[ScheduledItem]) -> str:
    """Build the '{Provider} ({service}) at {time}' summary string."""
    parts = []
    for item in sorted(items, key=lambda i: i.start_minutes):
        parts.append(f"{item.provider_name} ({item.service_name}) at {item.start_hhmm()}")
    return " + ".join(parts)


def _consent_items(
    items: list[ScheduledItem],
    provider_windows: dict[uuid.UUID, tuple[int, int]],
) -> list[ScheduledItem]:
    result = []
    for item in items:
        window = provider_windows.get(item.provider_id)
        if window is None:
            continue
        ws, we = window
        if item.start_minutes < ws or item.end_minutes > we:
            result.append(item)
    return result
