# AegisOps — Exhaustive Code, Architecture & Implementation Report

> **Snapshot Date:** `2026-11-19T03:50:00+05:30`  
> **Repository:** `https://github.com/shatwiks/AegisOps` (`main`, `224` tracked files before report update)  
> **Verification Baseline:** Core Phases `0–5` (`VERIFIED`), Showcase Phases `00–07` (`VERIFIED`), `65/65` Pytest (`0` failed, `0` skipped), Ruff clean, Mypy `50` source files clean, Vite `68` modules built, `15/15` docs verified, GitHub Actions CI `ubuntu-24.04` green.  
> **Disclaimer:** AegisOps is an independent engineering demonstration operating strictly on synthetic healthcare workloads inside a local `kind` Kubernetes cluster (`kind-aegisops-local`). It implies no affiliation with any healthcare organization and carries no HIPAA/HITRUST compliance or clinical production readiness.

---

## 1. What AegisOps Is & How It Works (Big Picture to Fine Details)

**AegisOps** is a full-stack **Autonomous AIOps Control Plane, CMDB Blast-Radius Analyzer, and Self-Healing Kubernetes Operator**. Instead of letting an LLM hallucinate commands against production pods or leak sensitive user fields to an external API, AegisOps separates responsibilities into hard, fail-closed layers:

1. **Telemetry & Alert Boundary**: Three custom Python FastAPI demo microservices (`eligibility-api`, `claims-processor`, `provider-directory`) run inside `kind-aegisops-local` and emit Prometheus metrics (`http_requests_total`, `db_pool_active_connections`, `simulated_memory_allocated_bytes`, `http_recent_p95_latency_seconds`, etc.) plus OpenTelemetry spans via OTel Collector (`55317/55318`). Prometheus (`59090`) evaluates traffic-guarded rules and routes alerts through Alertmanager (`59093`).
2. **Fail-Closed Edge Scrubber & Durable Ingestion**: `POST /api/v1/webhooks/alertmanager` verifies HMAC-SHA256 + Bearer credentials, blocks SSRF URLs, strips unallowlisted keys, and runs `scrubber.py` regex + recursive AST PII redaction *before* logging or persisting anything. One PostgreSQL transaction inserts the deduplicated `Incident`, immutable `IncidentEvent`, `AuditRecord`, and `OutboxJob(TRIAGE_INCIDENT)`.
3. **CMDB Blast-Radius & Severity Scoring**: `cmdb/graph.py` traverses directed dependency edges (`source depends_on target`) safely with cycle detection to list impacted downstream consumers and assign a deterministic `P1–P4` severity with an explicit JSON explanation.
4. **Hybrid RAG & Schema-Constrained Local AI**: `worker/runner.py` claims `outbox_jobs` via PostgreSQL `FOR UPDATE SKIP LOCKED`, embeds scrubbed incident text using local Ollama `nomic-embed-text:latest` (`768` dims), queries PostgreSQL `pgvector` HNSW cosine similarity + `tsvector` GIN full-text search fused by Reciprocal Rank Fusion (`k=60`), and calls local Ollama `llama3.2:3b` inside `<untrusted_telemetry>` / `<retrieved_runbook_data>` XML prompt isolation barriers to return a Pydantic-validated `DiagnosisProposal`.
5. **Deterministic Policy & Refusal Gate**: `policy/engine.py` and `playbooks/registry.py` never blindly execute AI output. If the target asset is unknown, evidence score is weak, model JSON fails, prompt injection triggers high uncertainty, or the runbook has `permitted_playbook_id=None` (e.g. `RB-011` single-instance `postgres-claims-db` failover), automation refuses and transitions to `ESCALATED`. Low-risk allowlisted playbooks auto-execute (`READY_TO_REMEDIATE`); high-risk playbooks require Keycloak `approver` sign-off with replay-protected `pyotp` TOTP bound to live Kubernetes UID & `resourceVersion` (`AWAITING_APPROVAL`).
6. **Leased Kubernetes Execution & 60s Watchdog**: `RedisTargetLease` acquires a per-deployment Redis `SET NX PX` lock with Lua token renewal (`locks.py`), records an idempotent `ExecutionAttempt` prior to calling `KubernetesExecutor` (`executor.py`, impersonating Terraform-scoped ServiceAccount `aegisops-remediator`), reconciles crashed retries cleanly, and starts `verify_sustained_recovery()` (`watchdog.py`) which demands 60 unbroken seconds of healthy K8s rollout + HTTP health probe + fresh Prometheus telemetry before reaching `RESOLVED`.
7. **Dual-Audience Interactive Console**: A React 18 + TypeScript + `@xyflow/react` SPA (`55173`) provides zero-risk unauthenticated **Visitor Mode** (`Executive Overview` vs. `Technical Deep-Dive`), **Guided Tour**, **Recorded Incident Replay**, **Privacy Scrubber Playground**, **Hybrid Search Tester**, **5-Scenario Chaos Lab**, **Live Business Probes**, **Keycloak S256 PKCE Auth**, **TOTP MFA Modals**, **Engineering Evidence**, and **Markdown / pure-Python multi-page PDF Postmortem Exports**.

