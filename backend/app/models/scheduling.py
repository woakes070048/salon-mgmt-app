import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantScopedBase
from app.database import Base


class TenantStationType(str, enum.Enum):
    styling = "styling"
    colour = "colour"
    multi_purpose = "multi_purpose"
    processing = "processing"


class ConsentReason(str, enum.Enum):
    early_start = "early_start"
    late_end = "late_end"
    processing_overlap = "processing_overlap"


class ConsentStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class TenantStation(TenantScopedBase):
    __tablename__ = "tenant_stations"

    station_type: Mapped[TenantStationType] = mapped_column(
        Enum(TenantStationType, name="tenantstation_type", create_type=False), nullable=False
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ServiceAlias(TenantScopedBase):
    __tablename__ = "service_aliases"

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)


class ProviderConsentRequest(TenantScopedBase):
    __tablename__ = "provider_consent_requests"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False, index=True
    )
    appointment_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_requests.id"), nullable=True
    )
    reason: Mapped[ConsentReason] = mapped_column(
        Enum(ConsentReason, name="consent_reason", create_type=False), nullable=False
    )
    proposed_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    proposed_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[ConsentStatus] = mapped_column(
        Enum(ConsentStatus, name="consent_status", create_type=False),
        nullable=False,
        default=ConsentStatus.pending,
    )
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RecommendationLog(Base):
    """Audit log for recommendation engine calls. No updated_at — append-only."""

    __tablename__ = "recommendation_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_requests.id"), nullable=True
    )
    email_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    chosen_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
