"""Add tenant_printer_configs table

Revision ID: p2q3r4s5t6u7
Revises: k1l2m3n4o5p6
Create Date: 2026-05-13 01:28:20.955141

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'p2q3r4s5t6u7'
down_revision = 'k1l2m3n4o5p6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_printer_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("printer_name", sa.String(255), nullable=False, server_default="EPSON TM-T88V Receipt"),
        sa.Column("printer_host", sa.String(255), nullable=True),
        sa.Column("printer_port", sa.Integer, nullable=False, server_default="9100"),
        sa.Column("paper_width", sa.Integer, nullable=False, server_default="80"),
        sa.Column("auto_print_on_cash", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("cash_drawer_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("receipt_logo_url", sa.Text, nullable=True),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_printer_config"),
    )


def downgrade() -> None:
    op.drop_table("tenant_printer_configs")