---

## 2. Backend Implementation Deep-Dive (`backend/app/`)

### 2.1 Configuration, Database, Redis & Application Factory
- **`backend/app/config.py` (`184` lines)**: Defines Pydantic `Settings` loaded via `@lru_cache(maxsize=1)` `get_settings()`. Enforces 9 strict startup validators:
  - `_reject_wildcard_cors`: refuses `*` CORS origins when credentials are enabled.
  - `_validate_database_url` / `_validate_redis_url`: validates PostgreSQL (`postgresql+asyncpg://`) and Redis DSNs.
  - `_validate_webhook_hmac` / `_validate_webhook_bearer` / `_validate_session_secret` / `_validate_fernet_key`: rejects placeholder secrets matching `_FORBIDDEN_SECRET_MARKERS` and validates minimum entropy lengths + valid Fernet key format.
  - `_validate_vector_dimensions`: locks `768` dimensions matching `nomic-embed-text:latest`.
  - `_validate_cross_fields`: validates K8s context/namespace allowlists (`kind-aegisops-local`, `aegisops-healthcare`) and recovery window invariants.
- **`backend/app/db.py` (`51` lines)**: `build_engine()`, `build_session_factory()`, `get_db_session()`, and `check_postgres_ready()` (verifies live Postgres connection and queries `pg_extension` to confirm `pgvector` is installed before `/readyz` returns `200`).
- **`backend/app/redis_client.py` (`24` lines)**: `build_redis_client()` and `check_redis_ready()` executing `PING`.
- **`backend/app/main.py` (`170` lines)**:
  - `create_app()` wires lifespan startup/teardown (engine, session factory, Redis client, `OIDCVerifier`), registers all `9` API routers (`webhooks`, `auth`, `approvals`, `incidents`, `topology`, `metrics`, `stream`, `runbooks`, `showcase`), configures strict CORS headers (`Authorization`, `Content-Type`, `X-CSRF-Token`, `X-Correlation-ID`), injects `X-Correlation-ID` HTTP middleware with Prometheus counter `aegisops_control_plane_requests_total`, registers a sanitized global exception handler (logs exception class & correlation ID only, never raw stack/payloads), and exposes `/healthz`, `/readyz`, and `/metrics`.
- **`backend/pyproject.toml` (`75` lines)**: Python `>=3.12,<3.13`, explicit `[build-system]` (`setuptools>=68.0`), `[tool.setuptools.packages.find]` (`include = ["app*"]`), `dev` extras (`pytest`, `pytest-asyncio`, `ruff`, `mypy`, `types-PyYAML`, `playwright`), Ruff line length `100` (`E, F, I, UP, B, SIM`), Mypy Python `3.12` config, and Pytest `asyncio_mode = "auto"`.

### 2.2 PostgreSQL + `pgvector` Data Model & Migrations (`13` Tables)
Implemented in `backend/app/models/entities.py` (`544` lines) and applied deterministically via `backend/migrations/env.py` + `0001_initial_schema.py` (`483` lines) -> `0002_showcase_upgrade.py` (`253` lines):

| Table | ORM Class (`entities.py`) | Purpose & Critical Constraints / Indexes |
|---|---|---|
| `assets` | `Asset` | CMDB node inventory (`slug`, `asset_type`, `criticality`, `owner_team`, `stateless_eligible`, `known_good_image`, `k8s_deployment_name`); `uq_assets_cluster_ns_name`, `ck_assets_criticality` |
| `asset_dependencies` | `AssetDependency` | Directed edges (`source_asset_id -> target_asset_id` meaning `source depends_on target`); self-loop prevented by `ck_asset_dep_no_self_edge`, unique `uq_asset_dep_src_tgt_type` |
| `incidents` | `Incident` | Core incident ledger holding scrubbed summary, blast-radius snapshot, severity explanation, captured prompt JSON, verification progress, `source_provenance` (`live_alert`/`interactive_demo`/`automated_test`/`recorded_replay`/`unknown`), optimistic `version_id`, timestamps (`fault_onset_at`..`resolved_at`); partial unique index `ix_incidents_active_dedup_key` on `dedup_key WHERE state NOT IN ('RESOLVED', 'FAILED')` |
| `incident_events` | `IncidentEvent` | Timeline of transitions & diagnostics; monotonic `sequence_num` (`BIGINT IDENTITY`) for SSE `after_seq`; Postgres trigger `trg_incident_events_append_only` blocks `UPDATE`/`DELETE` |
| `runbooks` | `Runbook` | Knowledge documents with `embedding` (`VECTOR(768)`, HNSW cosine index `ix_runbooks_embedding_hnsw` `m=16, ef_construction=64`), `search_tsv` (GIN index `ix_runbooks_search_tsv`), `embedding_model`, `embedding_digest`, and Showcase upload lifecycle `indexing_status` (`UPLOADED`..`READY`/`FAILED`) |
| `approval_requests` | `ApprovalRequest` | High-risk step-up approvals storing `parameters_hash`, `target_k8s_uid`, `target_resource_version`, status (`PENDING`/`APPROVED`/`DENIED`/`EXPIRED`), `decided_by_sub`, `totp_timecode_used` |
| `execution_attempts` | `ExecutionAttempt` | K8s mutation attempts with unique `idempotency_key`, Redis `lease_token`, `before_state_json`, `after_state_json`, `status` |
| `audit_records` | `AuditRecord` | Immutable governance ledger (`actor_sub`, `actor_role`, `action_type`, `policy_decision`, `details_json`); protected by trigger `trg_audit_records_append_only` |
| `outbox_jobs` | `OutboxJob` | Transactional queue (`TRIAGE_INCIDENT`, `EXECUTE_REMEDIATION`, `VERIFY_RECOVERY`, `RUN_DEMO_SCENARIO`, `INDEX_RUNBOOK`); `incident_id` nullable for Showcase/runbook jobs; indexed by `ix_outbox_jobs_claimable` & unique `dedup_job_key` |
| `user_totp_secrets` | `UserTotpSecret` | Fernet-encrypted `pyotp` seeds keyed by `user_sub`, `is_verified`, `last_used_timecode`, `failed_attempts`, `locked_until` |
| `demo_runs` | `DemoRun` | Chaos Lab execution tracker linking `scenario_id`, `status`, target asset lock, baseline snapshot, unique `idempotency_key`, and Guided Tour narration |
| `business_probe_samples` | `BusinessProbeSample` | Semantic HTTP/DB health checks (`eligibility-api`, `claims-processor`, `provider-directory`, `postgres-claims-db`) correlated to active incidents/runs |
| `system_control_flags` | `SystemControlFlag` | Operator safety toggles (`automation_paused`) persisted in PostgreSQL |

