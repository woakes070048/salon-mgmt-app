"""Add hst_number to tenants

Revision ID: u0v1w2x3y4z5
Revises: t9u0v1w2x3y4
Create Date: 2026-05-14

"""
import sqlalchemy as sa
from alembic import op

revision = "u0v1w2x3y4z5"
down_revision = "t9u0v1w2x3y4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("hst_number", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "hst_number")
