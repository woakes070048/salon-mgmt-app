import uuid
from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    logo_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    brand_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    slot_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    time_format: Mapped[str] = mapped_column(String(3), nullable=False, default="12h")
    default_language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    request_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    request_notification_recipients: Mapped[str | None] = mapped_column(Text(), nullable=True)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reminder_lead_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    reminder_send_time: Mapped[str] = mapped_column(String(5), nullable=False, default="09:00")
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    hours_summary: Mapped[str | None] = mapped_column(String(120), nullable=True)
    booking_email: Mapped[str | None] = mapped_column(Text(), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hst_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    booking_inbound_address: Mapped[str | None] = mapped_column(Text(), nullable=True, unique=True)
    providers_available_during_processing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
