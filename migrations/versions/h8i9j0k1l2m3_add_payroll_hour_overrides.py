"""Add payroll_hour_overrides table

Revision ID: h8i9j0k1l2m3
Revises: 4e3a1d4e4ada
Create Date: 2026-05-11

Stores admin-saved hour overrides for payroll periods.
When an override exists it takes precedence over actual time entries
and scheduled hours for that provider + period.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "h8i9j0k1l2m3"
down_revision = "4e3a1d4e4ada"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_hour_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.UniqueConstraint(
            "tenant_id", "provider_id", "period_start", "period_end",
            name="uq_payroll_hour_overrides"
        ),
    )
    op.create_index("ix_payroll_hour_overrides_tenant_period",
                    "payroll_hour_overrides",
                    ["tenant_id", "period_start", "period_end"])


def downgrade() -> None:
    op.drop_table("payroll_hour_overrides")
