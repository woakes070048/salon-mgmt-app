"""Tenant-configurable acknowledgements + per-request agreement snapshot

Revision ID: x3y4z5a1b2c3
Revises: w2x3y4z5a1b2
Create Date: 2026-05-15

Seeds Salon Lyol's two existing acknowledgements (Waiver and Release,
Cancellations and Refunds Policy) so the public booking form keeps working.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "x3y4z5a1b2c3"
down_revision = "w2x3y4z5a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_acknowledgements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("link_url", sa.String(1000), nullable=True),
        sa.Column("link_text", sa.String(255), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.add_column(
        "appointment_requests",
        sa.Column("acknowledgements_agreed", JSONB, nullable=True),
    )

    # Seed Salon Lyol's two existing acknowledgements
    op.execute("""
        INSERT INTO tenant_acknowledgements (
            tenant_id, title, body_text, link_url, link_text,
            is_required, display_order, is_active
        )
        SELECT
            t.id,
            'SALON LYOL Waiver and Release',
            'I acknowledge that I have read the {link} and understand its contents; and give my voluntary consent to be bound by the same.',
            'https://salonlyol.ca/waiver',
            'SALON LYOL Waiver and Release',
            true, 1, true
        FROM tenants t WHERE t.slug = 'salon-lyol'
    """)
    op.execute("""
        INSERT INTO tenant_acknowledgements (
            tenant_id, title, body_text, link_url, link_text,
            is_required, display_order, is_active
        )
        SELECT
            t.id,
            'SALON LYOL Cancellations and Refunds Policy',
            'I acknowledge that I have read the {link} and understand its contents; and give my voluntary consent with full intention to be bound by the same.',
            'https://salonlyol.ca/cancellation-policy',
            'SALON LYOL Cancellations and Refunds Policy',
            true, 2, true
        FROM tenants t WHERE t.slug = 'salon-lyol'
    """)


def downgrade() -> None:
    op.drop_column("appointment_requests", "acknowledgements_agreed")
    op.drop_table("tenant_acknowledgements")
