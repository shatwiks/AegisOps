# AegisOps — Complete Project Status & Engineering Report

> **Report Snapshot Date:** `2026-11-17T17:49:00+05:30`  
> **Repository:** `https://github.com/shatwiks/AegisOps` (`main` @ `c074375`, `224` tracked files)  
> **Overall Status:** `COMPLETE & VERIFIED` across Core Control Plane (`Phases 0–5`), Interactive Showcase Upgrade (`Phases 00–07`), Recruiter [README.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/README.md), and Hardened GitHub Actions CI ([ci.yml](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/.github/workflows/ci.yml)).  
> **Disclaimer:** AegisOps is an independent engineering demonstration operating strictly on synthetic healthcare workloads inside a local `kind` Kubernetes cluster (`kind-aegisops-local`). It implies no affiliation with any healthcare company and carries no HIPAA/HITRUST compliance or clinical production readiness.

---

## 1. Executive Summary (Technical & Non-Technical)

**AegisOps** is a locally runnable **autonomous AIOps control plane, CMDB dependency blast-radius engine, and self-healing Kubernetes operator**. It monitors three simulated healthcare microservices (`eligibility-api`, `claims-processor`, and `provider-directory`), automatically scrubs sensitive PII and secrets before storing or sending payloads to AI models, maps upstream/downstream outage impact via PostgreSQL dependency graphs, diagnoses root causes from internal engineering runbooks via hybrid vector/lexical RAG, enforces fail-closed human-in-the-loop approvals for risky mutations, and proves health recovery over an unbroken 60-second window before resolving any incident.

### Key Project Outcomes
- **100% Core & Showcase Delivery:** Every planned feature across **Base Phases 0–5** and **Showcase Phases 00–07** is implemented and verified.
- **Zero Cloud AI Cost:** Runs 100% locally on Ollama (`nomic-embed-text:latest` + `llama3.2:3b`) paired with deterministic server-side policy guardrails so model errors cannot execute unsafe actions.
- **Dual-Audience Experience:** Includes unauthenticated **Visitor Mode** (`Executive Overview` vs. `Technical Deep-Dive`), Guided Tour, Recorded Incident Replay, live Privacy Scrubber Playground, Hybrid Search Tester, and Markdown/PDF Postmortem exports alongside Keycloak OIDC + TOTP MFA operator workflows.
- **Verified Green CI/CD:** Live GitHub Actions **Run #10** (`44080690721`) passed every build, lint, typecheck, migration, documentation link, pytest, and secret-scan check on `ubuntu-24.04`.

---

## 2. Git Commit & Release Timeline

| Commit | Summary | Area |
|---|---|---|
| `1b46e1d` | `feat(aegisops): complete AIOps control plane & interactive showcase upgrade` | Full Phases `0–5` + Showcase `00–07` codebase pushed to `origin/main` |
| `c336d71` | `ci: prevent uv venv collision, guard psql, add docs check, and refine secret scan` | Fixed `setup-uv@v5` `.venv` activation conflict, added `scripts/verify_docs.py` to CI |
| `6126943` | `build(backend): configure explicit setuptools package discovery for app` | Added `[build-system]` + `[tool.setuptools.packages.find]` (`app*`) in `backend/pyproject.toml` |
| `2a1dff8` | `fix(docs-check): skip gitignored build/cache folder mentions on fresh checkouts` | Excluded generated dirs (`frontend/node_modules/`, `frontend/dist/`, `infra/terraform/.terraform/`) from `verify_docs.py` |
| `bb995c2` | `docs(readme): add recruiter-ready README with animated SVG visuals and dual-audience overview` | Added `docs/assets/aegisops-hero.svg`, `docs/assets/aegisops-lifecycle.svg`, and upgraded `README.md` |
| `c074375` | `ci: harden workflows with pinned ubuntu-24.04, retry-safe DB init, YAML gate, concurrency & LF rules` | Pinned OS, asyncpg extension retry loop, `.gitattributes`, concurrency/timeouts, fixed `live-cluster-chaos.yml` |

---

## 3. Complete Phase-by-Phase Delivery Record

### 3.1 Core Control Plane (Base Phases `0–5`)

