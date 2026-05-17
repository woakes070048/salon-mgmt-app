"""Add service_id to sale_items for direct service lookup without appointment_item join

Revision ID: a1b2c3d4e5f6
Revises: z1a2b3c4d5e6
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'a1b2c3d4e5f6'
down_revision = 'z1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sale_items', sa.Column(
        'service_id',
        UUID(as_uuid=True),
        sa.ForeignKey('services.id', ondelete='SET NULL'),
        nullable=True,
    ))
    op.create_index('ix_sale_items_service_id', 'sale_items', ['service_id'])


def downgrade() -> None:
    op.drop_index('ix_sale_items_service_id', 'sale_items')
    op.drop_column('sale_items', 'service_id')
