"""Drop provider-level product fee columns (fees now derived from service.default_cost)

Revision ID: a1b2c3d4e5f6
Revises: z1a2b3c4d5e6
Create Date: 2026-05-09

"""
from alembic import op

revision = "p1q2r3s4t5u6"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("providers", "product_fee_styling_flat")
    op.drop_column("providers", "product_fee_colour_pct")


def downgrade() -> None:
    import sqlalchemy as sa
    op.add_column("providers", sa.Column("product_fee_styling_flat", sa.Numeric(10, 2), nullable=True))
    op.add_column("providers", sa.Column("product_fee_colour_pct", sa.Numeric(5, 2), nullable=True))
