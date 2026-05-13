"""Add website to tenants

Revision ID: t9u0v1w2x3y4
Revises: s8t9u0v1w2x3
Create Date: 2026-05-13

"""
import sqlalchemy as sa
from alembic import op

revision = "t9u0v1w2x3y4"
down_revision = "s8t9u0v1w2x3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("website", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "website")
