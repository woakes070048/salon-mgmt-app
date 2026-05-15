"""Add print_merchant_copy to tenant_printer_configs

Revision ID: w2x3y4z5a1b2
Revises: v1w2x3y4z5a1
Create Date: 2026-05-14

Idempotent: ADD COLUMN IF NOT EXISTS so a partially-applied prior deploy
doesn't block the migration.
"""
from alembic import op

revision = "w2x3y4z5a1b2"
down_revision = "v1w2x3y4z5a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tenant_printer_configs "
        "ADD COLUMN IF NOT EXISTS print_merchant_copy BOOLEAN "
        "NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE tenant_printer_configs DROP COLUMN IF EXISTS print_merchant_copy"
    )
