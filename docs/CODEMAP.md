# AegisOps Code Map (`docs/CODEMAP.md`)

> **Status:** Updated and source-verified against refreshed Graphify AST+semantic extraction (`graphify-out/graph.json`, `graphify-out/GRAPH_REPORT.md`) across Showcase Phases `00–07` (see also [docs/FILE_MAP.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/FILE_MAP.md) for Showcase backend/frontend module inventory).

## 1. Graphify Generation Status & Structural Findings

- **Tooling**: `graphifyy` (installed isolated via `uv tool`, interpreter saved in `graphify-out/.graphify_python`)
- **Generated Artifacts**:
  - `graphify-out/graph.json` — NetworkX-serialized knowledge graph
  - `graphify-out/GRAPH_REPORT.md` — Community cohesion, god nodes, surprising cross-file edges, and suggested queries
  - `graphify-out/graph.html` — Interactive client-side visualization
  - `graphify-out/manifest.json` & `graphify-out/cost.json` — Incremental rebuild manifest and token ledger (`0` external LLM API tokens spent)
- **Scoped Corpus & Exclusions**:
  - **Included**: `203` files (`133` code files AST-extracted including all `backend/app/showcase/*`, `runbooks.py`, and `frontend/src/components/*` Showcase additions; `~97,571` words), `skipped_sensitive: []`
  - **Excluded**: `.venv/`, `frontend/node_modules/`, `frontend/dist/`, `.local/`, `.env`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `docs/evidence/`, `infra/terraform/.terraform/`, `graphify-out/`
  - **Known Extraction Limitation (Honest Gap)**: `tree_sitter_hcl` and `tree_sitter_sql` optional parsers were not installed in the isolated `uv` tool environment, so `infra/terraform/{main.tf,variables.tf,outputs.tf}` (`3` `.tf` files) and `infra/compose/postgres-init/01-init.sql` (`1` `.sql` file), plus `12` declarative/PowerShell/JSON config files (`backend/pyproject.toml`, `frontend/src/main.tsx`, `frontend/vite.config.ts`, `scripts/*.ps1`) yielded `0` AST symbols in Graphify and are documented directly from source inspection.
- **Refreshed Graph Metrics**:
  - **Nodes / Edges / Communities**: `1,569` nodes, `3,727` edges, `98` detected communities
  - **Provenance Mix**: `90% EXTRACTED` · `10% INFERRED` (`385` edges, avg confidence `0.93`) · `0% AMBIGUOUS`
  - **Diagnostics**: `missing_endpoint_edges: 0`, `self_loop_edges: 2`, `exact_duplicate_edges: 0`
- **Top God Nodes (Highest Connectivity)**:
  1. `Settings` (`backend/app/config.py`) — `72` edges
  2. `Asset` (`backend/app/models/entities.py`) — `47` edges
  3. `get_settings()` (`backend/app/config.py`) — `42` edges
  4. `Incident` (`backend/app/models/entities.py`) — `33` edges
  5. `KubernetesExecutor` (`backend/app/k8s/executor.py`) — `29` edges
  6. `build_session_factory()` (`backend/app/db.py`) — `27` edges
  7. `build_engine()` (`backend/app/db.py`) — `26` edges
  8. `create_app()` (`backend/app/main.py`) — `24` edges
  9. `test_k8s_guards_rbac_live_scale_and_crash_reconciliation()` (`backend/tests/integration/test_k8s_remediation_kind.py`) — `24` edges
  10. `AuthenticatedUser` (`backend/app/auth/oidc.py`) — `23` edges
