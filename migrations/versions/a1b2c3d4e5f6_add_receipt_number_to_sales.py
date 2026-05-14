"""Add receipt_number to sales

Revision ID: a1b2c3d4e5f6
Revises: z1a2b3c4d5e6
Create Date: 2026-05-14

"""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "z1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS receipt_number_seq START 1001")
    op.add_column(
        "sales",
        sa.Column(
            "receipt_number",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("nextval('receipt_number_seq')"),
        ),
    )
    # Backfill any existing rows
    op.execute(
        "UPDATE sales SET receipt_number = nextval('receipt_number_seq') "
        "WHERE receipt_number IS NULL"
    )


def downgrade() -> None:
    op.drop_column("sales", "receipt_number")
    op.execute("DROP SEQUENCE IF EXISTS receipt_number_seq")