| Phase | Scope & Capabilities Delivered | Verification Status & Evidence |
|---|---|---|
| **Phase 0** — Discovery & Runnable Foundation | FastAPI ASGI control plane (`backend/app/main.py`), Compose Postgres + `pgvector` (`55432`) & Redis (`56379`), health/readiness probes (`/healthz`, `/readyz`), React + TypeScript + Vite console scaffold | `PASS` (`11/11` initial tests, [phase-00-foundation.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/docs/evidence/phase-00-foundation.txt)) |
| **Phase 1** — CMDB, Incidents & Privacy Boundary | Alembic DDL (`0001_initial_schema.py`), cycle-safe Postgres recursive CTE CMDB blast radius (`8` assets, `9` edges), `P1–P4` deterministic severity engine, fail-closed edge PII scrubber (`scrubber.py`), HMAC/Bearer webhook auth, append-only `audit_records`, transactional `OutboxJob` queue | `PASS` (`42/42` tests, PII `P=1.0/R=1.0`, [phase-01-cmdb-privacy.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/docs/evidence/phase-01-cmdb-privacy.txt)) |
| **Phase 2** — Hybrid RAG & Refusal Gate | `18` healthcare Markdown runbooks/postmortems (`runbooks/RB-*.md`, `runbooks/PM-*.md`) embedded via Ollama `nomic-embed-text:latest` (`768` dims), `pgvector` HNSW cosine + GIN `tsvector` + RRF (`k=60`) hybrid search, structured Ollama `llama3.2:3b` diagnosis (`diagnosis.py`), server-side policy engine & deterministic refusal gate (`engine.py`) | `PASS` (`50/50` tests, live Ollama + injection refusal verified, [phase-02-hybrid-rag-refusal.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/docs/evidence/phase-02-hybrid-rag-refusal.txt)) |
| **Phase 3** — Durable Remediation & Verified Recovery | Local `kind-aegisops-local` cluster, Terraform namespaces/RBAC/quotas (`infra/terraform/`), synthetic workloads (`services/{eligibility-api,claims-processor,provider-directory}` + Postgres/Redis/kube-state-metrics), OTel/Prometheus/Alertmanager, Redis target lease locking (`locks.py`), outbox `SKIP LOCKED` worker (`runner.py`), K8s Python SDK executor + crash reconciler (`executor.py`), `60s` sustained recovery watchdog (`watchdog.py`) | `PASS` (`55/55` tests, live Kind scale & crash recovery verified, [phase-03-remediation-recovery.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/docs/evidence/phase-03-remediation-recovery.txt)) |
| **Phase 4** — SSO, Step-Up Approval & SRE Console | Keycloak 26 OIDC S256 PKCE (`oidc.py`, `pkce.ts`), RBAC enforcement, `pyotp` encrypted TOTP enrollment & single-use replay-protected step-up approvals bound to K8s `resourceVersion` (`totp.py`, `approvals.py`), cursor-resumable SSE (`stream.py`), `@xyflow/react` blast-radius graph (`TopologyGraph.tsx`), Playwright Chromium E2E suite | `PASS` (5-way concurrent approval race & Playwright PKCE + SSE verified, [phase-04-auth-console.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/docs/evidence/phase-04-auth-console.txt)) |
| **Phase 5** — Real Chaos, CI, Evaluation & Final Docs | Langfuse v2 redacted trace observability (`langfuse_tracer.py`), `4` live end-to-end Kubernetes chaos scenarios (`chaos/run_scenario.py`), `k6` webhook burst benchmark (`webhook_burst_and_api.js`), offline Ragas evaluation (`ragas_eval.py`), Graphify knowledge graph map (`docs/CODEMAP.md`), complete docs & GitHub Actions workflows | `PASS` (`4/4` chaos resolved, `240/240` k6 checks, Ragas measured, [phase-05-chaos-release.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/docs/evidence/phase-05-chaos-release.txt)) |

### 3.2 Interactive Showcase Upgrade (Phases `00–07`)

