"""SQLAlchemy 2.0 ORM definitions for AegisOps CMDB, incidents, RAG, approvals, and outbox."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

CANONICAL_INCIDENT_STATES: tuple[str, ...] = (
    "OPEN",
    "TRIAGING",
    "READY_TO_REMEDIATE",
    "AWAITING_APPROVAL",
    "ESCALATED",
    "REMEDIATING",
    "VERIFYING",
    "RESOLVED",
    "FAILED",
)

SOURCE_PROVENANCES: tuple[str, ...] = (
    "live_alert",
    "interactive_demo",
    "automated_test",
    "recorded_replay",
    "unknown",
)

RUNBOOK_INDEXING_STATUSES: tuple[str, ...] = (
    "UPLOADED",
    "VALIDATING",
    "INDEXING",
    "READY",
    "FAILED",
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base declarative class."""


class Asset(Base):
    """CMDB service, database, cache, or infrastructure asset."""

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("cluster", "namespace", "name", name="uq_assets_cluster_ns_name"),
        CheckConstraint(
            "criticality IN ('TIER_1_CRITICAL', 'TIER_2_HIGH', 'TIER_3_STANDARD', 'TIER_4_LOW')",
            name="ck_assets_criticality",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    cluster: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False)
    criticality: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_team: Mapped[str] = mapped_column(String(128), nullable=False)
    stateless_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    known_good_image: Mapped[str | None] = mapped_column(String(256), nullable=True)
    k8s_deployment_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AssetDependency(Base):
    """Directed CMDB dependency: source_asset depends_on target_asset."""

    __tablename__ = "asset_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "source_asset_id",
            "target_asset_id",
            "dependency_type",
            name="uq_asset_dep_src_tgt_type",
        ),
        CheckConstraint("source_asset_id <> target_asset_id", name="ck_asset_dep_no_self_edge"),
        Index("ix_asset_dep_source", "source_asset_id"),
        Index("ix_asset_dep_target", "target_asset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    target_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    dependency_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=False, default="")


class Incident(Base):
    """Authoritative incident record with lifecycle timestamps and optimistic lock."""

    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "state IN ('OPEN', 'TRIAGING', 'READY_TO_REMEDIATE', 'AWAITING_APPROVAL', "
            "'ESCALATED', 'REMEDIATING', 'VERIFYING', 'RESOLVED', 'FAILED')",
            name="ck_incidents_canonical_state",
        ),
        CheckConstraint("severity IN ('P1', 'P2', 'P3', 'P4')", name="ck_incidents_severity"),
        CheckConstraint(
            "source_provenance IN ('live_alert', 'interactive_demo', 'automated_test', 'recorded_replay', 'unknown')",
            name="ck_incidents_source_provenance",
        ),
        Index(
            "ix_incidents_active_dedup_key",
            "dedup_key",
            unique=True,
            postgresql_where=text("state NOT IN ('RESOLVED', 'FAILED')"),
        ),
        Index("ix_incidents_state_created", "state", "ingested_at"),
        Index("ix_incidents_provenance_ingested", "source_provenance", "ingested_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dedup_key: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    alert_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    alertname: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary_sanitized: Mapped[str] = mapped_column(Text, nullable=False)
    primary_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    unknown_asset_identifier: Mapped[str | None] = mapped_column(String(256), nullable=True)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    severity_explanation_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")

    diagnosis_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    proposed_playbook_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    proposed_parameters_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    refusal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    redaction_stats_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    source_provenance: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", server_default="unknown"
    )
    demo_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    sanitized_prompt_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    verification_state_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    fault_onset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mutated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_recovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    primary_asset: Mapped[Asset | None] = relationship("Asset")


