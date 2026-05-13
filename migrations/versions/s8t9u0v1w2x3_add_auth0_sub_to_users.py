"""Add auth0_sub column and make password_hash nullable

Revision ID: s8t9u0v1w2x3
Revises: q3r4s5t6u7v8
Create Date: 2026-05-13

The auth0_sso migration was lost in the duplicate revision ID cleanup.
This migration applies the DDL idempotently.

"""
import sqlalchemy as sa
from alembic import op

revision = "s8t9u0v1w2x3"
down_revision = "q3r4s5t6u7v8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {c["name"]: c for c in inspector.get_columns("users")}

    if "auth0_sub" not in columns:
        op.add_column("users", sa.Column("auth0_sub", sa.String(255), nullable=True))
        op.create_index("ix_users_auth0_sub", "users", ["auth0_sub"], unique=True)

    if not columns.get("password_hash", {}).get("nullable", True):
        op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
    op.drop_index("ix_users_auth0_sub", table_name="users")
    op.drop_column("users", "auth0_sub")
