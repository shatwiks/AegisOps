"""Initial AegisOps CMDB, incidents, hybrid RAG, approvals, execution, and outbox schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-17
"""

from __future__ import annotations

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("namespace", sa.String(128), nullable=False),
        sa.Column("cluster", sa.String(128), nullable=False),
        sa.Column("asset_type", sa.String(64), nullable=False),
        sa.Column("criticality", sa.String(32), nullable=False),
        sa.Column("owner_team", sa.String(128), nullable=False),
        sa.Column("stateless_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("known_good_image", sa.String(256), nullable=True),
        sa.Column("k8s_deployment_name", sa.String(128), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("cluster", "namespace", "name", name="uq_assets_cluster_ns_name"),
        sa.CheckConstraint(
            "criticality IN ('TIER_1_CRITICAL', 'TIER_2_HIGH', 'TIER_3_STANDARD', 'TIER_4_LOW')",
            name="ck_assets_criticality",
        ),
    )
    op.create_index("ix_assets_slug", "assets", ["slug"])

    op.create_table(
        "asset_dependencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dependency_type", sa.String(64), nullable=False),
        sa.Column("description", sa.String(256), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "source_asset_id",
            "target_asset_id",
            "dependency_type",
            name="uq_asset_dep_src_tgt_type",
        ),
        sa.CheckConstraint("source_asset_id <> target_asset_id", name="ck_asset_dep_no_self_edge"),
    )
    op.create_index("ix_asset_dep_source", "asset_dependencies", ["source_asset_id"])
    op.create_index("ix_asset_dep_target", "asset_dependencies", ["target_asset_id"])

    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dedup_key", sa.String(256), nullable=False),
        sa.Column("alert_fingerprint", sa.String(128), nullable=False),
        sa.Column("alertname", sa.String(128), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("summary_sanitized", sa.Text(), nullable=False),
        sa.Column(
            "primary_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("unknown_asset_identifier", sa.String(256), nullable=True),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column(
            "severity_explanation_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("state", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("diagnosis_json", postgresql.JSONB(), nullable=True),
        sa.Column("proposed_playbook_id", sa.String(128), nullable=True),
        sa.Column("proposed_parameters_json", postgresql.JSONB(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("refusal_reason", sa.Text(), nullable=True),
        sa.Column(
            "redaction_stats_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("fault_onset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("triaged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mutated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "state IN ('OPEN', 'TRIAGING', 'READY_TO_REMEDIATE', 'AWAITING_APPROVAL', "
            "'ESCALATED', 'REMEDIATING', 'VERIFYING', 'RESOLVED', 'FAILED')",
            name="ck_incidents_canonical_state",
        ),
        sa.CheckConstraint("severity IN ('P1', 'P2', 'P3', 'P4')", name="ck_incidents_severity"),
    )
    op.create_index("ix_incidents_dedup_key", "incidents", ["dedup_key"])
    op.create_index(
        "ix_incidents_active_dedup_key",
        "incidents",
        ["dedup_key"],
        unique=True,
        postgresql_where=sa.text("state NOT IN ('RESOLVED', 'FAILED')"),
    )
    op.create_index("ix_incidents_state_created", "incidents", ["state", "ingested_at"])

    op.create_table(
        "incident_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("from_state", sa.String(32), nullable=True),
        sa.Column("to_state", sa.String(32), nullable=True),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column(
            "details_sanitized_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_incident_events_inc_created", "incident_events", ["incident_id", "created_at"]
    )

    op.create_table(
        "runbooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(128), nullable=False, unique=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("service_slug", sa.String(128), nullable=False),
        sa.Column("symptoms", sa.Text(), nullable=False),
        sa.Column(
            "evidence_requirements_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "applicability_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "preconditions_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("risk_tier", sa.String(16), nullable=False),
        sa.Column("permitted_playbook_id", sa.String(128), nullable=True),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("verification_steps", sa.Text(), nullable=False),
        sa.Column("escalation_guidance", sa.Text(), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("search_tsv", postgresql.TSVECTOR(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.VECTOR(768), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("embedding_digest", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("doc_type IN ('RUNBOOK', 'POSTMORTEM')", name="ck_runbooks_doc_type"),
        sa.CheckConstraint("risk_tier IN ('LOW', 'HIGH')", name="ck_runbooks_risk_tier"),
    )
    op.create_index("ix_runbooks_service_slug", "runbooks", ["service_slug"])
    op.create_index("ix_runbooks_search_tsv", "runbooks", ["search_tsv"], postgresql_using="gin")
    op.create_index(
        "ix_runbooks_embedding_hnsw",
        "runbooks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("playbook_id", sa.String(128), nullable=False),
        sa.Column("playbook_version", sa.String(32), nullable=False),
        sa.Column("parameters_hash", sa.String(128), nullable=False),
        sa.Column(
            "parameters_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("target_asset_slug", sa.String(128), nullable=False),
        sa.Column("target_k8s_uid", sa.String(128), nullable=False),
        sa.Column("target_resource_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by_sub", sa.String(128), nullable=True),
        sa.Column("decided_by_email", sa.String(256), nullable=True),
        sa.Column("decided_by_role", sa.String(64), nullable=True),
        sa.Column("totp_timecode_used", sa.BigInteger(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'DENIED', 'EXPIRED', 'CONSUMED', 'INVALIDATED')",
            name="ck_approval_requests_status",
        ),
    )
    op.create_index(
        "ix_approval_requests_incident_status", "approval_requests", ["incident_id", "status"]
    )

    op.create_table(
        "execution_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approval_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("approval_requests.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(192), nullable=False, unique=True),
        sa.Column("playbook_id", sa.String(128), nullable=False),
        sa.Column("playbook_version", sa.String(32), nullable=False),
        sa.Column(
            "parameters_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("target_cluster", sa.String(128), nullable=False),
        sa.Column("target_namespace", sa.String(128), nullable=False),
        sa.Column("target_deployment", sa.String(128), nullable=False),
        sa.Column("lock_token", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="CLAIMED"),
        sa.Column(
            "before_state_sanitized_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("after_state_sanitized_json", postgresql.JSONB(), nullable=True),
        sa.Column("k8s_response_sanitized_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_message_sanitized", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('CLAIMED', 'PRECHECKED', 'MUTATING', 'ROLLOUT_WAITING', "
            "'SUCCEEDED', 'RECONCILED_SUCCEEDED', 'SKIPPED_LOCK_CONTENTION', "
            "'ABORTED_LEASE_LOST', 'FAILED')",
            name="ck_execution_attempts_status",
        ),
    )
    op.create_index(
        "ix_execution_attempts_incident", "execution_attempts", ["incident_id", "started_at"]
    )

    op.create_table(
        "audit_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_sub", sa.String(128), nullable=False),
        sa.Column("actor_role", sa.String(64), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("policy_decision", sa.String(64), nullable=False),
        sa.Column("before_state_json", postgresql.JSONB(), nullable=True),
        sa.Column("after_state_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "details_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_audit_records_incident_created", "audit_records", ["incident_id", "created_at"]
    )

    op.create_table(
        "outbox_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "incident_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("incidents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("dedup_job_key", sa.String(256), nullable=False, unique=True),
        sa.Column(
            "payload_sanitized_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_error_sanitized", sa.Text(), nullable=True),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "job_type IN ('TRIAGE_INCIDENT', 'EXECUTE_REMEDIATION', 'VERIFY_RECOVERY')",
            name="ck_outbox_jobs_type",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CLAIMED', 'COMPLETED', 'DEAD_LETTER')",
            name="ck_outbox_jobs_status",
        ),
    )
    op.create_index("ix_outbox_jobs_claimable", "outbox_jobs", ["status", "available_at"])

    op.create_table(
        "user_totp_secrets",
        sa.Column("user_sub", sa.String(128), primary_key=True),
        sa.Column("user_email", sa.String(256), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_used_timecode", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )

    # Append-only trigger enforcing immutability of audit_records and incident_events
    op.execute(
        """
        CREATE OR REPLACE FUNCTION aegisops_prevent_append_only_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Table % is append-only; UPDATE and DELETE are prohibited', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_records_append_only
        BEFORE UPDATE OR DELETE ON audit_records
        FOR EACH ROW EXECUTE FUNCTION aegisops_prevent_append_only_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_incident_events_append_only
        BEFORE UPDATE OR DELETE ON incident_events
        FOR EACH ROW EXECUTE FUNCTION aegisops_prevent_append_only_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_incident_events_append_only ON incident_events")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_records_append_only ON audit_records")
    op.execute("DROP FUNCTION IF EXISTS aegisops_prevent_append_only_mutation()")
    op.drop_table("user_totp_secrets")
    op.drop_table("outbox_jobs")
    op.drop_table("audit_records")
    op.drop_table("execution_attempts")
    op.drop_table("approval_requests")
    op.drop_table("runbooks")
    op.drop_table("incident_events")
    op.drop_table("incidents")
    op.drop_table("asset_dependencies")
    op.drop_table("assets")
