# AegisOps

**AegisOps** is an independent, locally runnable AIOps control plane, CMDB blast-radius analyzer, and self-healing Kubernetes operator built with synthetic healthcare workloads (`eligibility-api`, `claims-processor`, `provider-directory`).

> **Scope & Disclaimer:** AegisOps is an independent technical demonstration using strictly synthetic data. It implies no affiliation with Optum or any real healthcare organization, no regulatory certification (such as HIPAA/HITRUST compliance), and no readiness for a clinical environment.

## Verified Local Quick Start (Windows 11 / Docker Desktop / WSL2)

### Prerequisites
- **Docker Desktop** with Linux containers enabled (`29.9.2` verified, ~8 GB RAM available; Compose `v5.6.1`)
- **Python 3.12** (`3.12.14` verified) managed via `uv` into `.venv` from pinned `backend/requirements.lock`
- **Node.js 20+** (`v26.7.0` verified) & `npm` (`11.19.0`)
- **Ollama** (`0.40.10` verified) serving local `nomic-embed-text:latest` (`768` dims) and `llama3.2:3b`
- **kubectl** (`v1.36.0` verified), **k6** (`v2.2.0` verified)
- Project-local **`kind`** (`v0.27.0`) and **`terraform`** (`v1.10.5`) provisioned under `.local/bin/` by `scripts/setup.ps1`

### Project Command Interface
Commands under `scripts/` automate the complete local lifecycle:
- `.\scripts\setup.ps1` — Provision `.venv` (Python 3.12), frontend packages, `.local/bin/{kind,terraform}`, and generate `.env` secrets.
- `.\scripts\doctor.ps1` — Verify prerequisites, host ports (`53000–59093`), Docker, Ollama models, and cluster readiness.
- `.\scripts\up.ps1` — Start Compose backing services (`postgres`, `redis`, `otel`, `prometheus`, `alertmanager`, `keycloak`, `langfuse`), Ollama, `kind-aegisops-local`, Terraform namespaces/RBAC/quotas, workload builds/manifests, FastAPI API, Outbox Worker, and React Console.
- `.\scripts\migrate.ps1` — Apply Alembic migrations (`0001_initial_schema.py` + `0002_showcase_upgrade.py`) on PostgreSQL (`127.0.0.1:55432`).
- `.\scripts\seed.ps1` — Seed CMDB topology (`8` assets, `9` edges) and `18` SRE runbooks/postmortems with `nomic-embed-text` embeddings.
- `.\scripts\test.ps1` — Run Ruff, Mypy (`50` files), full Pytest suite (`65` unit, live integration, kind cluster, and Playwright Chromium E2E tests), and Vite production build (`68` modules). (Stop any standalone background worker daemon before running so live tests do not contend with test jobs; restart afterward.)
- `.\scripts\demo.ps1 -Scenario all` — Execute all 4 live Kubernetes chaos scenarios (`chaos/run_scenario.py`) end-to-end with 60s sustained recovery checks.
- `.\scripts\logs.ps1` — Tail logs across control-plane containers and Kubernetes pods.
- `.\scripts\down.ps1` — Non-destructive shutdown of host daemons and Docker Compose containers.
- `.\scripts\reset.ps1` — Explicit destructive reset scoped strictly to `kind-aegisops-local` and AegisOps Compose volumes.

### Local URLs & Role Access
| Component | URL | Notes |
|---|---|---|
| React SRE Console | `http://127.0.0.1:55173` | Vite dev console with OIDC PKCE login (`viewer`, `operator`, `approver` users configured via `.env` / `infra/compose/keycloak/realm-aegisops.json.tmpl`) |
| FastAPI Control Plane | `http://127.0.0.1:58000` | `/healthz`, `/readyz`, `/metrics`, `/api/v1/*` |
| Keycloak OIDC | `http://127.0.0.1:58080` | Realm `aegisops`, S256 PKCE client `aegisops-console` |
| Langfuse UI | `http://127.0.0.1:53000` | Sanitized LLM trace & eval UI (`aegisops_langfuse` DB) |
| Prometheus | `http://127.0.0.1:59090` | Metrics & traffic-guarded alert rule evaluation |
| Alertmanager | `http://127.0.0.1:59093` | Authenticated webhook delivery |
| `eligibility-api` | `http://127.0.0.1:58081` | Demo service (NodePort `30081`) |
| `claims-processor` | `http://127.0.0.1:58082` | Demo service (NodePort `30082`) |
| `provider-directory` | `http://127.0.0.1:58083` | Demo service (NodePort `30083`) |

> **Verification Boundary:** All runtime components, automated test tiers, 4 chaos scenarios (`docs/evidence/chaos-scenarios-report.json`), `k6` webhook burst benchmark (`240/240` checks, `docs/evidence/k6-summary.json`), local Ragas evaluation (`docs/evidence/ragas-evaluation.json`), and Graphify code map (`docs/CODEMAP.md`) ran and passed locally on Windows 11 + Docker Desktop + `kind-aegisops-local`. GitHub Actions workflows (`.github/workflows/ci.yml`, `.github/workflows/live-cluster-chaos.yml`) were validated cleanly locally and not executed on hosted GitHub runners.

## Documentation Index
- [OVERALL_FLOW.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/OVERALL_FLOW.md) — Master phase plan and acceptance gates
- [workingflow.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/workingflow.md) — End-to-end as-built developer walkthrough
- [STATE.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/STATE.md) — Current execution checkpoint
- [REQUIREMENTS.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/REQUIREMENTS.md) — Requirement traceability matrix
- [docs/ARCHITECTURE.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/ARCHITECTURE.md) | [docs/CODEMAP.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/CODEMAP.md) | [docs/API.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/API.md) | [docs/DATA_MODEL.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/DATA_MODEL.md)
- [docs/SECURITY.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/SECURITY.md) | [docs/DEPENDENCIES.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/DEPENDENCIES.md) | [docs/RUNBOOK.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/RUNBOOK.md) | [docs/TESTING.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/TESTING.md)
- [docs/VERIFICATION_REPORT.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/VERIFICATION_REPORT.md) | [docs/DEMO.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/DEMO.md)
- [docs/SHOWCASE_GUIDE.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/SHOWCASE_GUIDE.md) | [docs/SHOWCASE_TEST_REPORT.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/SHOWCASE_TEST_REPORT.md) | [docs/FILE_MAP.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/FILE_MAP.md)