class IncidentEvent(Base):
    """Append-only timeline events for an incident (protected from DELETE)."""

    __tablename__ = "incident_events"
    __table_args__ = (
        Index("ix_incident_events_inc_created", "incident_id", "created_at"),
        Index("ix_incident_events_sequence_num", "sequence_num"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sequence_num: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), nullable=False
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    details_sanitized_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Runbook(Base):
    """SRE runbook or synthetic postmortem with FTS TSVECTOR and 768-dim pgvector."""

    __tablename__ = "runbooks"
    __table_args__ = (
        CheckConstraint("doc_type IN ('RUNBOOK', 'POSTMORTEM')", name="ck_runbooks_doc_type"),
        CheckConstraint("risk_tier IN ('LOW', 'HIGH')", name="ck_runbooks_risk_tier"),
        CheckConstraint(
            "indexing_status IN ('UPLOADED', 'VALIDATING', 'INDEXING', 'READY', 'FAILED')",
            name="ck_runbooks_indexing_status",
        ),
        Index("ix_runbooks_search_tsv", "search_tsv", postgresql_using="gin"),
        Index(
            "ix_runbooks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    service_slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    symptoms: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_requirements_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    applicability_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    preconditions_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    risk_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    permitted_playbook_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    verification_steps: Mapped[str] = mapped_column(Text, nullable=False)
    escalation_guidance: Mapped[str] = mapped_column(Text, nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    search_tsv: Mapped[Any] = mapped_column(TSVECTOR, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(768), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="1.0.0", server_default="1.0.0"
    )
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="seeded_file", server_default="seeded_file"
    )
    tags_json: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    indexing_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="READY", server_default="READY"
    )
    indexing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_sub: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class ApprovalRequest(Base):
    """Action-bound, single-use, short-lived high-risk MFA approval record."""

    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'DENIED', 'EXPIRED', 'CONSUMED', 'INVALIDATED')",
            name="ck_approval_requests_status",
        ),
        Index("ix_approval_requests_incident_status", "incident_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    playbook_id: Mapped[str] = mapped_column(String(128), nullable=False)
    playbook_version: Mapped[str] = mapped_column(String(32), nullable=False)
    parameters_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    target_asset_slug: Mapped[str] = mapped_column(String(128), nullable=False)
    target_k8s_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    target_resource_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by_sub: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decided_by_email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    decided_by_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_timecode_used: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExecutionAttempt(Base):
    """Durable ledger of Kubernetes remediation attempts for crash/timeout reconciliation."""

    __tablename__ = "execution_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CLAIMED', 'PRECHECKED', 'MUTATING', 'ROLLOUT_WAITING', "
            "'SUCCEEDED', 'RECONCILED_SUCCEEDED', 'SKIPPED_LOCK_CONTENTION', "
            "'ABORTED_LEASE_LOST', 'FAILED')",
            name="ck_execution_attempts_status",
        ),
        Index("ix_execution_attempts_incident", "incident_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="RESTRICT"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(192), unique=True, nullable=False)
    playbook_id: Mapped[str] = mapped_column(String(128), nullable=False)
    playbook_version: Mapped[str] = mapped_column(String(32), nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    target_cluster: Mapped[str] = mapped_column(String(128), nullable=False)
    target_namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    target_deployment: Mapped[str] = mapped_column(String(128), nullable=False)
    lock_token: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CLAIMED")
    before_state_sanitized_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    after_state_sanitized_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    k8s_response_sanitized_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message_sanitized: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditRecord(Base):
    """Immutable append-only audit log (protected against DELETE/UPDATE by DB trigger)."""

    __tablename__ = "audit_records"
    __table_args__ = (Index("ix_audit_records_incident_created", "incident_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_sub: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_decision: Mapped[str] = mapped_column(String(64), nullable=False)
    before_state_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_state_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class OutboxJob(Base):
    """Transactional outbox jobs claimed via SELECT FOR UPDATE SKIP LOCKED."""

    __tablename__ = "outbox_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('TRIAGE_INCIDENT', 'EXECUTE_REMEDIATION', 'VERIFY_RECOVERY', "
            "'RUN_DEMO_SCENARIO', 'INDEX_RUNBOOK')",
            name="ck_outbox_jobs_type",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'CLAIMED', 'COMPLETED', 'DEAD_LETTER')",
            name="ck_outbox_jobs_status",
        ),
        Index("ix_outbox_jobs_claimable", "status", "available_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=True
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dedup_job_key: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    payload_sanitized_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    last_error_sanitized: Mapped[str | None] = mapped_column(Text, nullable=True)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserTotpSecret(Base):
    """Per-user Fernet-encrypted TOTP secret and replay/rate-limit state."""

    __tablename__ = "user_totp_secrets"

    user_sub: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_email: Mapped[str] = mapped_column(String(256), nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_used_timecode: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



class DemoRun(Base):
    """Durable showcase scenario orchestration run with conflict exclusion & tour narration."""

    __tablename__ = "demo_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED', 'INJECTING_FAULT', 'WAITING_FOR_ALERT', 'ACTIVE', "
            "'AWAITING_APPROVAL', 'VERIFYING', 'COMPLETED', 'ESCALATED', 'FAILED', 'CANCELLED')",
            name="ck_demo_runs_status",
        ),
        Index("ix_demo_runs_target_status", "target_service", "status"),
        Index("ix_demo_runs_started_at", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    target_service: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(192), unique=True, nullable=False)
    actor_sub: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_email: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )
    baseline_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    narration_state_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class BusinessProbeSample(Base):
    """Sanitized semantic business transaction check history correlated to scenarios/incidents."""

    __tablename__ = "business_probe_samples"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PASS', 'FAIL', 'DEGRADED', 'UNAVAILABLE')",
            name="ck_business_probes_status",
        ),
        Index("ix_business_probes_svc_checked", "target_service", "checked_at"),
        Index("ix_business_probes_incident", "incident_id", "checked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )
    demo_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("demo_runs.id", ondelete="SET NULL"), nullable=True
    )
    target_service: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint_path: Mapped[str] = mapped_column(String(256), nullable=False)
    probe_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_sanitized: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class SystemControlFlag(Base):
    """Backend-enforced operator control switches (e.g., pause automation)."""

    __tablename__ = "system_control_flags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    bool_value: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by_sub: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_by_email: Mapped[str] = mapped_column(String(256), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
