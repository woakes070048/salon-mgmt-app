"""Scheduling / recommendation API router.

Endpoints:
  POST /api/v1/scheduling/recommend    — get top-N booking recommendations
  GET  /api/v1/scheduling/stations     — list tenant station type counts
  POST /api/v1/scheduling/stations     — create / upsert a station type count
  PUT  /api/v1/scheduling/stations/{id} — update count
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from fastapi import Depends

from app.database import get_db
from app.deps import StaffUser
from app.models.client import Client
from app.models.scheduling import TenantStation
from app.scheduling.engine import recommend
from app.scheduling.types import EngineRequest
from app.schemas.scheduling import (
    RecommendationItem,
    Recommendation,
    RecommendationResponse,
    StructuredRequest,
    TenantStationCreate,
    TenantStationRead,
)

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


# ── Recommend ──────────────────────────────────────────────────────────────────

@router.post("/recommend", response_model=RecommendationResponse)
async def get_recommendations(
    body: StructuredRequest,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecommendationResponse:
    """Return top-3 booking recommendations for the requested services and date."""
    # Scope to current user's tenant
    tenant_id = current_user.tenant_id

    try:
        target_date = date.fromisoformat(body.desired_date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="desired_date must be a valid ISO date (YYYY-MM-DD)",
        )

    def hhmm_to_minutes(hhmm: str) -> int:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    earliest = hhmm_to_minutes(body.earliest_start) if body.earliest_start else 0
    latest = hhmm_to_minutes(body.latest_end) if body.latest_end else 23 * 60

    # Use client's preferred_provider_id as fallback for any service that
    # doesn't have an explicit preference set on the request.
    client_preferred_provider_id: uuid.UUID | None = None
    if body.client_id:
        client = await db.get(Client, body.client_id)
        if client:
            client_preferred_provider_id = client.preferred_provider_id

    engine_request = EngineRequest(
        tenant_id=tenant_id,
        target_date=target_date,
        services=[
            (svc.service_id, svc.preferred_provider_id or client_preferred_provider_id)
            for svc in body.services
        ],
        earliest_start_minutes=earliest,
        latest_end_minutes=latest,
    )

    engine_results = await recommend(db, engine_request, top_n=body.top_n)

    recs = [
        Recommendation(
            items=[
                RecommendationItem(
                    service_id=item.service_id,
                    service_name=item.service_name,
                    provider_id=item.provider_id,
                    provider_name=item.provider_name,
                    start_time=item.start_hhmm(),
                    end_time=item.end_hhmm(),
                    duration_minutes=item.duration_minutes,
                    station_type_required=item.station_type_required,
                )
                for item in rec.items
            ],
            total_duration_minutes=rec.total_duration_minutes,
            score=rec.score,
            rationale=rec.rationale,
            requires_consent=rec.requires_consent,
        )
        for rec in engine_results
    ]

    return RecommendationResponse(recommendations=recs, has_more=len(recs) >= body.top_n)


# ── Stations ───────────────────────────────────────────────────────────────────

@router.get("/stations", response_model=list[TenantStationRead])
async def list_stations(
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TenantStation]:
    result = await db.execute(
        select(TenantStation).where(TenantStation.tenant_id == current_user.tenant_id)
    )
    return list(result.scalars().all())


@router.post("/stations", response_model=TenantStationRead, status_code=status.HTTP_201_CREATED)
async def create_station(
    body: TenantStationCreate,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantStation:
    station = TenantStation(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        station_type=body.station_type,
        count=body.count,
    )
    db.add(station)
    await db.commit()
    await db.refresh(station)
    return station


@router.put("/stations/{station_id}", response_model=TenantStationRead)
async def update_station(
    station_id: uuid.UUID,
    body: TenantStationCreate,
    current_user: StaffUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantStation:
    result = await db.execute(
        select(TenantStation).where(
            and_(
                TenantStation.id == station_id,
                TenantStation.tenant_id == current_user.tenant_id,
            )
        )
    )
    station = result.scalar_one_or_none()
    if station is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Station not found")

    station.station_type = body.station_type
    station.count = body.count
    await db.commit()
    await db.refresh(station)
    return station