| Phase | Showcase Features Implemented (`Features A–O`) | Verification Status |
|---|---|---|
| **Showcase Phase 00** | Showcase audit & API/DB/UI contracts; Alembic `0002_showcase_upgrade.py` migration plan | `VERIFIED` ([00-audit-and-contracts.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/.planning/showcase/phases/00-audit-and-contracts.md)) |
| **Showcase Phase 01** | Unauthenticated `visitor` readiness overview (`/api/v1/showcase/overview`, `/readiness`), strict `operator+` RBAC, Pause Automation control (`controls.py`), scoped Baseline Reset preview/execute preserving audit logs | `VERIFIED` (`test_showcase_readiness_and_controls.py` `2/2` passed) |
| **Showcase Phase 02** | Default `Hide Test Runs` queue toggle, SQL tab counts (`active`/`resolved`/`escalated`/`failed`/`all`), search/sort/pagination, trusted `X-AegisOps-Provenance`, SSE `after_seq`, 7-step lifecycle stepper & live `"Checking service stability: X of 60 seconds observed"` | `VERIFIED` (`test_showcase_queue_and_lifecycle.py` `2/2` passed) |
| **Showcase Phase 03** | 5-scenario Chaos Lab (`ChaosLabPanel.tsx`, adding `pii_leak_and_db_failure`), `409 Conflict` dependent-service mutex, SSRF-protected live Business Probes (`BusinessProbeCard.tsx`), Guided Tour (`GuidedTourBar.tsx`) | `VERIFIED` (`test_showcase_scenarios_and_probes.py` `1/1` passed) |
| **Showcase Phase 04** | Zero-persistence Privacy Scrubber Playground (`8 KiB` cap, `30 req/60s` limiter), Captured Prompt & Policy Explanation Inspector (`PrivacyPromptDrawer.tsx`, `DecisionExplanationCard.tsx`), `.md` Runbook Upload pipeline (`UPLOADED -> VALIDATING -> INDEXING -> READY` with XSS/schema rejection) & Hybrid Search Tester (`RunbookKnowledgePanel.tsx`), live K8s `k8s_live` deployment stats on `/api/v1/topology` | `VERIFIED` (`test_showcase_inspectors_and_runbooks.py` `1/1` passed) |
| **Showcase Phase 05** | Isolated Recorded Replay (`ReplayController.tsx`, `replay.py`) + Markdown (`.md`) and pure-Python multi-page FlateDecode PDF (`.pdf`) Postmortem & Escalation exporters (`postmortem.py`, `pdf_renderer.py`) | `VERIFIED` (`test_showcase_replay_and_postmortem.py` `1/1` passed) |
| **Showcase Phase 06** | Executive Overview vs. Technical Deep-Dive UI mode toggle (`App.tsx`), Engineering Evidence view (`EngineeringEvidenceView.tsx`), visual layout & accessibility polish | `VERIFIED` (`tsc --noEmit` + Vite `68` modules build clean) |
| **Showcase Phase 07** | Full integrated gate (`65/65` pytest including `test_showcase_browser.py`), Graphify knowledge-graph refresh, and documentation verification | `VERIFIED` ([showcase-test-gate.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/docs/evidence/showcase-test-gate.txt)) |

---

## 4. Complete Runtime Topology & Port Registry

| Component | Technology | Host Binding / Port | Responsibility |
|---|---|---|---|
| **FastAPI Control Plane** | Python 3.12 + FastAPI (`backend/app/main.py`) | `127.0.0.1:58000` | REST/SSE API (`/api/v1/*`), webhooks, RBAC, probes, exports, `/healthz`, `/readyz`, `/metrics` |
| **Durable Outbox Worker** | Python Asyncio (`backend/app/worker/runner.py`) | Host process (`Semaphore(4)`) | `SKIP LOCKED` job claiming, RAG triage, Redis locking, K8s remediation, 60s watchdog |
| **React SRE Console** | React 18 + TS + Vite 6 (`frontend/`) | `127.0.0.1:55173` | Dual-mode UI (`Visitor` + PKCE), `@xyflow/react` CMDB graph, Chaos Lab, Replay, Knowledge Base |
| **PostgreSQL 16 + pgvector** | Docker (`aegisops-postgres`) | `127.0.0.1:55432` | Incidents, CMDB graph, outbox jobs, TOTP replay records, `pgvector` HNSW + FTS runbooks |
| **Redis 7.4** | Docker (`aegisops-redis`) | `127.0.0.1:56379` | Distributed K8s target leases (`SET NX PX` + Lua fencing) & rate-limit state |
| **Keycloak 26 OIDC** | Docker (`aegisops-keycloak`) | `127.0.0.1:58080` | Realm `aegisops`, S256 PKCE client `aegisops-console`, `viewer` / `operator` / `approver` roles |
| **Ollama Local AI** | Host runtime (`ollama serve`) | `127.0.0.1:11434` | Local `nomic-embed-text:latest` (`768` dims) & `llama3.2:3b` JSON inference |
| **Prometheus** | Docker (`aegisops-prometheus`) | `127.0.0.1:59090` | Scrapes demo services, K8s metrics, FastAPI; evaluates traffic-guarded alert rules |
| **Alertmanager** | Docker (`aegisops-alertmanager`) | `127.0.0.1:59093` | Sends signed HMAC/Bearer alert webhooks to FastAPI |
| **Langfuse v2** | Docker (`aegisops-langfuse`) | `127.0.0.1:53000` | Stores scrubbed LLM triage traces & offline evaluations |
| **OpenTelemetry Collector** | Docker (`aegisops-otel-collector`) | `127.0.0.1:55317` / `55318` | Ingests OTLP gRPC/HTTP telemetry from healthcare services |
| **Target Kind Cluster** | Kubernetes (`kind-aegisops-local`) | Kube API `64295`; NodePorts `58081–58084` | Namespaces `aegisops-healthcare` (`eligibility-api`, `claims-processor`, `provider-directory`, `postgres-claims-db`, `redis-session-cache`) & `aegisops-system` (`kube-state-metrics`) |

