"""Merge migration heads

Revision ID: q3r4s5t6u7v8
Revises: a2b3c4d5e6f7, p2q3r4s5t6u7
Create Date: 2026-05-13

"""
from alembic import op

revision = 'q3r4s5t6u7v8'
down_revision = ('a2b3c4d5e6f7', 'p2q3r4s5t6u7')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
