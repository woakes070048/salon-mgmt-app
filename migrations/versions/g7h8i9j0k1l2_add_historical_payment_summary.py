"""Add historical_payment_summary table

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-07

Stores monthly payment type totals sourced from external reports (e.g. Milano)
for months predating live SalonOS transactions. Used to backfill the Payment
Reconciliation section of the monthly sales report for year-end accuracy.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "g7h8i9j0k1l2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "historical_payment_summary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("label", sa.String(80), nullable=False),   # e.g. "VISA", "CASH", "DEBIT"
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("source", sa.String(80), nullable=False, server_default="milano"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("tenant_id", "year", "month", "label", name="uq_hist_payment_tenant_period_label"),
    )
    op.create_index("ix_historical_payment_summary_tenant_id", "historical_payment_summary", ["tenant_id"])
    op.create_index("ix_historical_payment_summary_period", "historical_payment_summary", ["tenant_id", "year", "month"])


def downgrade() -> None:
    op.drop_table("historical_payment_summary")