- **Key Architectural Queries Run**:
  - `graphify query "alertmanager webhook incident triage outbox worker kubernetes execution verification" --dfs --budget 1200`: returned `205` connected nodes bridging `webhooks.py::ingest_alertmanager_webhook` -> DB models `Incident` / `OutboxJob` / `ExecutionAttempt` -> `runner.py::_handle_triage_job`, `_handle_execute_job`, `_handle_verify_job` -> `executor.py::KubernetesExecutor`.
  - `graphify path "ingest_alertmanager_webhook" "execute_remediation_attempt"` (directed): `0` direct call edges (proves durable transactional decoupling via PostgreSQL `outbox_jobs` table rather than synchronous HTTP-to-K8s execution).
  - `graphify path "ingest_alertmanager_webhook" "execute_remediation_attempt" --undirected`: `2` hops via `AuditRecord` (`INFERRED 0.95` + `EXTRACTED 1.0`).
  - `graphify explain "KubernetesExecutor"`: `29` total degree links spanning `runner.py`, `approvals.py`, `watchdog.py`, `executor.py`, and integration tests.
- **Note on Knowledge Graph Scope**: Graphify edges capture static AST imports/calls and curated semantic links; runtime control/data flow through Redis, Prometheus scrapes, Alertmanager webhooks, and Kubernetes API server watches are established from source inspection and runtime verification tests below.

---

## 2. Complete Authored Module & Configuration Inventory

