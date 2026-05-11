"""Add is_business_reimbursed to sale_items

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-05-11

When True: the discount on this line is absorbed by the business.
The provider is commissioned on the full pre-discount amount and
pays product fees on the full amount. Client still pays the
discounted price.

When False (default): commission is on the discounted amount;
product fees are still on the full pre-discount amount.
"""
import sqlalchemy as sa
from alembic import op

revision = "i9j0k1l2m3n4"
down_revision = "h8i9j0k1l2m3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sale_items",
        sa.Column(
            "is_business_reimbursed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("sale_items", "is_business_reimbursed")
