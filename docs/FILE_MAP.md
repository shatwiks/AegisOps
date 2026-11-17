# AegisOps Complete File Map (`docs/FILE_MAP.md`)

> Authoritative map of authored source, infrastructure, test, runbook, script, and documentation files in this repository. Excludes generated build/cache directories (`.venv/`, `node_modules/`, `frontend/dist/`, `.local/`, `__pycache__/`).

## 1. Backend Control Plane (`backend/app/`)

| Path | Responsibility | Feature / Phase |
|---|---|---|
| `backend/app/__init__.py` | Package version `__version__` | Base Phase 0 |
| `backend/app/config.py` | Validated `Settings` & `.env` loader (`demo_internal_fault_token`, OIDC, Ollama, K8s bounds) | Phase 0 + Showcase 01 |
| `backend/app/db.py` | Async SQLAlchemy engine, `async_sessionmaker`, `/readyz` PostgreSQL & pgvector checks | Phase 0 |
| `backend/app/redis_client.py` | Async Redis client factory and ping probe | Phase 0 |
| `backend/app/main.py` | FastAPI lifespan, CORS, correlation IDs, `/healthz`, `/readyz`, `/metrics`, mounts all 8 API routers | Phase 0–4 + Showcase 01/04 |
| `backend/app/models/__init__.py` | Re-exports ORM entities | Phase 1 |
| `backend/app/models/entities.py` | 13 SQLAlchemy + pgvector ORM tables (`Asset`, `AssetDependency`, `Incident`, `IncidentEvent`, `Runbook`, `ApprovalRequest`, `ExecutionAttempt`, `AuditRecord`, `OutboxJob`, `UserTotpSecret`, `DemoRun`, `BusinessProbeSample`, `SystemControlFlag`) | Phase 1 + Showcase 01 |
| `backend/app/privacy/scrubber.py` | Deterministic regex + allowlist PHI/PII/secret scrubber (`scrub_text`, `scrub_alertmanager_payload`, `evaluate_redaction_corpus`) | Phase 1 |
| `backend/app/cmdb/graph.py` | Cycle-safe recursive CTE blast-radius walker (`get_blast_radius`) & P1–P4 `compute_severity` | Phase 1 |
| `backend/app/domain/state_machine.py` | Canonical `IncidentState`, `ALLOWED_TRANSITIONS`, row-locked `transition_incident` | Phase 1 |
| `backend/app/playbooks/__init__.py`, `backend/app/playbooks/registry.py` | Server-owned `PLAYBOOK_REGISTRY` (`5` playbooks) & strict `validate_playbook_for_asset` | Phase 2 |
| `backend/app/rag/__init__.py`, `backend/app/rag/embeddings.py` | Local Ollama `/api/embed` (`768` dims) & index model/digest validation | Phase 2 |
| `backend/app/rag/retriever.py` | Hybrid PostgreSQL GIN `TSVECTOR` + `pgvector` HNSW cosine search with RRF (`k=60`) & `READY` filter | Phase 2 + Showcase 04 |
| `backend/app/rag/diagnosis.py` | XML-delimited Ollama structured diagnosis & captured prompt snapshot builder (`generate_diagnosis_with_record`) | Phase 2 + Showcase 01 |
| `backend/app/policy/__init__.py`, `backend/app/policy/engine.py` | Server-controlled refusal, MFA gating & cosine threshold (`0.78`) policy engine (`evaluate_remediation_policy`) | Phase 2 |
| `backend/app/k8s/__init__.py`, `backend/app/k8s/executor.py` | Official K8s Python SDK executor (`KubernetesExecutor`), allowlisted patch/reconciliation & `patch_demo_workload` | Phase 3 + Showcase 01 |
| `backend/app/worker/__init__.py`, `backend/app/worker/locks.py` | Single-instance Redis `SET NX PX` lease with Lua ownership renewal/release | Phase 3 |
| `backend/app/worker/watchdog.py` | Sustained recovery watchdog (`60s` default) over K8s + `/readyz` + PromQL + tick progress callbacks | Phase 3 + Showcase 01 |
| `backend/app/worker/runner.py` | Durable `FOR UPDATE SKIP LOCKED` outbox worker (`asyncio.Semaphore(4)`, automation pause hold, scenario & indexing dispatch) | Phase 3 + Showcase 01/03/04 |
| `backend/app/auth/__init__.py`, `backend/app/auth/oidc.py`, `backend/app/auth/totp.py` | Keycloak RS256 JWKS verification, PKCE exchange, `optional_authenticate_request`, `require_role`, Fernet-encrypted `pyotp` MFA | Phase 4 + Showcase 01 |
| `backend/app/api/__init__.py` | API package marker | Phase 0 |
| `backend/app/api/webhooks.py` | HMAC/Bearer Alertmanager webhook ingestion, trusted `X-AegisOps-Provenance`, active `DemoRun` linking | Phase 1 + Showcase 02 |
| `backend/app/api/auth.py` | OIDC PKCE config/exchange/me/logout + TOTP enrollment/verification endpoints | Phase 4 |
| `backend/app/api/approvals.py` | Action-bound + resourceVersion-drift-checked high-risk approval/denial routes | Phase 4 |
| `backend/app/api/incidents.py` | Filtered/sorted/paginated incident queue, 7-step lifecycle, `why_this_action`, prompt inspector, `.md`/`.pdf` exports | Phase 4 + Showcase 02/04/05 |
| `backend/app/api/topology.py` | `visitor+` CMDB topology graph, cached read-only `k8s_live` deployment facts, & selected incident diff | Phase 4 + Showcase 04 |
| `backend/app/api/metrics.py` | Scoped MTTD/MTTR percentile distributions, business value counters & optional manual baseline comparison | Phase 4 + Showcase 06 |
| `backend/app/api/stream.py` | Authenticated SSE stream with `after_seq` / `Last-Event-ID` delta catch-up & `demo_runs` snapshots | Phase 4 + Showcase 02 |
| `backend/app/api/runbooks.py` | Runbook browser, security-validated `.md` upload (`64 KiB`, XSS/playbook guards), retry-index, Hybrid Search tester | Showcase 04 |
| `backend/app/api/showcase.py` | Showcase endpoints: readiness, controls, baseline reset, 5 scenarios, business probes, privacy preview, replays, overview & evidence | Showcase 01/03/04/05/06 |
| `backend/app/showcase/__init__.py`, `controls.py` | Global & per-scenario readiness (`Ready`/`Degraded`/`Blocked`), automation pause switch, idempotent preview/execute reset | Showcase 01 |
| `backend/app/showcase/probes.py` | SSRF-safe allowlisted semantic business transaction recovery probes (`BusinessProbeSample`) | Showcase 03 |
| `backend/app/showcase/scenarios.py` | 5-scenario Chaos Lab catalog, lock/conflict exclusion, durable `DemoRun` orchestration & narration state | Showcase 03 |
| `backend/app/showcase/replay.py` | Read-only chronological Recorded Incident Replay frame reconstruction (`captured_live_run` + `illustrative_fixture`) | Showcase 05 |
| `backend/app/showcase/pdf_renderer.py`, `postmortem.py` | Unified postmortem snapshot builder, HTML-safe `.md` formatter & pure-Python zlib `%PDF-1.4` writer | Showcase 05 |
| `backend/app/observability/__init__.py`, `langfuse_tracer.py`, `ragas_eval.py` | Scrubbed Langfuse v2 trace exporter & local Ollama Ragas evaluator | Phase 5 |
| `backend/app/seed/__init__.py`, `cmdb_seed.py`, `runbook_seed.py` | Idempotent 8-asset/9-edge CMDB seeder & 18-document runbook/postmortem embedding seeder | Phase 1/2 |