### 2.3 Canonical State Machine (`backend/app/domain/state_machine.py`, `134` lines)
- Defines `IncidentState` StrEnum (`OPEN`, `TRIAGING`, `READY_TO_REMEDIATE`, `AWAITING_APPROVAL`, `ESCALATED`, `REMEDIATING`, `VERIFYING`, `RESOLVED`, `FAILED`) and strict `ALLOWED_TRANSITIONS` mapping (terminal states `RESOLVED` and `FAILED` have empty outbound sets).
- `validate_transition(from_state, to_state)` raises `InvalidStateTransitionError` on any illegal transition.
- `transition_incident(...)` locks the row with `SELECT ... FOR UPDATE`, validates state transition, bumps `version_id`, sets optional lifecycle timestamp (`detected_at`, `triaged_at`, `approved_at`, `mutated_at`, `first_recovered_at`, `resolved_at`), and inserts both an `IncidentEvent` and an `AuditRecord` in the same DB transaction.

### 2.4 Edge Privacy Scrubber (`backend/app/privacy/scrubber.py`, `357` lines)
- Defines `36` normalized `SENSITIVE_KEY_TOKENS` (e.g., `ssn`, `memberid`, `patientname`, `dob`, `email`, `jwt`, `bearertoken`, `apikey`, `password`, `clientip`), `14` `ALLOWED_ALERT_LABELS`, `4` `ALLOWED_ALERT_ANNOTATIONS`, and `11` compiled `_PATTERNS` (`jwt`, `bearer`, `ssn_dashed`, `ssn_contextual`, `member_id`, `member_id_contextual`, `email`, `ipv4`, `phone`, `dob`, `person_name`).
- `scrub_text()` returns redacted text + per-category counts (`[REDACTED:SSN]`, `[REDACTED:MEMBER_ID]`, `[REDACTED:JWT]`, `Bearer [REDACTED:TOKEN]`, `[REDACTED:EMAIL]`, `[REDACTED:IP]`, `[REDACTED:PHONE]`, `dob=[REDACTED:DOB]`, `person=[REDACTED:NAME]`).
- `scrub_value()` walks nested dicts/lists recursively; `scrub_alertmanager_payload()` strips unallowlisted keys and tracks `dropped_unallowlisted_keys` + fail-closed `scrubber_failed_fallback` handling so exceptions never emit raw payloads.
- `evaluate_redaction_corpus()` scores synthetic corpus precision and recall (`1.00 / 1.00`).

### 2.5 CMDB Graph & Seeders (`backend/app/cmdb/graph.py`, `backend/app/seed/{cmdb_seed,runbook_seed}.py`)
- **`cmdb_seed.py` (`242` lines)**: Idempotently upserts `8` assets (`member-portal-gateway`, `eligibility-api`, `claims-processor`, `provider-directory`, `pharmacy-prior-auth`, `edi-837-ingest`, `postgres-claims-db`, `redis-session-cache`) and `9` directed dependency edges (`HTTP_SYNC`, `ASYNC_QUEUE`, `DATABASE`, `CACHE`).
- **`cmdb/graph.py` (`303` lines)**: `_traverse_direction()` performs breadth/depth-safe traversal with visited-set cycle breaking (`BlastRadiusNode`, `BlastRadiusResult`); `get_blast_radius()` returns both upstream dependencies and downstream affected consumers; `compute_severity()` computes `P1–P4` + structured `severity_explanation` JSON from root asset criticality, unique downstream consumer count, and alert severity.
- **`runbook_seed.py` (`163` lines)**: Parses Markdown frontmatter/sections of all `18` docs in `runbooks/` (`RB-001`–`RB-015` + `PM-001`–`PM-003`), generates `768`-dim embeddings with Ollama, builds Postgres `tsvector`, and upserts rows cleanly as `indexing_status="READY"`.

