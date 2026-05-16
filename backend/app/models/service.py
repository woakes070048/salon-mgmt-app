import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey

from app.models.base import TenantScopedBase


class PricingType(str, enum.Enum):
    fixed = "fixed"
    hourly = "hourly"


class TenantStationType(str, enum.Enum):
    """Station type required for a service. Same values as scheduling.TenantStationType."""
    styling = "styling"
    colour = "colour"
    multi_purpose = "multi_purpose"
    processing = "processing"


class ServiceCategory(TenantScopedBase):
    __tablename__ = "service_categories"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Service(TenantScopedBase):
    __tablename__ = "services"

    category_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_categories.id"), nullable=False, index=True
    )
    service_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    pricing_type: Mapped[PricingType] = mapped_column(
        Enum(PricingType), nullable=False, default=PricingType.fixed
    )
    default_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    default_cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_cost_percent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    processing_offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requires_prior_consultation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_points_exempt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    split_commission: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suggestions: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_complimentary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    required_station_type: Mapped[TenantStationType | None] = mapped_column(
        Enum(TenantStationType, name="tenantstation_type", create_type=False), nullable=True
    )


class ServiceFeeHistory(TenantScopedBase):
    """Snapshot of (default_cost, is_cost_percent) for a service at a point in time.

    Each row's `effective_from` is the start of the period during which these
    values applied. The payroll calculator looks up the row with the latest
    `effective_from <= period_end` for each service to ensure historical
    payroll runs are not retroactively distorted by present-day fee changes.

    Written automatically on service create and on PATCH /services/{id} when
    `default_cost` or `is_cost_percent` changes.
    """
    __tablename__ = "service_fee_history"

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id"), nullable=False, index=True
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    product_fee: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_cost_percent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
