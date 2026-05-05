import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantScopedBase


class AppointmentSource(str, enum.Enum):
    online_form = "online_form"
    email = "email"
    phone = "phone"
    walk_in = "walk_in"
    staff_entered = "staff_entered"


class AppointmentStatus(str, enum.Enum):
    requested = "requested"
    confirmed = "confirmed"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


class AppointmentRequestStatus(str, enum.Enum):
    new = "new"
    reviewed = "reviewed"
    converted = "converted"
    declined = "declined"


class ConfirmationStatus(str, enum.Enum):
    not_sent = "not_sent"
    draft = "draft"
    sent = "sent"
    skipped = "skipped"


class AppointmentItemStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class ReminderChannel(str, enum.Enum):
    email = "email"
    sms = "sms"


class ReminderStatus(str, enum.Enum):
    scheduled = "scheduled"
    sent = "sent"
    failed = "failed"
    cancelled = "cancelled"


class AppointmentRequest(TenantScopedBase):
    __tablename__ = "appointment_requests"

    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True, index=True
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    converted_to_appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", use_alter=True, name="fk_request_converted_to_appointment"),
        nullable=True,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    pronouns: Mapped[str | None] = mapped_column(String(50), nullable=True)
    submitted_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    desired_date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    desired_time_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[AppointmentSource] = mapped_column(
        Enum(AppointmentSource), nullable=False, default=AppointmentSource.online_form
    )
    special_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    waiver_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancellation_policy_acknowledged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    status: Mapped[AppointmentRequestStatus] = mapped_column(
        Enum(AppointmentRequestStatus), nullable=False, default=AppointmentRequestStatus.new
    )
    staff_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppointmentRequestItem(TenantScopedBase):
    __tablename__ = "appointment_request_items"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_requests.id"), nullable=False, index=True
    )
    converted_to_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_items.id"), nullable=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    preferred_provider_name: Mapped[str] = mapped_column(String(255), nullable=False)


class Appointment(TenantScopedBase):
    __tablename__ = "appointments"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True
    )
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_requests.id"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    appointment_date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, index=True)
    source: Mapped[AppointmentSource] = mapped_column(Enum(AppointmentSource), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus), nullable=False, default=AppointmentStatus.confirmed
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_charge_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recurring_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_status: Mapped[ConfirmationStatus] = mapped_column(
        Enum(ConfirmationStatus), nullable=False, default=ConfirmationStatus.not_sent
    )
    confirmation_draft_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_draft_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class AppointmentItem(TenantScopedBase):
    __tablename__ = "appointment_items"

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=False, index=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id"), nullable=False
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id"), nullable=False, index=True
    )
    second_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id"), nullable=True
    )
    station_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stations.id"), nullable=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_override_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    price_is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[AppointmentItemStatus] = mapped_column(
        Enum(AppointmentItemStatus), nullable=False, default=AppointmentItemStatus.pending
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class AppointmentReminder(TenantScopedBase):
    __tablename__ = "appointment_reminders"

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=False, index=True
    )
    channel: Mapped[ReminderChannel] = mapped_column(Enum(ReminderChannel), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[ReminderStatus] = mapped_column(
        Enum(ReminderStatus), nullable=False, default=ReminderStatus.scheduled
    )
