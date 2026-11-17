# AegisOps Operations Runbook

> **Status:** Complete local lifecycle scripts, Alembic `0002`, Showcase controls (`Pause Automation`, `Restore Demo Baseline`), Kubernetes recovery, Alertmanager/Prometheus alert rules, Keycloak SSO, Langfuse tracing, and 5-scenario Chaos Lab verified locally.

## Operational Lifecycle Commands
- `.\scripts\setup.ps1` — Install project-local `.venv` (via `uv` from `backend/requirements.lock`), frontend `node_modules`, `.local/bin/{kind,terraform}`, and generate `.env`.
- `.\scripts\doctor.ps1` — Run preflight checks across Python, Node, Docker, ports (`53000–59093`), Ollama models (`nomic-embed-text:latest`, `llama3.2:3b`), and `kind-aegisops-local`.
- `.\scripts\up.ps1` — Start Compose backing services (`--profile obs --profile auth --profile langfuse`), Ollama, `kind-aegisops-local`, Terraform namespaces/RBAC/quotas, workload images/manifests, FastAPI API (`58000`), Outbox Worker, and React Console (`55173`).
- `.\scripts\migrate.ps1` — Apply Alembic migrations (`0001_initial_schema.py` -> `0002_showcase_upgrade.py`) to PostgreSQL `127.0.0.1:55432`.
- `.\scripts\seed.ps1` — Seed `8` CMDB assets / `9` dependency edges and `18` SRE documents (`15` runbooks + `3` postmortems).
- `.\scripts\test.ps1` — Run Ruff, Mypy, full Pytest suite (`65` unit, integration, kind, and Playwright Chromium E2E tests), and Vite TypeScript build. *(Stop standalone Outbox Worker before running `scripts/test.ps1` so worker polling does not contend with in-process `run_worker_once` tests; restart it afterward.)*
- `.\scripts\demo.ps1 -Scenario all` — CLI harness executing live Kubernetes chaos scenarios (`chaos/run_scenario.py`) with 60s watchdog verification. (Operators can also launch all `5` showcase scenarios directly via Chaos Lab in the UI.)
- `.\scripts\logs.ps1` — Inspect Docker Compose and Kubernetes pod logs.
- `.\scripts\down.ps1` — Non-destructive shutdown of running host daemons and Docker Compose containers.
- `.\scripts\reset.ps1` — Explicit destructive teardown scoped strictly to `kind-aegisops-local` and AegisOps Compose volumes.

## Interactive Operator Showcase Controls & Recovery Procedures
1. **Pause / Resume Automation (`/api/v1/showcase/controls/automation`)**: Toggle `Pause Automation` in the Chaos Lab bar to hold future remediation dispatches at `READY_TO_REMEDIATE` (`AUTOMATION_PAUSED_HOLD`) cleanly. Pausing does not undo completed Kubernetes mutations or abort an in-flight API patch.
2. **Restore Demo Baseline (`/api/v1/showcase/reset/{preview,execute}`)**: Always inspect the concrete preview modal first. Execution restores healthy replicas (`1`), known-good images, `claims-processor` `192Mi` memory limit, clears `/internal/fault` flags & DB fault annotations in `aegisops-healthcare`, and preserves all audit/incident history (open incidents closed during forced reset are explicitly labeled `manual_reset_assisted`).
3. **Control-Plane PostgreSQL / Redis / Outbox Worker Outage**:
   - Check `/readyz` and `GET /api/v1/showcase/readiness` (Global `Ready`/`Degraded`/`Blocked`).
   - Worker Redis leases (`RedisTargetLease`) fail closed on lock loss; restarting `python -m app.worker.runner` reclaims expired `CLAIMED` jobs via `FOR UPDATE SKIP LOCKED` and reconciles idempotently via `KubernetesExecutor.reconcile_or_execute`.
4. **Ollama / Keycloak Unavailability**:
   - Missing or timed-out Ollama cleanly escalates incidents (`ESCALATED`) and disables Hybrid Search tester with HTTP `503` without guessing remediation.
   - Keycloak JWKS outage fails closed (`401`) on authorized routes while keeping safe Visitor Mode views operational.
5. **Stateful Database Alerts (`RB-011`, `postgres-claims-db`)**:
   - **Architectural Boundary**: Automated failover for `postgres-claims-db` is explicitly prohibited (`stateless_eligible=false`); Scenario 5 and live DB alerts transition directly to `ESCALATED` with P1 CMDB blast radius for human DBA intervention.
