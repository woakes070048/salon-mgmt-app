"""Add receipt_number to sales

Revision ID: v1w2x3y4z5a1
Revises: u0v1w2x3y4z5
Create Date: 2026-05-14

Idempotent: safe to re-run if a prior failed deploy partially applied
changes. We use raw SQL with IF NOT EXISTS / WHERE IS NULL guards so the
migration completes cleanly even when called multiple times.
"""
from alembic import op

revision = "v1w2x3y4z5a1"
down_revision = "u0v1w2x3y4z5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sequence — IF NOT EXISTS is safe on every Postgres version we run.
    op.execute("CREATE SEQUENCE IF NOT EXISTS receipt_number_seq START 1001")

    # Add column only if it isn't already there. A failed prior deploy may
    # have created it before crashing; we don't want to error on retry.
    op.execute(
        "ALTER TABLE sales ADD COLUMN IF NOT EXISTS receipt_number INTEGER"
    )

    # Backfill any rows that don't yet have a number.
    op.execute(
        "UPDATE sales SET receipt_number = nextval('receipt_number_seq') "
        "WHERE receipt_number IS NULL"
    )

    # Set default for future inserts. SET DEFAULT is idempotent.
    op.execute(
        "ALTER TABLE sales ALTER COLUMN receipt_number "
        "SET DEFAULT nextval('receipt_number_seq')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sales DROP COLUMN IF EXISTS receipt_number")
    op.execute("DROP SEQUENCE IF EXISTS receipt_number_seq")
