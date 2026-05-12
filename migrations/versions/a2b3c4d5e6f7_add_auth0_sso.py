"""Add auth0_sub to users; make password_hash nullable for SSO users

Revision ID: a2b3c4d5e6f7
Revises: z1a2b3c4d5e6
Create Date: 2026-05-12

"""
import sqlalchemy as sa
from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "z1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth0_sub", sa.String(255), nullable=True))
    op.create_index("ix_users_auth0_sub", "users", ["auth0_sub"], unique=True)
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(255), nullable=False)
    op.drop_index("ix_users_auth0_sub", table_name="users")
    op.drop_column("users", "auth0_sub")