### 2.6 Allowlisted Playbook Registry & Deterministic Policy Engine
- **`backend/app/playbooks/registry.py` (`179` lines)**: Defines immutable `@dataclass(frozen=True) class PlaybookSpec` and `PLAYBOOK_REGISTRY` with `5` strictly allowlisted deterministic playbooks:
  1. `replica_scale_out_bounded` (`v1.0.0`, `LOW` risk, stateless `SERVICE`, bounded `target_replicas` `[1, 4]` default `3`, `timeout=90s`)
  2. `stateless_deployment_restart` (`v1.0.0`, `LOW` risk, stateless `SERVICE`, RollingUpdate pod annotation restart, `timeout=120s`)
  3. `memory_limit_increase_bounded` (`v1.0.0`, `HIGH` risk — MFA required, bounded `memory_mi` `[128, 512]` default `384`, `timeout=120s`)
  4. `deployment_image_rollback` (`v1.0.0`, `HIGH` risk — MFA required, ignores LLM tag strings and forces DB `Asset.known_good_image`, `timeout=150s`)
  5. `scoped_cache_key_eviction` (`v1.0.0`, `LOW` risk, `CACHE`/`SERVICE`, `SCAN + UNLINK` strictly on prefix `session:lock:stale:`, `timeout=45s`)
  - `validate_playbook_for_asset()` enforces allowlist membership, target asset existence, asset type/service allowlist, `stateless_eligible`, `known_good_image` presence, and numeric parameter clamping.
- **`backend/app/policy/engine.py` (`204` lines)**: `evaluate_remediation_policy()` checks in order:
  1. Target `Asset` exists in CMDB -> else `REFUSE_AND_ESCALATE`.
  2. Pydantic `DiagnosisProposal` exists (not `None` / timed out / invalid JSON) -> else escalate.
  3. Model did not set `refusal_recommended=True` or `uncertainty_level == "HIGH"` and supplied non-null `proposed_playbook_id`.
  4. Cited runbook slug exists inside retrieved RAG context and its applicability includes `asset.slug`.
  5. Retrieval bar passes (`vector_similarity >= settings.aegisops_similarity_threshold` [`0.78`] OR `lexical_score >= 0.05 and vector_similarity >= 0.50`).
  6. Runbook's `permitted_playbook_id` is non-null (`None` on `RB-011` Postgres lag forces immediate escalation) and equals `proposal.proposed_playbook_id`.
  7. `validate_playbook_for_asset()` succeeds -> returns `REQUIRE_APPROVAL` (`AWAITING_APPROVAL`) for `HIGH` risk or `ALLOW_AUTO_EXECUTE` (`READY_TO_REMEDIATE`) for `LOW` risk.

### 2.7 Hybrid RAG, Prompt Isolation & Observability
- **`backend/app/rag/embeddings.py` (`71` lines)**: Verifies index embedding model/dimension consistency (`assert_index_model_consistency`) and embeds texts via local Ollama `/api/embed`.
- **`backend/app/rag/retriever.py` (`161` lines)**: `hybrid_search_runbooks()` executes a single PostgreSQL CTE joining top `vec_hits` (`embedding <=> :qvec`, `READY` docs only) and `lex_hits` (`websearch_to_tsquery` + `ts_rank_cd`), fusing scores via `1.0 / (rrf_k + rank)` (`rrf_k=60`) and returning separate `vector_similarity`, `lexical_score`, `rrf_score`, `vector_rank`, and `lexical_rank`.
- **`backend/app/rag/diagnosis.py` (`232` lines)**: `build_diagnosis_prompt()` isolates untrusted alert summaries inside `<untrusted_telemetry>` and retrieved docs inside `<retrieved_runbook_data>`. `generate_diagnosis_with_record()` invokes Ollama `llama3.2:3b` at `temperature=0` with JSON schema validation (`DiagnosisProposal`) and returns both the structured proposal and full prompt capture metadata (`system_prompt`, `user_prompt`, `cited_context_slugs`, `latency_ms`, `cached`).
- **`backend/app/observability/langfuse_tracer.py` (`63` lines)** & **`ragas_eval.py` (`74` lines)**: Records sanitized trace spans to local Langfuse (`53000`) and evaluates offline Ragas `faithfulness` + `context_recall` across 5 canonical scenarios.

