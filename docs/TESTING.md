# AegisOps Testing & Verification Strategy

> **Status:** Full automated pyramid, k6 burst benchmark, 4 live chaos scenarios, and local Ragas/Langfuse evaluation implemented and verified across Phases 0–5 (`scripts/test.ps1`, `chaos/run_scenario.py`, `chaos/k6/webhook_burst_and_api.js`).

## 1. Verification Pyramid
1. **Static & Type Gates (`scripts/test.ps1`)**:
   - `ruff check` across `backend/`
   - `mypy --config-file backend/pyproject.toml backend/app backend/scripts`
   - `npm --prefix frontend run typecheck` and Vite production build (`vite build`)
2. **Unit & Property/Adversarial Tests (`backend/tests/unit/`)**:
   - `test_config.py`, `test_scrubber.py` (synthetic redaction benchmark: `10` positive, `4` negative, `precision=1.0`, `recall=1.0`), `test_state_machine.py`, `test_policy_refusal.py` (prompt-injection & DB failover `RB-011` refusal).
3. **Real Dependency Integration Tests (`backend/tests/integration/`)**:
   - `test_foundation_health.py` (live PG16 + pgvector + Redis)
   - `test_cmdb_graph.py` (recursive CTE blast radius + cycle safety)
   - `test_alertmanager_webhook.py` (HMAC/Bearer auth, SSRF rejection, partial unique dedup, `DELETE` append-only trigger check)
   - `test_hybrid_rag.py` (`18` runbooks/postmortems, FTS vs vector RRF, `nomic-embed-text:latest` 768 dims)
   - `test_ollama_diagnosis.py` (live `llama3.2:3b` JSON schema diagnosis + explicit mocked malformed JSON/timeout test)
   - `test_locks_and_reconciler.py` (Lua ownership lock contention + Postgres `SKIP LOCKED` expired job recovery)
4. **Real Cluster Tests (`test_k8s_remediation_kind.py`) & Watchdog (`test_recovery_watchdog.py`)**:
   - Live `kind-aegisops-local` scaling (`provider-directory`), impersonation RBAC verification, UID drift refusal, crash reconciliation (`RECONCILED_SUCCEEDED`), and 60s watchdog verification (with explicit mocked sequence cases for transient dips).
   - **Operational Constraint**: Pause any standalone background outbox worker daemon (`python -m app.worker.runner`) before running `scripts/test.ps1` so the live worker does not race with `test_locks_and_reconciler.py` or `test_k8s_remediation_kind.py`.
5. **Real Browser Tests (`backend/tests/e2e/test_browser_console.py`)**:
   - Headless Playwright Chromium executing live Keycloak PKCE login against Vite (`55173`) + FastAPI (`58000`), verifying role badge, React Flow topology, `Stream: live`, TOTP enrollment modal, and logout.
6. **Chaos, Load & AI Evaluation**:
   - `powershell -ExecutionPolicy Bypass -File .\scripts\demo.ps1 -Scenario all` -> `docs/evidence/chaos-scenarios-report.json` (`4` live scenarios end-to-end).
   - `k6 run --summary-export docs/evidence/k6-summary.json chaos/k6/webhook_burst_and_api.js` -> `240/240` checks passed (`100.00%`), `0.00%` failed of `120` requests, `p95=1.1s < 1500ms`.
   - `.\.venv\Scripts\python.exe backend/scripts/run_ragas_eval.py` -> sequential local Ollama Ragas evaluation (`docs/evidence/ragas-evaluation.json`) & `21` sanitized Langfuse traces in Postgres (`aegisops_langfuse`).
7. **Documentation Link & Env Check**:
   - `.\.venv\Scripts\python.exe scripts/verify_docs.py` validates backticked repo paths and `AEGISOPS_*` env vars across `workingflow.md`, `docs/CODEMAP.md`, `docs/VERIFICATION_REPORT.md`, and `.planning/REQUIREMENTS.md`.
