"""Showcase upgrade schema extensions: provenance, prompt capture, live watchdog progress, replay/probes/controls.

Revision ID: 0002_showcase_upgrade
Revises: 0001_initial_schema
Create Date: 2026-11-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_showcase_upgrade"
down_revision: str | None = "0001_initial_schema"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    # 1. Extend incidents with trusted provenance, demo run link, captured prompt & live watchdog state
    op.add_column(
        "incidents",
        sa.Column("source_provenance", sa.String(32), nullable=False, server_default="unknown"),
    )
    op.add_column("incidents", sa.Column("demo_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "incidents", sa.Column("sanitized_prompt_json", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "incidents",
        sa.Column(
            "verification_state_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_incidents_source_provenance",
        "incidents",
        "source_provenance IN ('live_alert', 'interactive_demo', 'automated_test', 'recorded_replay', 'unknown')",
    )
    op.create_index("ix_incidents_demo_run_id", "incidents", ["demo_run_id"])
    op.create_index(
        "ix_incidents_provenance_ingested",
        "incidents",
        ["source_provenance", "ingested_at"],
    )

    # 2. Add strictly monotonic sequence_num to incident_events (append-only safe on PostgreSQL)
    op.add_column(
        "incident_events",
        sa.Column(
            "sequence_num",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
    )
    op.create_index("ix_incident_events_sequence_num", "incident_events", ["sequence_num"])

    # 3. Extend runbooks with versioning, upload provenance & async indexing lifecycle
    op.add_column(
        "runbooks",
        sa.Column("version", sa.String(32), nullable=False, server_default="1.0.0"),
    )
    op.add_column(
        "runbooks",
        sa.Column("source", sa.String(64), nullable=False, server_default="seeded_file"),
    )
    op.add_column(
        "runbooks",
        sa.Column(
            "tags_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "runbooks",
        sa.Column("indexing_status", sa.String(24), nullable=False, server_default="READY"),
    )
    op.add_column("runbooks", sa.Column("indexing_error", sa.Text(), nullable=True))
    op.add_column("runbooks", sa.Column("uploaded_by_sub", sa.String(128), nullable=True))
    op.alter_column("runbooks", "embedding", nullable=True)
    op.create_check_constraint(
        "ck_runbooks_indexing_status",
        "runbooks",
        "indexing_status IN ('UPLOADED', 'VALIDATING', 'INDEXING', 'READY', 'FAILED')",
    )

    # 4. Allow non-incident background jobs (RUN_DEMO_SCENARIO, INDEX_RUNBOOK) in outbox_jobs
    op.alter_column("outbox_jobs", "incident_id", nullable=True)
    op.drop_constraint("ck_outbox_jobs_type", "outbox_jobs", type_="check")
    op.create_check_constraint(
        "ck_outbox_jobs_type",
        "outbox_jobs",
        "job_type IN ('TRIAGE_INCIDENT', 'EXECUTE_REMEDIATION', 'VERIFY_RECOVERY', 'RUN_DEMO_SCENARIO', 'INDEX_RUNBOOK')",
    )

    # 5. New showcase tables: demo_runs, business_probe_samples, system_control_flags
    op.create_table(
        "demo_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("target_service", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(192), nullable=False, unique=True),
        sa.Column("actor_sub", sa.String(128), nullable=False),
        sa.Column("actor_email", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "baseline_snapshot_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "narration_state_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'INJECTING_FAULT', 'WAITING_FOR_ALERT', 'ACTIVE', "
            "'AWAITING_APPROVAL', 'VERIFYING', 'COMPLETED', 'ESCALATED', 'FAILED', 'CANCELLED')",
            name="ck_demo_runs_status",
        ),
    )
    op.create_index("ix_demo_runs_target_status", "demo_runs", ["target_service", "status"])
    op.create_index("ix_demo_runs_started_at", "demo_runs", ["started_at"])

    op.create_table(
        "business_probe_samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "demo_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("demo_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_service", sa.String(128), nullable=False),
        sa.Column("endpoint_path", sa.String(256), nullable=False),
        sa.Column("probe_type", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("summary_sanitized", sa.Text(), nullable=False),
        sa.Column(
            "details_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('PASS', 'FAIL', 'DEGRADED', 'UNAVAILABLE')",
            name="ck_business_probes_status",
        ),
    )
    op.create_index(
        "ix_business_probes_svc_checked",
        "business_probe_samples",
        ["target_service", "checked_at"],
    )
    op.create_index(
        "ix_business_probes_incident",
        "business_probe_samples",
        ["incident_id", "checked_at"],
    )

    op.create_table(
        "system_control_flags",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("bool_value", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by_sub", sa.String(128), nullable=False),
        sa.Column("updated_by_email", sa.String(256), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_table("system_control_flags")
    op.drop_table("business_probe_samples")
    op.drop_table("demo_runs")

    op.drop_constraint("ck_outbox_jobs_type", "outbox_jobs", type_="check")
    op.create_check_constraint(
        "ck_outbox_jobs_type",
        "outbox_jobs",
        "job_type IN ('TRIAGE_INCIDENT', 'EXECUTE_REMEDIATION', 'VERIFY_RECOVERY')",
    )
    op.alter_column("outbox_jobs", "incident_id", nullable=False)

    op.drop_constraint("ck_runbooks_indexing_status", "runbooks", type_="check")
    op.execute("DELETE FROM runbooks WHERE embedding IS NULL")
    op.alter_column("runbooks", "embedding", nullable=False)
    op.drop_column("runbooks", "uploaded_by_sub")
    op.drop_column("runbooks", "indexing_error")
    op.drop_column("runbooks", "indexing_status")
    op.drop_column("runbooks", "tags_json")
    op.drop_column("runbooks", "source")
    op.drop_column("runbooks", "version")

    op.drop_index("ix_incident_events_sequence_num", table_name="incident_events")
    op.drop_column("incident_events", "sequence_num")

    op.drop_index("ix_incidents_provenance_ingested", table_name="incidents")
    op.drop_index("ix_incidents_demo_run_id", table_name="incidents")
    op.drop_constraint("ck_incidents_source_provenance", "incidents", type_="check")
    op.drop_column("incidents", "verification_state_json")
    op.drop_column("incidents", "sanitized_prompt_json")
    op.drop_column("incidents", "demo_run_id")
    op.drop_column("incidents", "source_provenance")
