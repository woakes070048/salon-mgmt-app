"""merge heads

Revision ID: 4e3a1d4e4ada
Revises: g7h8i9j0k1l2, p1q2r3s4t5u6
Create Date: 2026-05-09 15:41:49.125842

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4e3a1d4e4ada'
down_revision: Union[str, None] = ('g7h8i9j0k1l2', 'p1q2r3s4t5u6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
