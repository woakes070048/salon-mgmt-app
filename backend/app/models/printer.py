from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantScopedBase


class TenantPrinterConfig(TenantScopedBase):
    __tablename__ = "tenant_printer_configs"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_printer_config"),)

    printer_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="EPSON TM-T88V Receipt"
    )
    printer_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    printer_port: Mapped[int] = mapped_column(Integer, nullable=False, default=9100)
    paper_width: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    auto_print_on_cash: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cash_drawer_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    print_merchant_copy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    receipt_logo_url: Mapped[str | None] = mapped_column(Text(), nullable=True)