### 2.8 Security, OIDC PKCE & TOTP MFA
- **`backend/app/auth/oidc.py` (`264` lines)**: `OIDCVerifier` fetches & caches Keycloak JWKS (`RS256`), exchanges PKCE authorization codes, validates tokens, derives server role precedence (`approver > operator > viewer`) via `derive_roles_from_claims()`, sets `HttpOnly` signed session cookie + readable `X-CSRF-Token` cookie, and provides FastAPI RBAC dependencies (`require_visitor_or_user`, `require_viewer`, `require_operator`, `require_approver`, `verify_csrf_header`).
- **`backend/app/auth/totp.py` (`132` lines)**: `enroll_user_totp()` creates a 160-bit Base32 secret encrypted via Fernet and returns an `otpauth://` provisioning URI; `verify_and_consume_totp()` enforces row locking (`SELECT ... FOR UPDATE`), `valid_window=1`, 5-attempt / 5-minute lockout (`429`), and strict monotonic replay prevention (`matched_timecode <= row.last_used_timecode` -> `401`).
- **`backend/app/api/approvals.py` (`278` lines)**: `approve_high_risk_action()` requires `approver` + CSRF + `otp_code`, checks `target_k8s_uid` and live `target_resource_version` against Kubernetes before enqueueing `EXECUTE_REMEDIATION` (drift returns `409 Conflict` requiring fresh inspection); `deny_high_risk_action()` transitions `AWAITING_APPROVAL -> ESCALATED`.

### 2.9 Kubernetes Executor, Redis Locks, Outbox Worker & 60s Watchdog
- **`backend/app/worker/locks.py` (`113` lines)**: `RedisTargetLease` acquires `aegisops:lock:<cluster>:<ns>:<deploy>` via `SET NX PX`, runs background renewal every `max(ttl_ms/3000, 0.5)s` using Lua ownership-check script `_LUA_EXTEND_IF_OWNED`, asserts live ownership right before K8s API calls (`assert_owned()`), and releases via `_LUA_RELEASE_IF_OWNED`.
- **`backend/app/k8s/executor.py` (`573` lines)**:
  - `KubernetesExecutor.validate_target_boundary()` blocks any context outside `kind-aegisops-local`, any namespace outside `aegisops-healthcare`, or any Deployment missing label `aegisops.io/managed=true`, and injects header `Impersonate-User: system:serviceaccount:aegisops-healthcare:aegisops-remediator`.
  - `read_deployment_snapshot()` reads live deployment fields & computes `rollout_status` (`Healthy`, `Progressing`, `Degraded`, `ScaledToZero`).
  - `execute_remediation_attempt()` records idempotent `ExecutionAttempt` (`IN_PROGRESS`), performs crash reconciliation via `_matches_desired_state()` (skipping duplicate patches if the prior crashed run already landed desired replicas/memory/image), asserts Redis lease ownership, patches deployment (`replicas`, `resources.limits.memory`, `image`, or `restartedAt` annotation; or safe prefix `SCAN`+`UNLINK` for `scoped_cache_key_eviction`), waits for rollout readiness, and saves before/after JSON diffs.
- **`backend/app/worker/runner.py` (`762` lines)**: Async worker pool (`asyncio.Semaphore(4)`) claiming `PENDING` or expired-lease `CLAIMED` jobs with `FOR UPDATE SKIP LOCKED` (`claim_next_outbox_job()`). Dispatches `TRIAGE_INCIDENT`, `EXECUTE_REMEDIATION` (checks `automation_paused` flag -> `_AutomationPausedHold` requeuing harmlessly), `VERIFY_RECOVERY`, `RUN_DEMO_SCENARIO`, and `INDEX_RUNBOOK`.
- **`backend/app/worker/watchdog.py` (`279` lines)**: `query_prometheus_scalar()` rejects missing, `NaN`, or stale (`>60s` old) Prometheus samples; `collect_health_sample()` requires ALL three signals healthy simultaneously (Kubernetes deployment rollout ready + HTTP `/readyz`/functional endpoint `200` + fresh Prometheus health metrics); `verify_sustained_recovery()` tracks unbroken elapsed healthy time over `aegisops_recovery_window_seconds` (`60s`) and resets elapsed time back to `0` on any probe dip (`verification_state_json`), reaching `RESOLVED` only after continuous 60s stability.

