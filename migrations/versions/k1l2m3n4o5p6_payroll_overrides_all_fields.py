"""Add service_commission, retail_commission, vacation_pct overrides to payroll_hour_overrides

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-05-11
"""
import sqlalchemy as sa
from alembic import op

revision = "k1l2m3n4o5p6"
down_revision = "j0k1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payroll_hour_overrides",
        sa.Column("service_commission_override", sa.Numeric(10, 2), nullable=True))
    op.add_column("payroll_hour_overrides",
        sa.Column("retail_commission_override", sa.Numeric(10, 2), nullable=True))
    op.add_column("payroll_hour_overrides",
        sa.Column("vacation_pct_override", sa.Numeric(5, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("payroll_hour_overrides", "vacation_pct_override")
    op.drop_column("payroll_hour_overrides", "retail_commission_override")
    op.drop_column("payroll_hour_overrides", "service_commission_override")