## 2. Backend Migrations, Tooling & Automated Tests (`backend/`)

| Path | Responsibility |
|---|---|
| `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/script.py.mako` | Async Alembic runner configuration & migration template |
| `backend/migrations/versions/0001_initial_schema.py` | Initial 10-table PostgreSQL + pgvector HNSW/GIN + append-only trigger schema |
| `backend/migrations/versions/0002_showcase_upgrade.py` | Adds Showcase columns (`source_provenance`, `demo_run_id`, `sanitized_prompt_json`, `verification_state_json`, `sequence_num`, `indexing_status`, etc.) + `demo_runs`, `business_probe_samples`, `system_control_flags` |
| `backend/pyproject.toml`, `backend/requirements.lock` | Ruff, Mypy, Pytest config (`asyncio_mode="auto"`) & 136 pinned Python packages |
| `backend/scripts/run_ragas_eval.py` | Standalone local Ragas Faithfulness & ContextRecall evaluation script -> `docs/evidence/ragas-evaluation.json` |
| `backend/tests/unit/test_{config,policy_refusal,scrubber,state_machine}.py` | Fast unit suites |
| `backend/tests/integration/test_{alertmanager_webhook,auth_and_approvals,cmdb_graph,foundation_health,hybrid_rag,k8s_remediation_kind,locks_and_reconciler,ollama_diagnosis,recovery_watchdog}.py` | Base platform Postgres, Redis, Ollama, Keycloak & `kind-aegisops-local` integration tests |
| `backend/tests/integration/test_showcase_{readiness_and_controls,queue_and_lifecycle,scenarios_and_probes,inspectors_and_runbooks,replay_and_postmortem}.py` | Showcase Phases 01–05 live Postgres, Redis, Ollama, Keycloak & Kind integration tests |
| `backend/tests/e2e/test_browser_console.py`, `backend/tests/e2e/test_showcase_browser.py` | Headless Chromium Playwright E2E tests covering OIDC PKCE, TOTP, Visitor Mode, Replay, Privacy Playground, Hybrid Search, Evidence & Operator flows |

## 3. Frontend SRE Showcase Console (`frontend/`)