---

## 5. Complete Repository File & Module Inventory (`224` Tracked Files)

### 5.1 Backend Control Plane (`backend/app/`)
- **Entry & Config**: `backend/app/main.py`, `backend/app/config.py`, `backend/app/db.py`, `backend/app/redis_client.py`, `backend/app/models/entities.py`, `backend/pyproject.toml`, `backend/requirements.lock`, `backend/migrations/env.py`, `backend/migrations/versions/0001_initial_schema.py`, `backend/migrations/versions/0002_showcase_upgrade.py`
- **API Routers (`backend/app/api/`)**: `auth.py`, `approvals.py`, `incidents.py`, `metrics.py`, `runbooks.py`, `showcase.py`, `stream.py`, `topology.py`, `webhooks.py`
- **Security, Identity & Privacy**: `backend/app/auth/oidc.py`, `backend/app/auth/totp.py`, `backend/app/privacy/scrubber.py`
- **CMDB, Playbooks, Policy & State**: `backend/app/cmdb/graph.py`, `backend/app/domain/state_machine.py`, `backend/app/playbooks/registry.py`, `backend/app/policy/engine.py`
- **Hybrid RAG & Observability**: `backend/app/rag/embeddings.py`, `backend/app/rag/retriever.py`, `backend/app/rag/diagnosis.py`, `backend/app/observability/langfuse_tracer.py`, `backend/app/observability/ragas_eval.py`
- **Kubernetes Execution & Worker**: `backend/app/k8s/executor.py`, `backend/app/worker/locks.py`, `backend/app/worker/runner.py`, `backend/app/worker/watchdog.py`
- **Seeders & Showcase Engine (`backend/app/seed/`, `backend/app/showcase/`)**: `cmdb_seed.py`, `runbook_seed.py`, `controls.py`, `pdf_renderer.py`, `postmortem.py`, `probes.py`, `replay.py`, `scenarios.py`

### 5.2 Frontend SRE Console (`frontend/`)
- **Core App**: `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/styles.css`, `frontend/src/types.ts`, `frontend/src/lib/pkce.ts`
- **13 UI Feature Components (`frontend/src/components/`)**:
  - `BusinessProbeCard.tsx`, `ChaosLabPanel.tsx`, `DecisionExplanationCard.tsx`, `EngineeringEvidenceView.tsx`, `GuidedTourBar.tsx`, `IncidentDetail.tsx`, `LifecycleStepper.tsx`, `MetricsDashboard.tsx`, `PrivacyPromptDrawer.tsx`, `ReplayController.tsx`, `RunbookKnowledgePanel.tsx`, `TopologyGraph.tsx`, `TotpModal.tsx`

