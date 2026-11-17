# AegisOps Showcase Test & Verification Report (`docs/SHOWCASE_TEST_REPORT.md`)

> **Verification Date:** `2026-11-17T11:18+05:30` (`2026-11-17T05:48:07Z`)  
> **Gate Artifact:** [showcase-test-gate.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/evidence/showcase-test-gate.txt)  
> **Overall Status:** `PASS` (`ExitCode: 0`, `65/65` pytest tests passing, `0` skipped, `50/50` mypy files clean, `68` Vite/TS modules built)

---

## 1. Execution Matrix by Environment & Test Category

| Test Suite / Check | Environment & Real Dependencies | Result | Scope & Measured Evidence |
|---|---|---|---|
| **Ruff Static Lint** | Python `.venv` (`backend/pyproject.toml`) | `PASS` | `All checks passed!` across `backend/` |
| **Mypy Strict Typecheck** | Python `.venv` (`backend/pyproject.toml`) | `PASS` | `Success: no issues found in 50 source files` |
| **TypeScript + Vite Build** | Node.js / Vite `6.0.11` (`frontend/`) | `PASS` | `tsc -b` + `vite build`: `68` modules transformed cleanly in `5.06s` |
| **Unit Suites (`backend/tests/unit/`)** | Pure Python + Pydantic (`32` test cases) | `PASS` | `test_config.py`, `test_scrubber.py` (`precision=1.0`, `recall=1.0` on `10` synthetic positive / `4` negative inputs), `test_policy_refusal.py`, `test_state_machine.py` |
| **Mocked Failure Branches** | Unit / Controlled Mocks (`3` test cases) | `PASS` | `test_ollama_diagnosis.py::test_mocked_ollama_malformed_json_and_timeout_refusal`; `test_recovery_watchdog.py` (missing telemetry & interrupted recovery reset) |
| **Base Control-Plane Integration** | Live Postgres 16 + `pgvector`, Redis 7, Ollama (`nomic-embed-text:latest` + `llama3.2:3b`), Keycloak 26, `kind-aegisops-local` | `PASS` | `test_foundation_health.py`, `test_cmdb_graph.py`, `test_alertmanager_webhook.py`, `test_hybrid_rag.py`, `test_ollama_diagnosis.py` (live), `test_locks_and_reconciler.py`, `test_k8s_remediation_kind.py`, `test_auth_and_approvals.py` (`5-way` TOTP/RV race) |
| **Showcase Integration Phases 01–05** | Live FastAPI, Postgres + Alembic `0002`, Redis, Ollama, Keycloak, `kind-aegisops-local` | `PASS` | `test_showcase_readiness_and_controls.py` (`2`), `test_showcase_queue_and_lifecycle.py` (`2`), `test_showcase_scenarios_and_probes.py` (`1`), `test_showcase_inspectors_and_runbooks.py` (`1`), `test_showcase_replay_and_postmortem.py` (`1`) |
| **Playwright Chromium E2E (`backend/tests/e2e/`)** | Live Chromium headless against Vite (`55173`), FastAPI (`58000`), Keycloak (`58080`), Postgres, Ollama, `kind-aegisops-local` | `PASS` | `test_browser_console.py` (OIDC PKCE + TOTP QR + SSE `Stream: live`) + `test_showcase_browser.py` (Visitor Mode, Replay, Privacy Playground, Hybrid Search, Evidence page, Operator PKCE, `Check Patient Eligibility`, Baseline Preview modal; `0` console/page errors) |
| **Prior Live 4-Scenario Chaos Suite** | `chaos/run_scenario.py` (`docs/evidence/chaos-scenarios-report.json`) | `PASS` | Executed across Scenarios 1–4 against Kind + Prometheus + Alertmanager + Ollama + 60s Watchdog |
| **`k6` Burst Benchmark** | `chaos/k6/webhook_burst_and_api.js` (`docs/evidence/k6-summary.json`) | `PASS` | `240/240` checks (`100%`), `0%` failed requests across `120` requests, `p95 = 1109ms` (`< 1500ms`) |
| **Local Sequential Ragas Eval** | Ollama `llama3.2:3b` + `nomic-embed-text:latest` (`docs/evidence/ragas-evaluation.json`) | `MEASURED` | `faithfulness = 0.7083`, `context_recall = 0.8586` (`3/5` samples numerical, `2/5` `NaN` from 3B NLI variance) |
| **GitHub Actions Remote Runners** | `.github/workflows/{ci,live-cluster-chaos}.yml` | `NOT_RUN` | Workflow YAMLs authored and validated locally; not triggered on remote hosted GitHub runners |
| **Destructive `scripts/reset.ps1`** | Full `kind` cluster & volume deletion | `NOT_RUN` | Omitted intentionally to preserve verified local cluster state; scoped UI `Restore Demo Baseline` verified against live Kind |

---

## 2. Showcase Features Verified During Final Gate (`65/65` Pytest + `68` Frontend Modules)

1. **Readiness, Pause Automation & Baseline Reset (`test_showcase_readiness_and_controls.py`)**: Verified `visitor+` readiness probe, strict `operator+` RBAC enforcement (`401`/`403`), pause-automation dispatch hold in `OutboxJob`, and idempotent baseline reset preview/execute preserving audit records.
2. **Queue Filtering, Provenance & 7-Step Lifecycle (`test_showcase_queue_and_lifecycle.py`)**: Verified `Hide Test Runs` ON by default, SQL tab counts (`active`/`resolved`/`escalated`/`failed`/`all`), search/sort/pagination, trusted `X-AegisOps-Provenance`, SSE `after_seq`, live `"Checking service stability: X of 60 seconds observed"`, and zero green false resolution on `ESCALATED`/`FAILED`.
3. **5-Scenario Chaos Lab, Conflicts & Scenario 5 Escalation (`test_showcase_scenarios_and_probes.py`)**: Verified 5-scenario catalog, idempotency deduplication, `409 Conflict` exclusion across dependent services, SSRF-blocked probes (`400`), live semantic probe execution (`eligibility-api`, `provider-directory`), fictional PII scrubbing, and `RB-011` DB escalation (`postgres-claims-db` untouched).
4. **Privacy Playground, Prompt Inspector, Runbook Upload/Search & Live K8s Topology (`test_showcase_inspectors_and_runbooks.py`)**: Verified zero-persistence privacy scrubbing (`8 KiB` -> `413`, `30 req/60s` -> `429`), captured & legacy prompt inspector (`viewer+`), `.md` upload security rejections (`<script>`, unknown playbook ID, risk-tier downgrade), real Ollama indexing (`UPLOADED -> VALIDATING -> INDEXING -> READY`), RRF/`0.78` hybrid search explanation, and live `k8s_live` deployment replica/image/memory facts on `/api/v1/topology`.
5. **Recorded Replay & Unified `.md`/`.pdf` Postmortems (`test_showcase_replay_and_postmortem.py`)**: Verified read-only `captured_live_run` + `illustrative_fixture` frame reconstruction without live K8s bleed-through, escaped Markdown export, pure-Python multi-page `%PDF-1.4` FlateDecode output, non-leaking TOTP fields, and distinct `Escalation Report` framing.
6. **Headless Chromium End-to-End Browser Verification (`test_browser_console.py` + `test_showcase_browser.py`)**: Verified unauthenticated Visitor Mode, Table View toggle, Guided Tour over Recorded Replay, Privacy Scrubber Playground, Hybrid Search Tester, Engineering Evidence view, Keycloak OIDC PKCE (`approver` & `operator`), live `Check Patient Eligibility` probe, TOTP enrollment QR, Technical/Executive toggle, and Baseline Reset preview modal.