### 2.1 Backend Application (`backend/app/`)
| Path | Role | Key Symbols | Primary Upstream / Downstream Links | Tests | `workingflow.md` |
|---|---|---|---|---|---|
| `backend/app/__init__.py` | Package version metadata | `__version__` | Imported by `main.py` | `test_foundation_health.py` | §4, §5 |
| `backend/app/config.py` | Pydantic runtime & safety configuration | `Settings`, `get_settings` | Imported across all backend & chaos modules | `test_config.py` | §3, §5, §19 |
| `backend/app/db.py` | Async SQLAlchemy engine, sessions, readiness probe | `build_engine`, `build_session_factory`, `check_postgres_ready` | Uses `config.py`; consumed by `main.py`, `runner.py`, seeds | `test_foundation_health.py` | §5, §9 |
| `backend/app/redis_client.py` | Async Redis client factory and ping probe | `build_redis_client`, `check_redis_ready` | Uses `config.py`; consumed by `main.py`, `runner.py`, `locks.py` | `test_foundation_health.py`, `test_locks_and_reconciler.py` | §5, §16 |
| `backend/app/main.py` | FastAPI lifespan, routers, CORS, `/healthz`, `/readyz`, `/metrics` | `create_app`, `get_app`, `get_request_session`, `API_REQUESTS_TOTAL` | Mounts all 7 API routers & `OIDCVerifier` | `test_foundation_health.py`, `test_auth_and_approvals.py` | §5, §8 |
| `backend/app/models/__init__.py` | ORM model exports | `Base`, `Asset`, `Incident`, `OutboxJob`, etc. | Re-exports `entities.py` | Used by Alembic & all integration tests | §9 |
| `backend/app/models/entities.py` | 10 PostgreSQL + pgvector ORM tables & indexes | `Asset`, `AssetDependency`, `Incident`, `IncidentEvent`, `Runbook`, `ApprovalRequest`, `ExecutionAttempt`, `AuditRecord`, `OutboxJob`, `UserTotpSecret` | Queried across APIs, CMDB, RAG, worker, auth | `test_cmdb_graph.py`, `test_hybrid_rag.py` | §9 |
| `backend/app/privacy/scrubber.py` | Earliest-boundary PHI/PII/secret scrubber & corpus evaluator | `scrub_text`, `scrub_value`, `scrub_alertmanager_payload`, `evaluate_redaction_corpus`, `RedactionResult` | Called first in `webhooks.py`, `langfuse_tracer.py`, `ragas_eval.py` | `test_scrubber.py` | §5, §11 |
| `backend/app/cmdb/graph.py` | Cycle-safe recursive CTE blast-radius & P1–P4 severity | `get_blast_radius`, `compute_severity`, `BlastRadiusNode`, `BlastRadiusResult` | Called by `webhooks.py`, `runner.py`, `topology.py`, `incidents.py` | `test_cmdb_graph.py` | §5, §6, §9 |
| `backend/app/domain/state_machine.py` | Canonical state enum, transition guard, append-only writer | `IncidentState`, `ALLOWED_TRANSITIONS`, `validate_transition`, `transition_incident`, `InvalidStateTransitionError` | Called by `runner.py`, `approvals.py` | `test_state_machine.py` | §5, §10 |
| `backend/app/playbooks/__init__.py` | Playbook package marker | — | Export boundary for `registry.py` | — | §12 |
| `backend/app/playbooks/registry.py` | Versioned allowlisted remediation playbooks & parameter validation | `PlaybookSpec`, `PLAYBOOK_REGISTRY`, `validate_playbook_for_asset` | Enforced by `policy/engine.py` & `k8s/executor.py` | `test_policy_refusal.py` | §12 |
| `backend/app/rag/__init__.py` | RAG package marker | — | — | — | §11 |
| `backend/app/rag/embeddings.py` | Local Ollama `/api/embed` client & digest/dimension check | `embed_texts`, `assert_index_model_consistency`, `EmbeddingConfigError` | Used by `retriever.py`, `runbook_seed.py` | `test_hybrid_rag.py` | §11 |
| `backend/app/rag/retriever.py` | PostgreSQL FTS + pgvector cosine + RRF hybrid search | `hybrid_search_runbooks`, `RetrievedDocument` | Used by `runner.py`, `run_ragas_eval.py` | `test_hybrid_rag.py` | §11 |
| `backend/app/rag/diagnosis.py` | Prompt-injection-delimited Ollama structured diagnosis | `DiagnosisProposal`, `build_diagnosis_prompt`, `generate_diagnosis`, `DiagnosisInvocationError` | Used by `runner.py` | `test_ollama_diagnosis.py` | §11 |
| `backend/app/policy/__init__.py` | Policy package marker | — | — | — | §12 |
| `backend/app/policy/engine.py` | Server-controlled refusal/approval/auto-exec gate | `PolicyDecision`, `evaluate_remediation_policy` | Consumes `PLAYBOOK_REGISTRY` + `DiagnosisProposal`; called by `runner.py` | `test_policy_refusal.py` | §12 |
| `backend/app/worker/__init__.py` | Worker package marker | — | — | — | §5, §6 |
| `backend/app/worker/locks.py` | Single-instance Redis `SET NX PX` lease with Lua scripts | `RedisTargetLease`, `LeaseLostError` | Enforced by `runner.py` & `executor.py` | `test_locks_and_reconciler.py` | §5, §16 |
| `backend/app/k8s/__init__.py` | K8s executor package marker | — | — | — | §5, §12 |
| `backend/app/k8s/executor.py` | Official K8s SDK executor, context/NS guards, generation rollout & reconciliation | `KubernetesExecutor`, `KubernetesGuardError`, `TargetSnapshot`, `execute_remediation_attempt` | Called by `runner.py` & `approvals.py` | `test_k8s_remediation_kind.py` | §5, §6, §16 |
| `backend/app/worker/watchdog.py` | Sustained recovery watchdog (`60s` default) over K8s + HTTP + PromQL | `HealthProbeSample`, `query_prometheus_scalar`, `collect_health_sample`, `verify_sustained_recovery` | Invoked in `VERIFY_RECOVERY` by `runner.py` | `test_recovery_watchdog.py` | §6, §15 |
| `backend/app/worker/runner.py` | Durable outbox `SKIP LOCKED` loop handling triage, execution, recovery | `claim_next_outbox_job`, `_handle_triage_job`, `_handle_execute_job`, `_handle_verify_job`, `run_worker_once`, `run_worker_loop` | Orchestrates CMDB, RAG, Policy, Langfuse, Locks, K8s, Watchdog | `test_locks_and_reconciler.py`, Chaos 1–4 | §6, §7 |
| `backend/app/auth/__init__.py` | Auth package marker | — | — | — | §13 |
| `backend/app/auth/oidc.py` | Keycloak RS256 JWKS verification, PKCE exchange, HMAC cookies, CSRF | `AuthenticatedUser`, `OIDCVerifier`, `derive_roles_from_claims`, `exchange_pkce_code`, `sign_session_cookie`, `authenticate_request`, `require_role` | Enforced across API routes & SSE | `test_auth_and_approvals.py`, `test_browser_console.py` | §8, §13 |
| `backend/app/auth/totp.py` | Fernet-encrypted TOTP seeding, rate-limited & replay-safe verify | `enroll_user_totp`, `verify_and_consume_totp` | Called by `api/auth.py`, `api/approvals.py` | `test_auth_and_approvals.py` | §13 |
| `backend/app/api/__init__.py` | API routers package marker | — | — | — | §8 |
| `backend/app/api/webhooks.py` | Authenticated HMAC/Bearer Alertmanager webhook, SSRF guard, atomic outbox | `ingest_alertmanager_webhook`, `_verify_webhook_auth`, `_enforce_rate_limit`, `_contains_forbidden_fetch_directive`, `_resolve_asset` | Uses `scrubber.py`, `cmdb/graph.py`, `pg_insert` `on_conflict_do_nothing` | `test_alertmanager_webhook.py`, `chaos/k6/` | §6, §8 |
| `backend/app/api/auth.py` | Public OIDC config, PKCE callback exchange, `/me`, logout, TOTP endpoints | `auth_public_config`, `oidc_pkce_exchange`, `auth_me`, `auth_logout`, `totp_enroll`, `totp_verify_enrollment` | Uses `oidc.py`, `totp.py` | `test_auth_and_approvals.py`, `test_browser_console.py` | §8, §13 |
| `backend/app/api/approvals.py` | Single-use action-bound & RV-drift-checked approval/denial routes | `approve_high_risk_action`, `deny_high_risk_action` | Uses `totp.py`, `executor.py`, `state_machine.py` | `test_auth_and_approvals.py`, Chaos 1 & 4 | §7, §8, §13 |
| `backend/app/api/incidents.py` | Sanitized incident queue & full detail/citations/diff endpoint | `list_incidents`, `get_incident_detail`, `_serialize_incident` | RBAC `viewer+`, calls `cmdb/graph.py` | `test_auth_and_approvals.py`, `chaos/run_scenario.py` | §8, §14 |
| `backend/app/api/topology.py` | CMDB topology graph & blast-radius query endpoints | `get_topology`, `get_asset_blast_radius` | RBAC `viewer+`, calls `cmdb/graph.py` | `test_browser_console.py` | §8, §14 |
| `backend/app/api/metrics.py` | Honest MTTD, triage, action, verification, MTTR percentiles & PHI redaction counts | `get_metrics_summary`, `_summarize_samples` | Queries `incidents` timestamps directly | `test_browser_console.py`, Chaos 1–4 | §8, §15 |
| `backend/app/api/stream.py` | Authenticated live SSE incident snapshot stream | `stream_incidents` | Polls Postgres snapshots every `2.0s` for `viewer+` | `test_auth_and_approvals.py`, `test_browser_console.py` | §8, §14 |
| `backend/app/observability/__init__.py` | Observability package marker | — | — | — | §15 |
| `backend/app/observability/langfuse_tracer.py` | Scrubbed Langfuse v2 trace & generation exporter (fail-safe when off) | `record_sanitized_llm_trace` | Called by `runner.py` | Chaos 1–4 (`21` traces) | §15 |
| `backend/app/observability/ragas_eval.py` | Local Ollama Ragas Faithfulness & ContextRecall evaluator (`RunConfig(max_workers=1)`) | `run_local_ragas_evaluation` | Called by `run_ragas_eval.py` | `backend/scripts/run_ragas_eval.py` | §15 |
| `backend/app/seed/__init__.py` | Seed package marker | — | — | — | §3 |
| `backend/app/seed/cmdb_seed.py` | Idempotent 8-asset, 9-edge healthcare CMDB seeder | `CMDB_ASSETS`, `CMDB_DEPENDENCIES`, `seed_cmdb` | Run via `scripts/seed.ps1` and tests | `test_cmdb_graph.py` | §3, §9 |
| `backend/app/seed/runbook_seed.py` | Markdown YAML parser & Ollama 768-dim runbook/postmortem seeder | `seed_runbooks`, `_parse_markdown_runbook` | Embeds all `18` `runbooks/*.md` docs | `test_hybrid_rag.py` | §3, §11 |

