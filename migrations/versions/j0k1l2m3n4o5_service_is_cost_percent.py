"""service is_cost_percent flag

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-05-11

"""
from alembic import op
import sqlalchemy as sa

revision = 'j0k1l2m3n4o5'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('services', sa.Column('is_cost_percent', sa.Boolean(), nullable=False, server_default='false'))
    op.execute("""
        UPDATE services
        SET is_cost_percent = true
        WHERE category_id IN (
            SELECT id FROM service_categories
            WHERE LOWER(name) LIKE '%colour%'
               OR LOWER(name) LIKE '%color%'
               OR LOWER(name) LIKE '%colouring%'
        )
    """)


def downgrade() -> None:
    op.drop_column('services', 'is_cost_percent')