| Path | Responsibility |
|---|---|
| `frontend/index.html`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts` | Vite 6 + React 18 + strict TypeScript setup & dev proxy (`55173 -> 58000`) |
| `frontend/src/main.tsx`, `frontend/src/styles.css`, `frontend/src/types.ts`, `frontend/src/lib/pkce.ts` | React mount, responsive WCAG-aware dark SRE CSS (`prefers-reduced-motion`), API contracts, PKCE crypto & CSRF/Blob helpers |
| `frontend/src/App.tsx` | Visitor Mode + OIDC PKCE shell, Executive vs Technical view toggle, Queue Tabs (`Active`/`Resolved`/`Escalated`/`Failed`/`All`) + `Hide Test Runs`, SSE & navigation |
| `frontend/src/components/ChaosLabPanel.tsx` | 5-scenario Chaos Lab cards, Readiness indicator/drawer, Pause Automation switch & Restore Demo Baseline preview modal |
| `frontend/src/components/GuidedTourBar.tsx` | Event-driven Guided Demo narration banner (live or replay, Pause/Skip/Exit, `aria-live`) |
| `frontend/src/components/LifecycleStepper.tsx` | 7-step operational lifecycle tracker with live `"Checking service stability: X of 60 seconds observed"` bar |
| `frontend/src/components/DecisionExplanationCard.tsx` | 7-question "Why This Action?" breakdown separating AI hypothesis, server policy, MFA & observed outcome |
| `frontend/src/components/BusinessProbeCard.tsx` | Allowlisted `Check Patient Eligibility` semantic probe trigger & bounded history |
| `frontend/src/components/PrivacyPromptDrawer.tsx` | Zero-persistence Privacy Scrubber Playground (3 fictional presets) + Sanitized Prompt Inspector |
| `frontend/src/components/RunbookKnowledgePanel.tsx` | Searchable Runbook Browser, validated `.md` Upload (`UPLOADED -> VALIDATING -> INDEXING -> READY/FAILED`) & Test Hybrid Search UI |
| `frontend/src/components/ReplayController.tsx` | Isolated Recorded Incident Replay (`Play`/`Pause`, `1x`/`2x`/`4x`, Step Back/Forward, Seek, `Exit Replay`) |
| `frontend/src/components/EngineeringEvidenceView.tsx` | Reviewer Engineering Evidence page (git/build/migration metadata, Ragas, k6, test gate artifacts & limitations) |
| `frontend/src/components/TopologyGraph.tsx` | `@xyflow/react` blast-radius graph with live K8s replica/image/memory badges, diff markers & Accessible Table View toggle |
| `frontend/src/components/IncidentDetail.tsx` | Incident summary, LifecycleStepper, DecisionExplanationCard, TOTP approval form, `.md`/`.pdf` download buttons & event timeline |
| `frontend/src/components/MetricsDashboard.tsx` | Scope-filtered business value counters, optional user manual baseline comparison & MTTD/MTTR latency distributions |
| `frontend/src/components/TotpModal.tsx` | TOTP enrollment QR generator & confirmation modal for `approver` users |

## 4. Demo Services, Infrastructure, Knowledge Base & Scripts

| Area | Paths |
|---|---|
| Synthetic Microservices | `services/requirements.txt`, `services/shared/{__init__,base_service}.py`, `services/eligibility-api/{Dockerfile,main.py}`, `services/claims-processor/{Dockerfile,main.py}`, `services/provider-directory/{Dockerfile,main.py}` |
| Compose & Telemetry | `infra/compose/docker-compose.yml`, `infra/compose/postgres-init/01-init.sql`, `infra/compose/otel/otel-collector-config.yaml`, `infra/compose/prometheus/{prometheus.yml,alert_rules.yml}`, `infra/compose/alertmanager/alertmanager.yml.tmpl`, `infra/compose/keycloak/realm-aegisops.json.tmpl` |
| Kubernetes & Terraform | `infra/k8s/kind-config.yaml`, `infra/k8s/workloads/{eligibility-api,claims-processor,provider-directory,postgres-claims-db,redis-session-cache,kube-state-metrics}.yaml`, `infra/terraform/{main,variables,outputs}.tf` |
| Chaos & Load Benchmarks | `chaos/run_scenario.py`, `chaos/k6/webhook_burst_and_api.js` |
| SRE Knowledge Corpus | `runbooks/RB-001-claims-processor-oom.md` .. `runbooks/RB-015-schema-migration-lock-contention.md`, `runbooks/PM-001-eligibility-pool-exhaustion-postmortem.md` .. `runbooks/PM-003-canary-release-regression-postmortem.md` |
| Lifecycle Scripts & CI | `scripts/{_common,setup,doctor,up,migrate,seed,test,demo,logs,down,reset}.ps1`, `scripts/{send_synthetic_alert,verify_docs}.py`, `.github/workflows/{ci,live-cluster-chaos}.yml` |
| Planning, Docs & Evidence | `README.md`, `OVERALL_FLOW.md`, `workingflow.md`, `.planning/*`, `.planning/showcase/*`, `docs/*.md`, `docs/evidence/*`, `graphify-out/*` |