### 2.2 Backend Migrations, Packaging & Evaluation Scripts
| Path | Role | Key Symbols / Details | Linked From | `workingflow.md` |
|---|---|---|---|---|
| `backend/alembic.ini` | Alembic configuration targeting `backend/migrations` | `script_location = migrations` | `migrations/env.py`, `scripts/migrate.ps1` | §3, §9 |
| `backend/migrations/env.py` | Async Alembic runner reading `AEGISOPS_DATABASE_URL` | `do_run_migrations`, `run_migrations_online` | `backend/app/config.py`, `models/entities.py` | §9 |
| `backend/migrations/script.py.mako` | Alembic migration file template | — | Alembic CLI | §9 |
| `backend/migrations/versions/0001_initial_schema.py` | Initial DDL: extensions, 10 tables, HNSW & GIN & partial unique indexes, append-only triggers | `upgrade`, `downgrade`, `trg_incident_events_append_only`, `trg_audit_records_append_only` | `scripts/migrate.ps1` | §9 |
| `backend/pyproject.toml` | Package definition, Ruff, Mypy, and Pytest config (`asyncio_mode = "auto"`) | `[project]`, `[tool.ruff]`, `[tool.mypy]` | `scripts/setup.ps1`, `scripts/test.ps1` | §3, §18 |
| `backend/requirements.lock` | Pinned `uv pip freeze` lockfile (`136` Python dependencies) | `fastapi==0.115.14`, `langfuse==2.60.10`, `ragas==0.2.15`, etc. | `docs/DEPENDENCIES.md` | §18 |
| `backend/scripts/run_ragas_eval.py` | Runs 5 canonical AIOps queries through Hybrid RAG + Ragas local evaluation | `EVAL_CASES`, `main` -> `docs/evidence/ragas-evaluation.json` | `backend/app/observability/ragas_eval.py` | §15 |