### 2.10 FastAPI Routers & Showcase Modules
- **`webhooks.py` (`445` lines)**: `POST /api/v1/webhooks/alertmanager` checks HMAC/Bearer auth, rate limits requests, blocks SSRF callback keys (`_FORBIDDEN_URL_KEYS`), scrubs payloads, assigns `source_provenance` (`X-AegisOps-Provenance` validated against trusted shared headers), deduplicates active incidents, links active `DemoRun`, and enqueues triage atomically.
- **`incidents.py` (`887` lines)**: `GET /api/v1/incidents` (`hide_test_runs`, tab SQL counts, search, sort, pagination), `GET /api/v1/incidents/{id}` (full `compute_lifecycle_steps()` + `build_why_this_action()` + business probes), `GET /{id}/prompt` (captured Ollama prompt inspector), `GET /{id}/postmortem.md`, and `GET /{id}/postmortem.pdf`.
- **`runbooks.py` (`694` lines)**: `GET /api/v1/runbooks`, `GET /{slug}`, `POST /api/v1/runbooks/upload` (`<=64 KiB` `.md`, strips/rejects `<script>`/`javascript:` XSS, validates YAML frontmatter & `PLAYBOOK_REGISTRY` IDs, blocks risk-tier downgrades, dispatches `INDEX_RUNBOOK` `UPLOADED->VALIDATING->INDEXING->READY`), `POST /{slug}/retry-index`, and `POST /api/v1/runbooks/search` (live Hybrid Search Tester).
- **`topology.py` (`253` lines)**: `GET /api/v1/topology` (returns nodes, directed edges, 3s TTL cached live K8s `k8s_live` facts, optional `incident_id` diff) & `GET /api/v1/topology/{slug}/blast-radius`.
- **`metrics.py` (`205` lines)** & **`stream.py` (`131` lines)**: Scoped MTTD/MTTR quantiles & business value counters (`/api/v1/metrics/summary`); cursor-resumable SSE (`after_seq`, `2.0s` DB poll interval) streaming events + active `demo_runs` (`/api/v1/stream/incidents`).
- **`showcase.py` (`648` lines)** backed by **`backend/app/showcase/`**:
  - `controls.py` (`693` lines): `collect_system_readiness()`, `get_automation_flag()`, `set_automation_flag()`, `preview_demo_baseline_reset()`, `execute_demo_baseline_reset()` (restores healthy baseline in `aegisops-healthcare` while preserving immutable audit logs).
  - `scenarios.py` (`713` lines): 5-scenario Chaos Lab catalog + `_conflicting_services()` cross-service `409 Conflict` lock + background traffic loop (`_drive_url_loop`) + fault injection + real-time Guided Tour `build_narration_from_incident()`.
  - `probes.py` (`232` lines): SSRF-safe allowlisted probes (`eligibility-api`, `claims-processor`, `provider-directory`, `postgres-claims-db`).
  - `replay.py` (`490` lines): `list_available_replays()` and `get_replay_timeline()` returning both `captured_live_run` timelines and `illustrative_fixture` demonstrations without touching live Redis/DB/K8s.
  - `postmortem.py` (`404` lines) + `pdf_renderer.py` (`180` lines): Unified server postmortem snapshot renderer emitting escaped Markdown and multi-page pure-Python `%PDF-1.4` (`FlateDecode`) binary PDFs.

---

## 3. Synthetic Microservices, Infrastructure & Chaos Tooling

### 3.1 Target Microservices (`services/`)
Built cleanly via Dockerfiles on `python:3.12-slim` with `services/shared/base_service.py` (`151` lines) configuring Prometheus gauges/counters/histograms + optional OTLP tracing and token-protected fault endpoints (`verify_internal_fault_token`):
- **`services/eligibility-api/main.py` (`171` lines, `:58081`)**: Supports good image `v1.0.0-good` and broken canary `v1.9.0-broken` (`IS_BROKEN_CANARY`), queries Postgres & Redis (`MAX_POOL`), exposes `/healthz`, `/readyz`, `GET /api/eligibility/check`, and `POST /internal/fault`.
- **`services/claims-processor/main.py` (`160` lines, `:58082`)**: Simulates claim adjudication (`POST /api/claims/adjudicate` calling `eligibility-api`), tracks memory working-set gauges against cgroup limits, exposes fault injection for memory exhaustion (`OOMKilled` Exit 137 / `88%+` allocation).
- **`services/provider-directory/main.py` (`109` lines, `:58083`)**: Clinic search endpoint (`GET /api/providers/search`) with Redis-backed CPU latency fault switch.

### 3.2 Docker Compose, Observability, Terraform & Kubernetes (`infra/`)
- **`infra/compose/docker-compose.yml` (`155` lines)**: Runs `aegisops-postgres` (`pgvector/pgvector:pg16` on `55432`, init script `01-init.sql` creating `aegisops_langfuse` DB), `aegisops-redis` (`7.4-alpine` appendonly on `56379`), `aegisops-otel-collector` (`0.114.0` on `55317/55318`), `aegisops-prometheus` (`v2.55.1` on `59090`), `aegisops-alertmanager` (`v0.27.0` on `59093`), `aegisops-keycloak` (`26.0` on `58080`), and `aegisops-langfuse` (`v2` on `53000`).
- **`infra/compose/prometheus/alert_rules.yml` (`75` lines)**: Defines 4 traffic-guarded alert rules (`High5xxErrorRate`, `EligibilityDbPoolExhausted`, `ClaimsProcessorMemoryPressure`, `ProviderDirectoryHighLatencyCpu`) with deterministic `error_code` labels (`ERR_CANARY_IMG_SHA_BAD_9921`, `ERR_PG_POOL_TIMEOUT_57P03`, `ERR_OOM_EXIT_137_CLAIMS_BATCH`, `ERR_CPU_SATURATION_P95_SLOW`).
- **`infra/terraform/main.tf` (`125` lines)** + `variables.tf`/`outputs.tf`: Provisions `aegisops-healthcare` and `aegisops-system` namespaces on `kind-aegisops-local`, least-privilege ServiceAccount `aegisops-remediator` (`Role` + `RoleBinding` allowing `patch` ONLY on `apps/deployments` & `deployments/scale`, read-only on `pods/events/services`), `LimitRange` (`default=256Mi`, `max=512Mi`), and `ResourceQuota` (`24` pods, `4` req CPU, `3Gi` req mem, `8` limit CPU, `6Gi` limit mem).
- **`infra/k8s/kind-config.yaml` (`23` lines)** & **`infra/k8s/workloads/*.yaml`**: Local Kubernetes `v1.32.2` node mapping NodePorts `30081–30084` to host `58081–58084`, hosting the 3 microservices plus `postgres-claims-db`, `redis-session-cache`, and `kube-state-metrics`.

