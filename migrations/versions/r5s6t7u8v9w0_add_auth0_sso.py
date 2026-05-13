"""Add auth0_sub to users; make password_hash nullable for SSO users

Revision ID: r5s6t7u8v9w0
Revises: z1a2b3c4d5e6
Create Date: 2026-05-12

NOTE: This migration was originally assigned revision a2b3c4d5e6f7 which
collided with an existing revision. It has been reassigned a unique ID.
The DDL was already applied to production prior to this rename, so the
upgrade() is a no-op. A fresh schema build gets this DDL from this file.

"""
import sqlalchemy as sa
from alembic import op

revision = "r5s6t7u8v9w0"
down_revision = "z1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op on existing databases — DDL already applied before this rename.
    # Included here so fresh schema builds get the correct columns.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("users")]
    if "auth0_sub" not in columns:
        op.add_column("users", sa.Column("auth0_sub", sa.String(255), nullable=True))
        op.create_index("ix_users_auth0_sub", "users", ["auth0_sub"], unique=True)
    existing_nullable = next(
        (c["nullable"] for c in inspector.get_columns("users") if c["name"] == "password_hash"),
        True,
    )
    if not existing_nullable:
        op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
    op.drop_index("ix_users_auth0_sub", table_name="users")
    op.drop_column("users", "auth0_sub")