### 2.3 Backend Test Suite (`backend/tests/`)
| Path | Tier & Dependencies | Verified Coverage |
|---|---|---|
| `backend/tests/__init__.py` | Test package marker | — |
| `backend/tests/unit/test_config.py` | Unit (pure Pydantic validation) | Valid/invalid `Settings` bounds, context allowlist, Fernet keys |
| `backend/tests/unit/test_scrubber.py` | Unit (pure Python + corpus metrics) | Positive/negative redactions, nested/multiline, fail-closed fallback, precision/recall=1.0 |
| `backend/tests/unit/test_state_machine.py` | Unit (pure transition matrix) | Valid vs. illegal transitions (`OPEN -> RESOLVED`, etc.) |
| `backend/tests/unit/test_policy_refusal.py` | Unit (deterministic policy engine) | Low-risk auto-exec, high-risk rollback overriding LLM image tag, DB failover refusal |
| `backend/tests/integration/test_foundation_health.py` | Integration (live Postgres + Redis) | `/healthz` and `/readyz` real pgvector & Redis checks |
| `backend/tests/integration/test_cmdb_graph.py` | Integration (live Postgres) | Seed idempotency, directed upstream vs downstream blast radius, cycle-safe CTEs |
| `backend/tests/integration/test_alertmanager_webhook.py` | Integration (live Postgres + Redis) | HMAC/Bearer auth, SSRF guard, PHI redaction, partial unique dedup, DELETE trigger protection |
| `backend/tests/integration/test_hybrid_rag.py` | Integration (live Postgres + pgvector + Ollama) | `18` seeded runbooks, FTS vs vector RRF lexical advantage, 768-dim Ollama embed validation |
| `backend/tests/integration/test_ollama_diagnosis.py` | Integration + explicit mocked timeout/malformed test | Live `llama3.2:3b` JSON diagnosis, prompt-injection refusal, safe fallback on malformed/timeout |
| `backend/tests/integration/test_locks_and_reconciler.py` | Integration (live Redis + Postgres) | Lua ownership lock contention, lease loss abort, `SKIP LOCKED` expired job recovery |
| `backend/tests/integration/test_k8s_remediation_kind.py` | Integration (live `kind-aegisops-local` + Postgres + Redis) | Context/NS guards, remediator impersonation RBAC, live `2` replica scale, crash reconciliation, UID drift guard |
| `backend/tests/integration/test_recovery_watchdog.py` | Integration + mocked sequence probes | Refuses unknown/missing Prometheus metrics; requires unbroken sustained healthy window |
| `backend/tests/integration/test_auth_and_approvals.py` | Integration (live Keycloak + Postgres + `kind`) | Distinct ID/access RS256 validation, RBAC 403s, encrypted TOTP replay lock, RV drift 409, 5-way race -> 1 execution |
| `backend/tests/e2e/test_browser_console.py` | Real Chromium Playwright E2E (`55173` + `58080` + `58000`) | Real Keycloak PKCE flow, role badge, React Flow topology, `Stream: live`, TOTP QR modal, Sign Out |