### 5.3 Synthetic Microservices, Infrastructure, Chaos & Runbooks
- **Simulated Healthcare Workloads (`services/`)**: `services/eligibility-api/main.py` + `Dockerfile`, `services/claims-processor/main.py` + `Dockerfile`, `services/provider-directory/main.py` + `Dockerfile`, `services/shared/base_service.py`, `services/requirements.txt`
- **Infrastructure & Config (`infra/`)**: `infra/k8s/kind-config.yaml`, `infra/k8s/workloads/{eligibility-api,claims-processor,provider-directory,postgres-claims-db,redis-session-cache,kube-state-metrics}.yaml`, `infra/terraform/{main,outputs,variables}.tf`, `infra/compose/docker-compose.yml`, `infra/compose/{alertmanager/alertmanager.yml.tmpl,keycloak/realm-aegisops.json.tmpl,otel/otel-collector-config.yaml,postgres-init/01-init.sql,prometheus/prometheus.yml,prometheus/alert_rules.yml}`
- **Chaos & Benchmarks (`chaos/`)**: `chaos/run_scenario.py`, `chaos/k6/webhook_burst_and_api.js`
- **Knowledge Corpus (`runbooks/`)**: `15` runbooks (`RB-001` through `RB-015`) + `3` synthetic postmortems (`PM-001` through `PM-003`)
- **Lifecycle Automation (`scripts/`)**: `setup.ps1`, `doctor.ps1`, `up.ps1`, `migrate.ps1`, `seed.ps1`, `test.ps1`, `demo.ps1`, `logs.ps1`, `down.ps1`, `reset.ps1`, `send_synthetic_alert.py`, `verify_docs.py`, `_common.ps1`
- **CI/CD & Git Hygiene**: `.github/workflows/ci.yml`, `.github/workflows/live-cluster-chaos.yml`, `.gitattributes`

### 5.4 Automated Test Suite (`backend/tests/`, `20` Test Modules / `65` Executed Items)
- **Unit Tests (`32` cases)**: `backend/tests/unit/{test_config,test_policy_refusal,test_scrubber,test_state_machine}.py`
- **Integration Tests (`31` cases)**: `backend/tests/integration/{test_foundation_health,test_cmdb_graph,test_alertmanager_webhook,test_hybrid_rag,test_ollama_diagnosis,test_locks_and_reconciler,test_k8s_remediation_kind,test_auth_and_approvals,test_recovery_watchdog,test_showcase_readiness_and_controls,test_showcase_queue_and_lifecycle,test_showcase_scenarios_and_probes,test_showcase_inspectors_and_runbooks,test_showcase_replay_and_postmortem}.py`
- **Playwright Chromium E2E (`2` suites)**: `backend/tests/e2e/{test_browser_console,test_showcase_browser}.py`

---

## 6. Security & Zero-Trust Engineering Controls

1. **Fail-Closed Edge Privacy Scrubber (`backend/app/privacy/scrubber.py`)**: Redacts SSNs, Member IDs, emails, bearer/JWT tokens, IPv4 addresses, and contextual patient names synchronously prior to database persistence, LLM prompt assembly, or Langfuse trace export (`precision = 1.0`, `recall = 1.0`).
2. **Webhook Authenticity & Deduplication (`backend/app/api/webhooks.py`)**: Enforces HMAC-SHA256 + Bearer verification on Alertmanager deliveries and atomic Postgres partial-unique deduplication.
3. **Keycloak OIDC PKCE & RBAC (`backend/app/auth/oidc.py`)**: Enforces `visitor` (unauthenticated read-only), `viewer`, `operator`, and `approver` tiers server-side regardless of UI presentation mode.
4. **Action-Bound TOTP MFA & Replay Defense (`backend/app/auth/totp.py`)**: High-risk remediations (`memory_limit_increase_bounded`, `deployment_image_rollback`) require `approver` role + Fernet-encrypted `pyotp` code verification consumed atomically against incident ID, playbook ID, parameter hash, target UID, and Kubernetes `resourceVersion`.
5. **Server-Authoritative Policy & Rollback Guard (`backend/app/policy/engine.py`)**: Never trusts image tags from LLM output (`deployment_image_rollback` strictly resolves `Asset.known_good_image` from CMDB); refuses unknown assets, low similarity, out-of-bounds parameters, malformed model JSON, and stateful database failover (`RB-011`).
6. **SSRF, XSS & Abuse Protections**: Private-network SSRF rejection on Business Probes (`400`), `8 KiB` body cap + `30 req/60s` rate limiting on Privacy Playground (`413`/`429`), and strict `<script>` / unknown-playbook / risk-downgrade rejection on `.md` runbook uploads.

---

