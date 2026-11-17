# AegisOps Data Model

> **Status:** Implemented and verified via Alembic (`0001_initial_schema.py` -> `0002_showcase_upgrade.py`) on PostgreSQL 16 + `pgvector` across all `13` tables in `backend/app/models/entities.py`.

## 1. Core Design Rules
- **Vector Column & Index**: `runbooks.embedding` (`VECTOR(768)`, nullable while `UPLOADED`/`VALIDATING`/`INDEXING`/`FAILED`) matches `nomic-embed-text:latest` (`768` dimensions), indexed with `pgvector` HNSW (`ix_runbooks_embedding_hnsw`, `vector_cosine_ops`, `m=16`, `ef_construction=64`), paired with `embedding_model` and `embedding_digest`. Only `indexing_status = 'READY' AND embedding IS NOT NULL` rows are eligible for Hybrid RAG search (`retriever.py`).
- **Lexical Column & Index**: `runbooks.search_tsv` `TSVECTOR` column indexed with GIN (`ix_runbooks_search_tsv`) for `websearch_to_tsquery` + `ts_rank_cd`.
- **Directed Edges (`asset_dependencies`)**: `source_asset_id -> target_asset_id` means `source depends_on target`, enforced by `ck_asset_dep_no_self_edge` and `uq_asset_dep_src_tgt_type`.
- **Append-Only Governance & Monotonic Events**: `incident_events` and `audit_records` prohibit `DELETE`/`UPDATE` via PostgreSQL triggers (`trg_incident_events_append_only`, `trg_audit_records_append_only`). `incident_events.sequence_num` (`BIGINT IDENTITY`) enables monotonic SSE `after_seq` catch-up.
- **Deduplication & Provenance**: Partial unique index `ix_incidents_active_dedup_key` on `incidents(dedup_key) WHERE state NOT IN ('RESOLVED', 'FAILED')`; webhooks use literal `text("state NOT IN ('RESOLVED', 'FAILED')")` (DEC-010). `incidents.source_provenance` distinguishes `live_alert`, `interactive_demo`, `automated_test`, `recorded_replay`, and `unknown`.

## 2. Table Summary (`backend/migrations/versions/0001_initial_schema.py` + `0002_showcase_upgrade.py`)
| Table | Purpose | Key Constraints & Indexes |
|---|---|---|
| `assets` | CMDB inventory of cluster workloads, dependencies & policies | `uq_assets_cluster_ns_name`, `ck_assets_criticality`, `ix_assets_slug` |
| `asset_dependencies` | Directed service dependency edges (`source depends_on target`) | `ck_asset_dep_no_self_edge`, `uq_asset_dep_src_tgt_type`, `ix_asset_dep_{source,target}` |
| `incidents` | Sanitized incident ledger, provenance, captured prompt record, verification progress, severity & timestamps | `ck_incidents_canonical_state`, `ck_incidents_severity`, `ck_incidents_source_provenance`, `ix_incidents_active_dedup_key`, `ix_incidents_provenance_ingested` |
| `incident_events` | Immutable state-transition & timeline log with monotonic `sequence_num` | `trg_incident_events_append_only`, `ix_incident_events_inc_created`, `ix_incident_events_sequence_num`, FK `RESTRICT` |
| `runbooks` | Indexed SRE runbooks & synthetic postmortems + upload lifecycle (`UPLOADED`..`READY`/`FAILED`) | `ck_runbooks_doc_type`, `ck_runbooks_risk_tier`, `ck_runbooks_indexing_status`, `ix_runbooks_search_tsv`, `ix_runbooks_embedding_hnsw` |
| `approval_requests` | Action-bound step-up approval records (`target_k8s_uid`, `target_resource_version`, `parameters_hash`) | `ck_approval_requests_status`, `ix_approval_requests_incident_status` |
| `execution_attempts` | Idempotent K8s mutation records, lease tokens, pre/after state diffs | `idempotency_key` unique, `ck_execution_attempts_status`, `ix_execution_attempts_incident` |
| `audit_records` | Compliance & policy decision ledger (append-only trigger protected) | `trg_audit_records_append_only`, `ix_audit_records_incident_created` |
| `outbox_jobs` | Durable PostgreSQL `SKIP LOCKED` queue (`TRIAGE_INCIDENT`, `EXECUTE_REMEDIATION`, `VERIFY_RECOVERY`, `RUN_DEMO_SCENARIO`, `INDEX_RUNBOOK`; `incident_id` nullable for showcase/index jobs) | `dedup_job_key` unique, `ck_outbox_jobs_{type,status}`, `ix_outbox_jobs_claimable` |
| `user_totp_secrets` | Fernet-encrypted MFA seeds, replay `last_used_timecode`, lockout counters | PK `user_sub`, `failed_attempts`, `locked_until` |
| `demo_runs` | Durable Chaos Lab orchestration tracking status, target lock, baseline snapshot & Tour narration | `ck_demo_runs_status`, unique `idempotency_key`, `ix_demo_runs_target_status`, `ix_demo_runs_started_at` |
| `business_probe_samples` | Sanitized semantic business transaction probe results correlated to runs/incidents | `ck_business_probes_status`, `ix_business_probes_svc_checked`, `ix_business_probes_incident` |
| `system_control_flags` | Backend-enforced operator control switches (`automation_paused`) | PK `key` |