### 2.4 Frontend SRE Console (`frontend/`)
| Path | Role | Key Symbols / Components | Connections | `workingflow.md` |
|---|---|---|---|---|
| `frontend/package.json` | Vite + React 18 + `@xyflow/react` + TypeScript scripts | `dev`, `typecheck`, `build`, `lint` | `scripts/up.ps1`, `scripts/test.ps1` | §14, §18 |
| `frontend/package-lock.json` | Locked npm dependency tree (`react@18.3.1`, `@xyflow/react@12.4.4`, `qrcode.react@4.2.0`) | Exact reproducible UI packages | `docs/DEPENDENCIES.md` | §18 |
| `frontend/tsconfig.json` | TypeScript strict compiler config | `strict: true`, `noEmit` for typecheck | `npm run typecheck` | §14 |
| `frontend/vite.config.ts` | Dev server on `127.0.0.1:55173` proxying `/api`, `/healthz`, `/readyz` -> `58000` | `defineConfig` | Proxies browser XHR & SSE cleanly without CORS issues | §3, §14 |
| `frontend/index.html` | Console SPA HTML shell | `<div id="root">` | Loads `src/main.tsx` | §14 |
| `frontend/src/main.tsx` | React 18 root render inside `<StrictMode>` | `createRoot` | Renders `<App />` | §14 |
| `frontend/src/types.ts` | Strongly typed API contract interfaces | `AuthConfig`, `UserSession`, `TopologyResponse`, `IncidentSummary`, `IncidentDetailResponse`, `MetricsSummaryResponse` | Shared across all components | §8, §14 |
| `frontend/src/lib/pkce.ts` | Browser S256 PKCE crypto helpers, cookie reader & CSRF-aware fetch wrapper | `generateRandomString`, `sha256Base64Url`, `readCookie`, `apiFetch` | Injects `X-CSRF-Token` on mutating calls | §13, §14 |
| `frontend/src/App.tsx` | Top-level OIDC PKCE bootstrap (StrictMode-deduplicated), SSE lifecycle & dashboard layout | `App`, `inFlightPkcePromise`, `lastUpdateAtRef` | Connects `/api/v1/auth/*`, `/topology`, `/incidents`, `/metrics/summary`, `/stream/incidents` | §13, §14 |
| `frontend/src/components/TopologyGraph.tsx` | Interactive `@xyflow/react` directed dependency & blast-radius viewer | `TopologyGraph`, `TopologyInner` | Click-to-focus `fitView`, visual impact highlights | §14 |
| `frontend/src/components/IncidentDetail.tsx` | Incident detail inspector, RAG citations, TOTP approval/deny form & execution diffs | `IncidentDetail`, `handleApprove`, `handleDeny` | Submits TOTP + expected parameters/playbook binding | §13, §14 |
| `frontend/src/components/TotpModal.tsx` | TOTP MFA enrollment modal rendering `QRCodeSVG` & verification input | `TotpModal`, `startEnrollment`, `submitVerify` | Calls `/api/v1/auth/totp/{enroll,verify-enrollment}` | §13, §14 |
| `frontend/src/components/MetricsDashboard.tsx` | Honest MTTD/MTTR latency percentile cards & redaction tally banner | `MetricsDashboard`, `TimingCard` | Renders `/api/v1/metrics/summary` | §14, §15 |
| `frontend/src/styles.css` | SRE console dark/slate responsive visual styling | Layout grids, severity pills, diff preformatted blocks | Imported by `main.tsx` | §14 |

