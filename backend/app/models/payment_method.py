import enum

from sqlalchemy import Boolean, Enum as SQLEnum, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantScopedBase


class PaymentMethodKind(str, enum.Enum):
    cash = "cash"
    card = "card"
    transfer = "transfer"
    other = "other"
    on_account = "on_account"


class TenantPaymentMethod(TenantScopedBase):
    __tablename__ = "tenant_payment_methods"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_tenant_payment_method_code"),
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[PaymentMethodKind] = mapped_column(
        SQLEnum(PaymentMethodKind, name="payment_method_kind"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
