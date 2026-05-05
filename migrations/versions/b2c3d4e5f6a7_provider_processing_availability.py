"""Add provider-during-processing availability settings

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-05

New columns:
  - tenants.providers_available_during_processing (bool NOT NULL DEFAULT true)
  - providers.available_during_processing (bool nullable — null inherits tenant default)
"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "providers_available_during_processing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "providers",
        sa.Column(
            "available_during_processing",
            sa.Boolean(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("providers", "available_during_processing")
    op.drop_column("tenants", "providers_available_during_processing")