### 2.5 Synthetic Healthcare Microservices (`services/`)
| Path | Role | Key Endpoints & Metrics | Kubernetes Targets | `workingflow.md` |
|---|---|---|---|---|
| `services/requirements.txt` | Pinned runtime packages for service containers | `fastapi`, `uvicorn`, `psycopg`, `redis`, `opentelemetry-*`, `prometheus-client` | Built into all 4 container images | §3, §18 |
| `services/shared/__init__.py` | Shared service package marker | — | Copied into `/app/shared` | §5 |
| `services/shared/base_service.py` | OTel OTLP HTTP exporter, Prometheus counters/histograms & sliding 12s `http_recent_p95_latency_seconds` gauge | `configure_telemetry`, `verify_internal_fault_token`, `HTTP_REQUESTS_TOTAL`, `HTTP_RECENT_P95_SECONDS` | Imported by all 3 healthcare services | §5, §15 |
| `services/eligibility-api/Dockerfile` | Multi-variant image (`v1.0.0-good` and build-arg `v1.9.0-broken` canary) | `RELEASE_VERSION`, `BROKEN_CANARY` | `eligibility-api` Deployment (`58081`) | §17 |
| `services/eligibility-api/main.py` | Tier-1 eligibility service hitting demo Postgres & Redis, cached dep check, DB pool & canary fault modes | `/healthz`, `/readyz`, `/api/eligibility/check`, `/internal/fault` | Chaos Scenarios 2 & 4 | §17 |
| `services/claims-processor/Dockerfile` | Claims adjudication worker HTTP service container (`v1.0.0-good`) | Uvicorn port `8082` | `claims-processor` Deployment (`58082`) | §17 |
| `services/claims-processor/main.py` | Reads K8s Downward API `POD_MEMORY_LIMIT_BYTES`, simulates working-set memory demand in Redis | `/healthz`, `/readyz`, `/api/claims/adjudicate`, `/internal/fault` | Chaos Scenario 1 | §17 |
| `services/provider-directory/Dockerfile` | Clinic search service image (`v1.0.0-good`) | Uvicorn port `8083` | `provider-directory` Deployment (`58083`) | §17 |
| `services/provider-directory/main.py` | Concurrency slot (`asyncio.Semaphore(2)`, `0.22s` simulated work under fault) exhibiting genuine scale-out speedup `1 -> 3` pods | `/healthz`, `/readyz`, `/api/providers/search`, `/internal/fault` | Chaos Scenario 3 | §17 |