### 3.3 Chaos Harness, Knowledge Corpus & Automation (`chaos/`, `runbooks/`, `scripts/`)
- **`chaos/run_scenario.py` (`530` lines)** & **`chaos/k6/webhook_burst_and_api.js`**: Automates end-to-end fault injection, traffic generation, Keycloak + `pyotp` approval flows, 60s watchdog verification (`docs/evidence/chaos-scenarios-report.json`), and `k6` webhook burst benchmarking (`docs/evidence/k6-summary.json`).
- **`runbooks/` (`18` docs)**: `15` engineering runbooks (`RB-001`–`RB-015`, spanning OOM, DB pool, CPU latency, canary rollback, scoped cache locks, TLS expiry, EDI 837 queue, CoreDNS, CrashLoop, Redis timeout, Postgres lag boundary `RB-011`, disk pressure, OIDC JWKS, prior auth timeout, DDL lock contention) + `3` synthetic postmortems (`PM-001`–`PM-003`).
- **`scripts/` (`13` files)**: Cross-phase lifecycle automation (`setup.ps1`, `doctor.ps1`, `up.ps1`, `migrate.ps1`, `seed.ps1`, `test.ps1`, `demo.ps1`, `logs.ps1`, `down.ps1`, `reset.ps1`, `send_synthetic_alert.py`, `verify_docs.py`, `_common.ps1`).

---

## 4. Frontend SRE & Showcase Console (`frontend/src/`)

Built with **React 18, TypeScript, Vite 6 (`68` transformed modules), and `@xyflow/react`**:
- **`App.tsx` (`742` lines)**, **`lib/pkce.ts` (`84` lines)**, **`types.ts` (`492` lines)**, **`styles.css` (`830` lines)**:
  - Implements **Audience Toggle (`Executive Overview` vs. `Technical Deep-Dive`)** decoupled from server RBAC (`Visitor`, `viewer`, `operator`, `approver`).
  - Manages S256 PKCE login flow, CSRF header injection (`readCookie`, `apiFetch`, `apiDownloadFile`), 3 main tabs (`console`, `knowledge`, `evidence`), queue filters (`active`/`resolved`/`escalated`/`failed`/`all`, default `Hide Test Runs` ON, search, sort), SSE live updates (`connecting`/`live`/`reconnecting` + stale indicator), Guided Tour (`sessionStorage` restorable), and isolated Recorded Replay controller.
- **13 Specialized UI Components (`frontend/src/components/`)**:
  - `TopologyGraph.tsx` (`251L`): Interactive `@xyflow/react` blast-radius graph displaying criticality badges, downstream highlight rings, and live K8s replica/image/memory facts.
  - `IncidentDetail.tsx` (`331L`), `LifecycleStepper.tsx` (`69L`), `DecisionExplanationCard.tsx` (`122L`): Complete incident timeline, 7-step progress bar, live `"Checking service stability: X of 60 seconds observed"`, 7-question "Why This Action" breakdown, RAG citations, TOTP approve/deny triggers, and `.md`/`.pdf` download buttons.
  - `ChaosLabPanel.tsx` (`349L`): 5-scenario launcher, `409 Conflict` lock display, Pause Automation toggle, and scoped Baseline Reset preview/confirm modal.
  - `BusinessProbeCard.tsx` (`134L`): One-click `Check Patient Eligibility` and service probes with response time & dependency check output.
  - `PrivacyPromptDrawer.tsx` (`231L`): Interactive Privacy Scrubber Playground (with 3 presets & live redaction counts) + XML-isolated Ollama Prompt Inspector.
  - `RunbookKnowledgePanel.tsx` (`367L`): Searchable `18+` runbook library, `.md` runbook uploader with validation/indexing status badge + retry button, and interactive Hybrid Search Tester displaying vector cosine, lexical rank, RRF, and `0.78` threshold explanations.
  - `ReplayController.tsx` (`150L`), `GuidedTourBar.tsx` (`94L`), `MetricsDashboard.tsx` (`138L`), `EngineeringEvidenceView.tsx` (`97L`), `TotpModal.tsx` (`99L`): Complete Showcase walkthrough, metrics & baseline ROI configurator, live build/eval evidence viewer, and TOTP QR enrollment/approval modal.

---

## 5. CI/CD, Git Hygiene & Verification Evidence

