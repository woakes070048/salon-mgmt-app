"""merge_heads_service_id

Revision ID: 40922e618b16
Revises: a1ea45b5edac, y4z5a1b2c3d4
Create Date: 2026-05-17 10:33:44.359304

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '40922e618b16'
down_revision: Union[str, None] = ('a1ea45b5edac', 'y4z5a1b2c3d4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