### 2.6 Infrastructure, Compose, Kubernetes, Terraform, Chaos, Runbooks, CI & Operations Scripts
| Scope / Directory | Paths | Purpose |
|---|---|---|
| Compose & Observability (`infra/compose/`) | `infra/compose/docker-compose.yml`, `infra/compose/postgres-init/01-init.sql`, `infra/compose/otel/otel-collector-config.yaml`, `infra/compose/prometheus/prometheus.yml`, `infra/compose/prometheus/alert_rules.yml`, `infra/compose/alertmanager/alertmanager.yml.tmpl`, `infra/compose/keycloak/realm-aegisops.json.tmpl` | Isolated backing services (`53000`, `55317/55318`, `55432`, `56379`, `58080`, `59090`, `59093`), `aegisops_langfuse` bootstrap, traffic-guarded alerts, authenticated webhook template, Keycloak PKCE realm |
| Kubernetes & Terraform (`infra/k8s/`, `infra/terraform/`) | `infra/k8s/kind-config.yaml`, `infra/k8s/workloads/postgres-claims-db.yaml`, `infra/k8s/workloads/redis-session-cache.yaml`, `infra/k8s/workloads/eligibility-api.yaml`, `infra/k8s/workloads/claims-processor.yaml`, `infra/k8s/workloads/provider-directory.yaml`, `infra/k8s/workloads/kube-state-metrics.yaml`, `infra/terraform/main.tf`, `infra/terraform/variables.tf`, `infra/terraform/outputs.tf` | `kind-aegisops-local` cluster (`30081–30084` -> `58081–58084`), Terraform-owned namespaces (`aegisops-healthcare`, `aegisops-system`), least-privilege `aegisops-remediator` RBAC, quotas, `/healthz` probes, Downward API limits |
| Chaos & Load (`chaos/`) | `chaos/run_scenario.py`, `chaos/k6/webhook_burst_and_api.js` | Live 4-scenario orchestrator (control intervals, TOTP approval, 60s watchdog verification) + `k6` 15-VU burst & `/readyz` benchmark |
| Runbook Knowledge Base (`runbooks/`) | `runbooks/RB-001-claims-processor-oom.md` .. `runbooks/RB-015-schema-migration-lock-contention.md`, `runbooks/PM-001-eligibility-pool-exhaustion-postmortem.md` .. `runbooks/PM-003-canary-release-regression-postmortem.md` | `15` deterministic/escalate-only runbooks + `3` synthetic postmortems indexed in Postgres FTS + pgvector (`RB-011` DB failover boundary) |
| Lifecycle Scripts (`scripts/`) | `scripts/_common.ps1`, `scripts/setup.ps1`, `scripts/doctor.ps1`, `scripts/up.ps1`, `scripts/migrate.ps1`, `scripts/seed.ps1`, `scripts/test.ps1`, `scripts/demo.ps1`, `scripts/logs.ps1`, `scripts/down.ps1`, `scripts/reset.ps1`, `scripts/send_synthetic_alert.py`, `scripts/verify_docs.py` | End-to-end operator CLI, secret generator, synthetic webhook test injector, and automated doc-to-source path/env verifier |
| CI/CD Workflows (`.github/workflows/`) | `.github/workflows/ci.yml`, `.github/workflows/live-cluster-chaos.yml` | Fast Postgres/Redis/Node/Python CI + manual live cluster & Ollama chaos definition (not executed on GitHub runner) |
| Planning & Documentation (`./`, `.planning/`, `docs/`) | `README.md`, `OVERALL_FLOW.md`, `workingflow.md`, `.env.example`, `.gitignore`, `.planning/STATE.md`, `.planning/REQUIREMENTS.md`, `.planning/DECISIONS.md`, `.planning/BLOCKERS.md`, `.planning/phases/00-discovery-and-foundation.md` .. `.planning/phases/05-chaos-infrastructure-and-release.md`, `docs/ARCHITECTURE.md`, `docs/CODEMAP.md`, `docs/API.md`, `docs/DATA_MODEL.md`, `docs/SECURITY.md`, `docs/RUNBOOK.md`, `docs/DEPENDENCIES.md`, `docs/TESTING.md`, `docs/DEMO.md`, `docs/VERIFICATION_REPORT.md`, `docs/evidence/.gitkeep`, `docs/evidence/phase-00-foundation.txt` .. `docs/evidence/phase-04-auth-console.txt`, `docs/evidence/chaos-scenarios-report.json`, `docs/evidence/k6-summary.json`, `docs/evidence/ragas-evaluation.json` | Planning ledgers, architecture/API/security specs, runnable guides, and raw evidence bundles (`phase-05-chaos-release.txt` generated at final Phase 5 gate) |