### 5.1 GitHub Actions Workflows (`.github/workflows/`) & `.gitattributes`
- **`ci.yml` (`115` lines)**: Runs on `ubuntu-24.04` (pinned LTS) with `permissions: contents: read`, PR `concurrency` cancellation, `timeout-minutes: 15`, `pgvector/pgvector:pg16` (`55432`) & `redis:7.4-alpine` (`56379`) services, `astral-sh/setup-uv@v5` (`activate-environment: false`, `uv venv --clear`), Node `22` `npm ci` + `typecheck` + `build`, `asyncpg` extension retry init + `alembic upgrade head` + `cmdb_seed`, workflow YAML syntax check + `ruff` + `mypy` + `scripts/verify_docs.py`, unit & PG/Redis integration pytest suites (`50` CI tests), and tracked-file secret pattern scan.
- **`live-cluster-chaos.yml` (`65` lines)**: Manual `workflow_dispatch` workflow (`ubuntu-24.04`, `timeout-minutes: 30`) installing `setup-uv@v5`, `kind v0.27.0`, `kubectl`, Ollama (`nomic-embed-text:latest` + `llama3.2:3b`), Playwright Chromium (`--with-deps`), building and loading demo service images into `kind-aegisops-local`, and verifying workload deployments.
- **`.gitattributes` (`4` lines)**: Enforces `eol=lf` on `.sh`, `.yml`, `.yaml` so Windows edits never introduce CRLF issues on Linux runners.

### 5.2 Complete Automated Test Suite (`backend/tests/`, `20` Modules / `65` Tests)
- **Unit Tests (`32` cases)**: `test_config.py` (settings validation), `test_scrubber.py` (regex, nested dict, fail-closed, corpus precision/recall `1.0`), `test_policy_refusal.py` (low/high risk, unknown asset, DB refusal, parameter clamping), `test_state_machine.py` (all valid & illegal transitions).
- **Integration Tests (`31` cases)**: `test_foundation_health.py`, `test_cmdb_graph.py`, `test_alertmanager_webhook.py`, `test_hybrid_rag.py`, `test_ollama_diagnosis.py`, `test_locks_and_reconciler.py`, `test_k8s_remediation_kind.py`, `test_auth_and_approvals.py` (including 5-way TOTP/RV concurrency race), `test_recovery_watchdog.py`, and Showcase suites `test_showcase_{readiness_and_controls,queue_and_lifecycle,scenarios_and_probes,inspectors_and_runbooks,replay_and_postmortem}.py`.
- **Browser E2E Tests (`2` suites)**: `test_browser_console.py` & `test_showcase_browser.py` in headless Chromium verifying Visitor Mode, Replay, Privacy Playground, Hybrid Search, Evidence view, Keycloak OIDC PKCE login, live probe execution, TOTP QR modal, SSE `Stream: live`, and Baseline Reset modal with `0` console/page errors.

### 5.3 Quantitative Benchmark Summary
- **Final Local Gate (`.\scripts\test.ps1` -> `docs/evidence/showcase-test-gate.txt`)**: `65 / 65` Pytest passed in `220.05s`, Ruff clean, Mypy `50` files clean, Vite `68` modules built in `5.06s`.
- **`k6` Webhook Burst (`docs/evidence/k6-summary.json`)**: `240 / 240` checks (`100.00%`), `0.00%` failed requests across `120` requests (`5–15` VUs), `p95 = 1109.0 ms` (`< 1500 ms` target).
- **Live Chaos Scenarios (`docs/evidence/chaos-scenarios-report.json` + Scenario 5 test)**: Scenarios `1–4` (`claims_oom`, `eligibility_pool`, `provider_cpu`, `eligibility_canary`) all reached `RESOLVED` post-60s watchdog; Scenario `5` (`pii_leak_and_db_failure`) scrubbed synthetic PII and escalated `RB-011` safely.
- **Offline `Ragas` (`docs/evidence/ragas-evaluation.json`)**: `context_recall = 0.8586`, `faithfulness = 0.7083` (`3/5` numeric, `2/5` `NaN` due to `llama3.2:3b` NLI formatting variance).
- **Documentation Verification (`scripts/verify_docs.py`)**: All `15` tracked core docs validated cleanly with `0` broken path/env references.

---

## 6. Operational Status & Explicit Boundaries
- **Verified Green CI**: GitHub Actions `ci.yml` passes cleanly on `ubuntu-24.04` (verified on **Run #10** `44080690721` before report-only commit; report commit also validated cleanly with `scripts/verify_docs.py`).
- **Unexecuted Hosted Operations**: `live-cluster-chaos.yml` (`workflow_dispatch`) is YAML-validated and hardened locally but has not been manually triggered on GitHub runners (its full runtime equivalent runs locally via `.\scripts\up.ps1` + `.\scripts\demo.ps1 -Scenario all` + `.\scripts\test.ps1`). `scripts/reset.ps1` was intentionally skipped locally to preserve the verified cluster snapshot.
- **Host Runtime Note**: When Docker backing services (`55432`..`53000`) and `kind` (`64295`) are up, run `.\scripts\up.ps1` after any workstation reboot to bring up FastAPI (`58000`), Outbox Worker, Ollama (`11434`), and Vite (`55173`).
