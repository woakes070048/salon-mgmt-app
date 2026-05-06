"""Public API for the booking recommendation engine.

Usage:
    from app.scheduling.engine import recommend
    results = await recommend(db, request, top_n=3)
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.scheduling.availability import (
    get_provider_working_windows,
    get_service_capabilities,
    get_station_occupancy,
    get_tenant_operating_minutes,
)
from app.scheduling.candidates import enumerate_candidates
from app.scheduling.explainer import build_rationale
from app.scheduling.scorer import (
    ScorerWeights,
    _DEFAULT_WEIGHTS,
    score_partial,
    score_requires_consent,
)
from app.scheduling.types import (
    CandidateAssignment,
    EngineRecommendation,
    EngineRequest,
    ScheduledItem,
)
from app.models.provider import Provider
from app.models.service import Service
from sqlalchemy import and_, select


async def recommend(
    db: AsyncSession,
    request: EngineRequest,
    top_n: int = 3,
    weights: ScorerWeights = _DEFAULT_WEIGHTS,
) -> list[EngineRecommendation]:
    """Run the recommendation engine and return up to top_n recommendations.

    Algorithm: DFS over service assignments with branch-and-bound pruning.
    """
    tenant_id = request.tenant_id
    target_date = request.target_date

    # ── Load data ──────────────────────────────────────────────────────────────
    operating = await get_tenant_operating_minutes(db, tenant_id, target_date)
    earliest = max(
        request.earliest_start_minutes,
        operating.start_minutes if operating else 0,
    )
    latest = min(
        request.latest_end_minutes,
        operating.end_minutes if operating else 23 * 60,
    )

    provider_free = await get_provider_working_windows(db, tenant_id, target_date)
    station_occ = await get_station_occupancy(db, tenant_id, target_date)

    service_ids = [sid for sid, _ in request.services]
    capabilities = await get_service_capabilities(db, tenant_id, service_ids, target_date)

    # Load service names and station types
    svc_result = await db.execute(
        select(Service).where(
            and_(Service.tenant_id == tenant_id, Service.id.in_(service_ids))
        )
    )
    services_by_id = {s.id: s for s in svc_result.scalars().all()}

    # Load provider names
    provider_ids = {
        cap.provider_id
        for caps in capabilities.values()
        for cap in caps
    }
    prov_result = await db.execute(
        select(Provider).where(
            and_(Provider.tenant_id == tenant_id, Provider.id.in_(provider_ids))
        )
    )
    provider_names: dict[uuid.UUID, str] = {
        p.id: p.display_name for p in prov_result.scalars().all()
    }

    # Provider scheduled windows for consent checks: pid -> (start_min, end_min)
    provider_windows: dict[uuid.UUID, tuple[int, int]] = {}
    for pid, intervals in provider_free.items():
        if intervals:
            start = min(iv.start_minutes for iv in intervals)
            end = max(iv.end_minutes for iv in intervals)
            provider_windows[pid] = (start, end)

    # Preferred providers map: service_id -> preferred_provider_id | None
    preferred_providers: dict[uuid.UUID, uuid.UUID | None] = {
        sid: ppid for sid, ppid in request.services
    }

    # ── Pre-enumerate candidates per service ───────────────────────────────────
    service_candidates: list[list[CandidateAssignment]] = []
    for sid, _ppid in request.services:
        svc = services_by_id.get(sid)
        svc_name = svc.name if svc else str(sid)
        stn_type = svc.required_station_type.value if svc and svc.required_station_type else None
        caps = capabilities.get(sid, [])
        candidates = list(
            enumerate_candidates(
                service_id=sid,
                service_name=svc_name,
                capabilities=caps,
                provider_free=provider_free,
                provider_names=provider_names,
                station_occupancy=station_occ,
                station_type_required=stn_type,
                earliest_start=earliest,
                latest_end=latest,
            )
        )
        # Sort candidates: preferred provider first, then by start time
        ppid = preferred_providers.get(sid)
        candidates.sort(key=lambda c: (0 if c.provider_id == ppid else 1, c.start_minutes))
        service_candidates.append(candidates)

    # ── DFS with branch-and-bound ──────────────────────────────────────────────
    results: list[tuple[float, EngineRecommendation]] = []
    best_score = float("inf")

    def dfs(
        depth: int,
        assigned: list[ScheduledItem],
        claimed_stations: list[tuple[str, int, int]],  # (type, start, end) for cleanup
        partial_score: float,
    ) -> None:
        nonlocal best_score

        if depth == len(service_candidates):
            # Complete assignment
            requires_consent, consent_count = score_requires_consent(
                assigned, provider_windows
            )
            final_score = partial_score + weights.w_consent * consent_count
            if final_score >= best_score:
                return
            best_score = final_score

            # Build recommendation
            rec = EngineRecommendation(
                items=list(assigned),
                score=final_score,
                rationale="",
                requires_consent=requires_consent,
            )
            rec.rationale = build_rationale(rec, preferred_providers, provider_windows)
            results.append((final_score, rec))

            # Keep only top_n * 3 candidates to bound memory, prune aggressively
            if len(results) > top_n * 3:
                results.sort(key=lambda x: x[0])
                del results[top_n * 3:]
                best_score = results[-1][0]
            return

        candidates = service_candidates[depth]

        for cand in candidates:
            # Client can only be in one chair at a time — each service must
            # start after all previously assigned services have ended.
            if assigned and cand.start_minutes < max(prev.end_minutes for prev in assigned):
                continue

            # Provider already used for a different service at overlapping time?
            conflict = False
            for prev in assigned:
                if prev.provider_id == cand.provider_id:
                    if (
                        cand.start_minutes < prev.end_minutes
                        and cand.start_minutes + cand.duration_minutes > prev.start_minutes
                    ):
                        conflict = True
                        break
            if conflict:
                continue

            # Station availability
            if cand.station_type_required:
                if not station_occ.is_available(
                    cand.station_type_required,
                    cand.start_minutes,
                    cand.start_minutes + cand.duration_minutes,
                ):
                    continue
                station_occ.claim(
                    cand.station_type_required,
                    cand.start_minutes,
                    cand.start_minutes + cand.duration_minutes,
                )
                claimed_stations.append(
                    (
                        cand.station_type_required,
                        cand.start_minutes,
                        cand.start_minutes + cand.duration_minutes,
                    )
                )

            item = ScheduledItem(
                service_id=cand.service_id,
                service_name=cand.service_name,
                provider_id=cand.provider_id,
                provider_name=cand.provider_name,
                start_minutes=cand.start_minutes,
                duration_minutes=cand.duration_minutes,
                station_type_required=cand.station_type_required,
            )
            assigned.append(item)

            # Compute partial score for pruning
            new_partial = score_partial(
                assigned, preferred_providers, earliest, latest, weights
            )
            if new_partial < best_score:
                dfs(depth + 1, assigned, claimed_stations, new_partial)

            assigned.pop()
            if cand.station_type_required and claimed_stations:
                entry = claimed_stations[-1]
                station_occ.release(entry[0], entry[1], entry[2])
                claimed_stations.pop()

    dfs(0, [], [], 0.0)

    results.sort(key=lambda x: x[0])

    # Deduplicate: two recommendations are the same if every item has the same
    # provider + start_minutes (ignore floating point score differences).
    seen: set[tuple[tuple[uuid.UUID, int], ...]] = set()
    unique: list[EngineRecommendation] = []
    for _, rec in results:
        key = tuple(
            sorted((i.provider_id, i.start_minutes) for i in rec.items)
        )
        if key not in seen:
            seen.add(key)
            unique.append(rec)
        if len(unique) >= top_n:
            break

    return unique
