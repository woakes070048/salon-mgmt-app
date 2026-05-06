"""Add inbound email fields to appointment_requests for reply threading.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-06

New columns on appointment_requests:
  - inbound_message_id  TEXT nullable — RFC 2822 Message-ID from the original
                        inbound email; used to set In-Reply-To when sending a
                        staff reply so the client sees it as one thread.
  - inbound_raw_body    TEXT nullable — plain-text body of the original email;
                        displayed in the booking request panel so staff can read
                        the original message without leaving the app.
"""

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointment_requests",
        sa.Column("inbound_message_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "appointment_requests",
        sa.Column("inbound_raw_body", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("appointment_requests", "inbound_raw_body")
    op.drop_column("appointment_requests", "inbound_message_id")
