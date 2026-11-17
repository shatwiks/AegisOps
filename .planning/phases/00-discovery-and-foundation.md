# Phase 0 — Discovery and Runnable Foundation

## 1. Objective, Scope, Dependencies, and Requirement IDs
- **Objective**: Establish the runnable project skeleton, dependency management, local tool provisioning (`.venv` Python 3.12 via `uv`, `.local/bin/{kind,terraform}`), `.env.example`, configuration validation, Compose PostgreSQL+pgvector & Redis services, FastAPI health endpoints (`/healthz`, `/readyz`), React/Vite shell, `kind` cluster config, and `scripts/` command interface.
- **Dependencies**: Host Docker Desktop, `uv`, Python 3.12, Node.js 20+, `kubectl`, `k6`, Ollama.
- **Requirement IDs**: `REQ-OPS-01` (partial: foundation commands, `.env.example`, doctor).

## 2. Entry Criteria and Findings
- Empty repository at `d:\PROJECTS\AegisOps An Autonomous AIOps, CMDB Blast-Radius & Self-Healing Kubernetes Control`.
- Git initialized on `main`.
- Ports `53000–59093` verified unused; unrelated containers on host must not be touched.
- Ollama `nomic-embed-text:latest` (`sha256:0a109f...`) and `llama3.2:3b` (`sha256:a80c4f...`) cached locally.

## 3. Implementation Tasks
- [x] Create `.env.example` with full documentation and safe placeholders (`DEC-003` port table).
- [x] Create `backend/pyproject.toml` and pin dependencies into `.venv` (`uv`) + lock file (`backend/requirements.lock`).
- [x] Implement `backend/app/config.py` (`Settings` with strict fail-fast validation for secrets, vector dim 768, kube context allowlist).
- [x] Implement `backend/app/db.py` (`create_async_engine`, `async_sessionmaker`, `pgvector` readiness check).
- [x] Implement `backend/app/redis_client.py` (`redis.asyncio.Redis` pool and `PING` check).
- [x] Implement `backend/app/main.py` (FastAPI `lifespan`, `/healthz`, `/readyz`, correlation ID middleware, restricted CORS).
- [x] Create `frontend/` React + TypeScript + Vite shell (`package.json`, `tsconfig.json`, `vite.config.ts`, `src/App.tsx`).
- [x] Create `infra/compose/docker-compose.yml` and `infra/compose/postgres-init/01-init.sql` (Postgres + pgvector + Redis).
- [x] Create `infra/k8s/kind-config.yaml` mapping NodePorts `30081–30083` to `58081–58083`.
- [x] Implement `scripts/{_common,setup,doctor,up,migrate,seed,test,demo,logs,down,reset}.ps1`.
- [x] Write `backend/tests/unit/test_config.py` and `backend/tests/integration/test_foundation_health.py`.

## 4. Interfaces, Schemas, Data Flow, and Phase Decisions
- Configuration fails loudly at startup if `AEGISOPS_WEBHOOK_HMAC_SECRET`, `AEGISOPS_TOTP_ENCRYPTION_KEY`, or `AEGISOPS_SESSION_SECRET` are missing or placeholder values, or if `AEGISOPS_EMBEDDING_DIMENSIONS != 768`.
- `GET /healthz` returns `{"status": "ok"}` (process liveness). `GET /readyz` checks live Postgres `SELECT 1` + `vector` extension existence and Redis `PING`, returning `503` if any core dependency is down.
- See `DEC-001`, `DEC-002`, `DEC-003`, `DEC-004`, `DEC-006` in `DECISIONS.md`.

## 5. Acceptance Criteria (Observable Behavior)
1. `.\scripts\setup.ps1` completes cleanly, installing `.venv` (Python 3.12), `frontend/node_modules`, `.local/bin/{kind,terraform}`, and generating `.env` with non-committed random secrets.
2. `.\scripts\doctor.ps1` accurately detects all prerequisites, available ports, Ollama cached models, and Compose availability.
3. Invalid configuration tests verify FastAPI/Settings refuses invalid or empty secrets and disallowed cluster contexts.
4. Real `aegisops-postgres` (`55432`) and `aegisops-redis` (`56379`) start healthy, `/healthz` returns `200`, and `/readyz` returns `200` with verified Postgres/pgvector and Redis status.
5. `frontend` builds cleanly via `npm --prefix frontend run build`.

## 6. Verification Commands, Working Directory, and Expected Outcomes
- Working directory: repo root `d:\PROJECTS\AegisOps An Autonomous AIOps, CMDB Blast-Radius & Self-Healing Kubernetes Control`
- Required services: `aegisops-postgres`, `aegisops-redis`
- Commands:
  - `.\scripts\setup.ps1` -> exit `0`
  - `.\scripts\doctor.ps1` -> exit `0`
  - `docker compose -f infra/compose/docker-compose.yml up -d postgres redis` -> healthy containers
  - `.venv\Scripts\pytest.exe backend/tests/unit/test_config.py backend/tests/integration/test_foundation_health.py -v` -> all pass
  - `npm --prefix frontend run build` -> exit `0`

## 7. Actual Results
- **Timestamp**: `2026-11-17T04:15:10+05:30`
- **Working Tree State**: Initialized `main` branch (uncommitted Phase 0 files)
- **Check Results**:
  - `.\scripts\setup.ps1` -> `PASS` (exit `0`; installed Python 3.12.14 `.venv` with 136 packages, `kind v0.27.0`, `Terraform v1.10.5`, 89 npm packages, generated `.env`)
  - `.\scripts\doctor.ps1` -> `PASS` (exit `0`; all 10 tool/model/config/compose checks `[OK]`, all 14 allocated ports verified)
  - `docker compose up -d postgres redis` -> `PASS` (`aegisops-postgres` & `aegisops-redis` healthy)
  - `ruff check backend` -> `PASS` (`All checks passed!`)
  - `mypy backend/app` -> `PASS` (`Success: no issues found in 5 source files`)
  - `pytest` (`test_config.py`, `test_foundation_health.py`) -> `PASS` (`11 passed in 2.96s`)
  - `npm --prefix frontend run build` -> `PASS` (`vite v6.0.11` built `dist/` in `1.73s`)
- **Evidence Path**: [phase-00-foundation.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/evidence/phase-00-foundation.txt)

## 8. Defects Found and Fixes Made
1. **PowerShell 5.1 RNG method**: `RandomNumberGenerator::Fill` threw `MethodNotFound` under Windows PowerShell 5.1; replaced with `RandomNumberGenerator::Create().GetBytes($buf)` in `scripts/_common.ps1`.
2. **`kubectl --short` flag removed in v1.36.0**: `scripts/doctor.ps1` updated to call `kubectl version --client` directly.
3. **Ampersand (`&`) in workspace folder path broke `npm` `.cmd` shims**: Invoking `tsc -b` via `.bin\tsc.cmd` failed with `'Self-Healing' is not recognized`. Updated `frontend/package.json` scripts to invoke `node ./node_modules/typescript/bin/tsc` and `node ./node_modules/vite/bin/vite.js` directly.

## 9. Documentation Updates and Exit Checklist
- [x] Update `docs/DEPENDENCIES.md` with exact installed package and container versions.
- [x] Update `.planning/REQUIREMENTS.md` (`REQ-OPS-01` partial) and `.planning/STATE.md`.
- [x] Save sanitized test output to `docs/evidence/phase-00-foundation.txt`.

## 10. Current Status and Next Action
- **Status**: `VERIFIED`
- **Next Action**: Begin Phase 1 — CMDB, Incidents, and Privacy Boundary (`01-cmdb-incidents-and-scrubbing.md`).
