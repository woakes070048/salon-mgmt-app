"""Tenant-configurable acknowledgements shown on the public booking form.

Each acknowledgement is a policy block (e.g. waiver, cancellation policy)
the client must agree to before submitting a booking request. Title and
body text are tenant-defined; optional link points to the full policy.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantScopedBase


class TenantAcknowledgement(TenantScopedBase):
    __tablename__ = "tenant_acknowledgements"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional hyperlink shown inside the body. If both are set, the rendered
    # body will show body_text with `{link}` replaced by an anchor tag using
    # link_text as the visible label and link_url as the href.
    link_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    link_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
