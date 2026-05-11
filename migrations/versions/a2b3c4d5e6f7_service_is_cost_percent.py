"""service is_cost_percent flag

Revision ID: a2b3c4d5e6f7
Revises: z1a2b3c4d5e6
Create Date: 2026-05-11

"""
from alembic import op
import sqlalchemy as sa

revision = 'a2b3c4d5e6f7'
down_revision = 'z1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('services', sa.Column('is_cost_percent', sa.Boolean(), nullable=False, server_default='false'))
    # Existing colour-category services become percent-based
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
