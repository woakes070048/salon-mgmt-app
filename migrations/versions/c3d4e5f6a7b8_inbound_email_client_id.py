"""P3-7: Add client_id to appointment_requests for inbound email ingestion.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7, b2c3d4e5f6g7
Create Date: 2026-05-05

New columns:
  - appointment_requests.client_id (UUID, nullable FK → clients.id)
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = ("b2c3d4e5f6a7", "b2c3d4e5f6g7")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointment_requests",
        sa.Column("client_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_appointment_requests_client_id",
        "appointment_requests",
        "clients",
        ["client_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_appointment_requests_client_id"),
        "appointment_requests",
        ["client_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_appointment_requests_client_id"),
        table_name="appointment_requests",
    )
    op.drop_constraint(
        "fk_appointment_requests_client_id",
        "appointment_requests",
        type_="foreignkey",
    )
    op.drop_column("appointment_requests", "client_id")
