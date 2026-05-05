"""Pydantic schemas for the booking recommendation engine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Supporting value types ─────────────────────────────────────────────────────

TenantStationTypeStr = Literal["styling", "colour", "multi_purpose", "processing"]
ConsentReasonStr = Literal["early_start", "late_end", "processing_overlap"]
ConsentStatusStr = Literal["pending", "accepted", "declined"]


# ── TenantStation ──────────────────────────────────────────────────────────────

class TenantStationCreate(BaseModel):
    station_type: TenantStationTypeStr
    count: int = Field(default=1, ge=1)


class TenantStationRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    station_type: TenantStationTypeStr
    count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── ServiceAlias ───────────────────────────────────────────────────────────────

class ServiceAliasCreate(BaseModel):
    service_id: uuid.UUID
    alias: str = Field(min_length=1, max_length=500)


class ServiceAliasRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    service_id: uuid.UUID
    alias: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── ProviderConsentRequest ─────────────────────────────────────────────────────

class ProviderConsentRequestRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    provider_id: uuid.UUID
    appointment_request_id: uuid.UUID | None
    reason: ConsentReasonStr
    proposed_start: datetime | None
    proposed_end: datetime | None
    status: ConsentStatusStr
    notified_at: datetime | None
    responded_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── RecommendationLog ──────────────────────────────────────────────────────────

class RecommendationLogRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    request_id: uuid.UUID | None
    email_message_id: str | None
    recommendations_json: dict
    chosen_index: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Recommendation engine input / output ───────────────────────────────────────

class RequestedService(BaseModel):
    service_id: uuid.UUID
    preferred_provider_id: uuid.UUID | None = None


class StructuredRequest(BaseModel):
    tenant_id: uuid.UUID
    client_id: uuid.UUID | None = None
    appointment_request_id: uuid.UUID | None = None
    services: list[RequestedService] = Field(min_length=1)
    desired_date: str = Field(
        description="ISO date string, e.g. 2026-06-15",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    earliest_start: str | None = Field(
        default=None,
        description="HH:MM — earliest acceptable start time",
        pattern=r"^\d{2}:\d{2}$",
    )
    latest_end: str | None = Field(
        default=None,
        description="HH:MM — latest acceptable end time",
        pattern=r"^\d{2}:\d{2}$",
    )


class RecommendationItem(BaseModel):
    """One service assignment within a recommendation."""
    service_id: uuid.UUID
    service_name: str
    provider_id: uuid.UUID
    provider_name: str
    start_time: str   # HH:MM
    end_time: str     # HH:MM
    duration_minutes: int
    station_type_required: TenantStationTypeStr | None = None


class Recommendation(BaseModel):
    """One complete recommended slot — assignments for all requested services."""
    items: list[RecommendationItem]
    total_duration_minutes: int
    score: float
    rationale: str
    requires_consent: bool


class RecommendationResponse(BaseModel):
    recommendations: list[Recommendation]
    has_more: bool = False
