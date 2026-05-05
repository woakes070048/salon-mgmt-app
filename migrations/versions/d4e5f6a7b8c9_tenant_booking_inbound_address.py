"""Add booking_inbound_address to tenants

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-05

New column:
  - tenants.booking_inbound_address — the Roux-administered inbound routing
    address for this tenant (e.g. salon-lyol@inbound.roux.salon). Tenants
    forward their public booking email here; the webhook router matches on
    this address to identify the tenant.
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("booking_inbound_address", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_tenants_booking_inbound_address",
        "tenants",
        ["booking_inbound_address"],
        unique=True,
        postgresql_where=sa.text("booking_inbound_address IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tenants_booking_inbound_address", table_name="tenants")
    op.drop_column("tenants", "booking_inbound_address")