## 7. Verified Test, Benchmark & CI/CD Evidence

| Evidence Source | Outcome | Key Quantitative Measurements |
|---|---|---|
| **GitHub Actions CI (`ci.yml`)** | `PASS` | **Run #10** ([44080690721](https://github.com/shatwiks/AegisOps/actions/runs/44080690721)) on commit `c074375`: `ubuntu-24.04`, all job steps passed (`backend-and-frontend`) |
| **Final Showcase Test Gate (`.\scripts\test.ps1`)** | `PASS` | `ExitCode: 0`, `65 / 65` Pytest passed in `220.05s`, Ruff clean, Mypy `50` files clean, Vite `68` modules built in `5.06s` ([showcase-test-gate.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/docs/evidence/showcase-test-gate.txt)) |
| **Chaos Scenarios (`1–5`)** | `PASS` | Scenarios `1–4` (`claims_oom`, `eligibility_pool`, `provider_cpu`, `eligibility_canary`) verified fault -> remediate -> `60s` watchdog -> `RESOLVED` ([chaos-scenarios-report.json](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/docs/evidence/chaos-scenarios-report.json)); Scenario `5` (`pii_leak_and_db_failure`) scrubbed PII & safely escalated `RB-011` (`test_showcase_scenarios_and_probes.py`) |
| **`k6` Load & Burst Test** | `PASS` | `240 / 240` checks (`100%`), `0.00%` `http_req_failed` across `120` requests (`5–15` VUs), `p95 = 1109.0 ms` (`< 1500 ms` target) ([k6-summary.json](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/docs/evidence/k6-summary.json)) |
| **Local `Ragas` RAG Eval** | `MEASURED` | `context_recall = 0.8586`, `faithfulness = 0.7083` over 5 canonical scenarios with local `llama3.2:3b` + `nomic-embed-text:latest` (`3/5` numeric scores, `2/5` `NaN` from 3B NLI variance — [ragas-evaluation.json](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/docs/evidence/ragas-evaluation.json)) |
| **Documentation Integrity (`verify_docs.py`)** | `PASS` | `14 / 14` checked documentation files passed on both Windows and clean Linux checkout with `0` broken path/env references |

---

## 8. Live Environment Snapshot (At Report Time: `2026-11-17T17:45+05:30`)

| Runtime Layer | Current State | Notes |
|---|---|---|
| **Docker & Kind Infrastructure** | **UP / HEALTHY** | `aegisops-postgres` (`55432`), `aegisops-redis` (`56379`), `aegisops-keycloak` (`58080`), `aegisops-prometheus` (`59090`), `aegisops-alertmanager` (`59093`), `aegisops-langfuse` (`53000`), `aegisops-otel-collector`, `aegisops-local-control-plane` (`kind`) all running |
| **Host Application Daemons** | **STOPPED** | Ports `58000` (FastAPI), `55173` (Vite Console), `11434` (`ollama serve`), and background Outbox Worker were stopped by an earlier host restart (`TcpTestSucceeded = False`); run `.\scripts\up.ps1` to resume interactive UI |

---

## 9. Known Boundaries & Unexecuted Operations

1. **Manual Chaos Workflow on GitHub Runners ([live-cluster-chaos.yml](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps%2C%20CMDB%20Blast-Radius%20%26%20Self-Healing%20Kubernetes%20Control/.github/workflows/live-cluster-chaos.yml))**: Uses `workflow_dispatch`, hardened for Ubuntu 24.04 (`setup-uv@v5`, `kubectl`, `--with-deps` Playwright, Ollama readiness polling), and validated for YAML syntax cleanly—not triggered on remote hosted GitHub runners (the complete live cluster suite runs and passes locally).
2. **Destructive Teardown (`scripts/reset.ps1`)**: Scoped cleanly to `kind-aegisops-local` and AegisOps Compose volumes; intentionally left unexecuted to preserve verified local database/cluster state (while non-destructive UI `Restore Demo Baseline` was verified end-to-end).
3. **Small Local Model NLI Variance**: `llama3.2:3b` yields occasional JSON/NLI formatting variance (`2/5` `NaN` in Ragas), reinforced by design via strict Pydantic validation and deterministic server-side refusal logic.
4. **Non-Production / Synthetic Scope**: Healthcare data, alerts, and runbooks are synthetic demonstration artifacts only.
