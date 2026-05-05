import enum
import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Enum, Integer, Numeric, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantScopedBase


class ProviderType(str, enum.Enum):
    stylist = "stylist"
    colourist = "colourist"
    dualist = "dualist"


class PayType(str, enum.Enum):
    hourly = "hourly"
    salary = "salary"
    commission = "commission"


class EIRateType(str, enum.Enum):
    normal = "normal"
    reduced = "reduced"


class OnlineBookingVisibility(str, enum.Enum):
    not_available = "not_available"
    available_to_my_clients = "available_to_my_clients"
    available_to_all = "available_to_all"


class Provider(TenantScopedBase):
    __tablename__ = "providers"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True, index=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_type: Mapped[ProviderType] = mapped_column(Enum(ProviderType), nullable=False)
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Personal info
    sex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    province: Mapped[str | None] = mapped_column(String(50), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    personal_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cell_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    other_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Employment
    job_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_day_worked: Mapped[date | None] = mapped_column(Date, nullable=True)
    certification: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Compensation — SIN and bank account encrypted at application level before storage
    sin_encrypted: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pay_type: Mapped[PayType | None] = mapped_column(Enum(PayType), nullable=True)
    pay_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    hourly_minimum: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    vacation_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True, default=4.00)
    retail_commission_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True, default=10.00)
    commission_tiers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    product_fee_styling_flat: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    product_fee_colour_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Banking
    bank_institution_no: Mapped[str | None] = mapped_column(String(10), nullable=True)
    bank_transit_no: Mapped[str | None] = mapped_column(String(10), nullable=True)
    bank_account_encrypted: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Tax
    cpp_exempt: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ei_exempt: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ei_rate_type: Mapped[EIRateType | None] = mapped_column(Enum(EIRateType), nullable=True)
    province_of_taxation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wcb_csst_exempt: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    td1_federal_credit: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    td1_provincial_credit: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Booking behaviour
    can_be_cashier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    makes_appointments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_appointments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    available_during_processing: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    booking_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    online_booking_visibility: Mapped[OnlineBookingVisibility] = mapped_column(
        Enum(OnlineBookingVisibility),
        nullable=False,
        default=OnlineBookingVisibility.not_available,
    )
