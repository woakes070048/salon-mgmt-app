"""Add tables and columns for booking recommendation engine

Revision ID: a1b2c3d4e5f6
Revises: c5d6e7f8a9b0
Create Date: 2026-05-05

New tables:
  - tenant_stations
  - service_aliases
  - provider_consent_requests
  - recommendation_log

New columns:
  - services.is_complimentary (bool, NOT NULL DEFAULT false)
  - services.required_station_type (enum tenantstation_type, nullable)
  - tenants.booking_email (text, nullable)
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None

# Enum types — defined once, reused across tables with create_type=False
_station_type = sa.Enum(
    "styling", "colour", "multi_purpose", "processing",
    name="tenantstation_type",
)
_consent_reason = sa.Enum(
    "early_start", "late_end", "processing_overlap",
    name="consent_reason",
)
_consent_status = sa.Enum(
    "pending", "accepted", "declined",
    name="consent_status",
)


def upgrade() -> None:
    # ── tenant_stations (creates tenantstation_type enum) ──────────────────────
    op.create_table(
        "tenant_stations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("station_type", _station_type, nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tenant_stations_tenant_id"), "tenant_stations", ["tenant_id"], unique=False
    )

    # ── service_aliases ────────────────────────────────────────────────────────
    op.create_table(
        "service_aliases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_service_aliases_tenant_id"), "service_aliases", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_service_aliases_service_id"), "service_aliases", ["service_id"], unique=False
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_service_aliases_tenant_lower_alias "
        "ON service_aliases (tenant_id, lower(alias))"
    )

    # ── provider_consent_requests (creates consent_reason, consent_status) ────
    op.create_table(
        "provider_consent_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("appointment_request_id", sa.UUID(), nullable=True),
        sa.Column("reason", _consent_reason, nullable=False),
        sa.Column("proposed_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proposed_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            _consent_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.ForeignKeyConstraint(["appointment_request_id"], ["appointment_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_provider_consent_requests_tenant_id"),
        "provider_consent_requests",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_consent_requests_provider_id"),
        "provider_consent_requests",
        ["provider_id"],
        unique=False,
    )

    # ── recommendation_log ─────────────────────────────────────────────────────
    op.create_table(
        "recommendation_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=True),
        sa.Column("email_message_id", sa.Text(), nullable=True),
        sa.Column("recommendations_json", postgresql.JSONB(), nullable=False),
        sa.Column("chosen_index", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["request_id"], ["appointment_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recommendation_log_tenant_id"), "recommendation_log", ["tenant_id"], unique=False
    )

    # ── New columns on services ────────────────────────────────────────────────
    op.add_column(
        "services",
        sa.Column(
            "is_complimentary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "services",
        sa.Column(
            "required_station_type",
            sa.Enum(
                "styling", "colour", "multi_purpose", "processing",
                name="tenantstation_type",
                create_type=False,
            ),
            nullable=True,
        ),
    )

    # ── New column on tenants ──────────────────────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column("booking_email", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "booking_email")
    op.drop_column("services", "required_station_type")
    op.drop_column("services", "is_complimentary")

    op.drop_index(op.f("ix_recommendation_log_tenant_id"), table_name="recommendation_log")
    op.drop_table("recommendation_log")

    op.drop_index(
        op.f("ix_provider_consent_requests_provider_id"),
        table_name="provider_consent_requests",
    )
    op.drop_index(
        op.f("ix_provider_consent_requests_tenant_id"),
        table_name="provider_consent_requests",
    )
    op.drop_table("provider_consent_requests")

    op.drop_index(op.f("ix_service_aliases_service_id"), table_name="service_aliases")
    op.drop_index(op.f("ix_service_aliases_tenant_id"), table_name="service_aliases")
    op.execute("DROP INDEX IF EXISTS uq_service_aliases_tenant_lower_alias")
    op.drop_table("service_aliases")

    op.drop_index(op.f("ix_tenant_stations_tenant_id"), table_name="tenant_stations")
    op.drop_table("tenant_stations")

    op.execute("DROP TYPE IF EXISTS consent_status")
    op.execute("DROP TYPE IF EXISTS consent_reason")
    op.execute("DROP TYPE IF EXISTS tenantstation_type")
