"""Service product fee effective-date history (P-PAYROLL-1)

Revision ID: y4z5a1b2c3d4
Revises: x3y4z5a1b2c3
Create Date: 2026-05-15

Creates service_fee_history so the payroll calculator can look up the fee
that was in effect at a given period_end, instead of always using the
service's current fee. Seeds one row per existing service with their
current values and effective_from = '2000-01-01' (sentinel meaning
"applied before any explicit change") so existing payroll queries
immediately return a row.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "y4z5a1b2c3d4"
down_revision = "x3y4z5a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_fee_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("service_id", UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=False, index=True),
        sa.Column("effective_from", sa.Date(), nullable=False, index=True),
        sa.Column("product_fee", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_cost_percent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # Seed one history row per existing service capturing today's values.
    # effective_from = '2000-01-01' is a sentinel — "this fee applied for any
    # period that began before any explicit fee change was recorded".
    op.execute("""
        INSERT INTO service_fee_history (
            tenant_id, service_id, effective_from, product_fee, is_cost_percent
        )
        SELECT
            tenant_id, id, DATE '2000-01-01', default_cost, is_cost_percent
        FROM services
    """)


def downgrade() -> None:
    op.drop_table("service_fee_history")
