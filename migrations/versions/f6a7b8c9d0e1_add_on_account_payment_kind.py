"""Add on_account payment method kind

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-07

"""
import uuid
import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None

# ALTER TYPE ... ADD VALUE cannot run inside a transaction in PostgreSQL.
# Setting this flag tells Alembic to run this migration outside a transaction.
def upgrade() -> None:
    # Must commit any open transaction before adding enum value
    op.execute("COMMIT")
    op.execute("ALTER TYPE payment_method_kind ADD VALUE IF NOT EXISTS 'on_account'")

    # Seed an "On Account" payment method for every active tenant
    op.execute("""
        INSERT INTO tenant_payment_methods (id, tenant_id, code, label, kind, is_active, sort_order, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            id,
            'on_account',
            'On Account',
            'on_account',
            true,
            90,
            NOW(),
            NOW()
        FROM tenants
        WHERE is_active = true
          AND id NOT IN (
              SELECT tenant_id FROM tenant_payment_methods WHERE code = 'on_account'
          )
    """)


def downgrade() -> None:
    op.execute("DELETE FROM tenant_payment_methods WHERE code = 'on_account'")
    # PostgreSQL does not support removing enum values — manual cleanup required
