# AegisOps Execution State

- **Active Phase**: `ALL BASE PHASES VERIFIED (Phases 0–5 complete locally) -> Active Showcase Upgrade tracked in .planning/showcase/STATE.md`
- **Showcase Plan Pointer**: [.planning/showcase/STATE.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/showcase/STATE.md) · [.planning/showcase/MASTER_PLAN.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/showcase/MASTER_PLAN.md)
- **Current Task**: Maintenance / demonstration ready (`Ollama`, `FastAPI`, `Outbox Worker`, `Vite`, Compose stack, and `kind-aegisops-local` running cleanly with `0` active Prometheus alerts and `0` open incidents).
- **Last Verification Revision**: `main` (Phase 5 full gate `2026-11-17T08:21:28+05:30`, `57 passed in 116.67s`)
- **Completed Gates**: `Phase 0` (`VERIFIED`), `Phase 1` (`VERIFIED`), `Phase 2` (`VERIFIED`, 50/50), `Phase 3` (`VERIFIED`, 55/55), `Phase 4` (`VERIFIED`, Keycloak OIDC PKCE + TOTP + RBAC + Playwright E2E), `Phase 5` (`VERIFIED`, 4/4 live chaos scenarios, k6 `240/240`, `21` Langfuse traces, Ragas eval, Graphify `1,356` nodes, `57/57` final suite, `verify_docs.py` clean)
- **Failing Checks**: None

## Environment Readiness (Observed 2026-11-17)
- **OS / Shell**: Windows 11 / PowerShell
- **Python**: `3.12.14` in `.venv` via `uv` (`136` pinned packages in `backend/requirements.lock`)
- **Node / npm**: `v26.7.0` / `11.19.0` (`59` modules built in `2.61s`)
- **Docker**: `29.9.2` (`Docker Desktop`), Compose `v5.6.1`
- **kubectl**: `v1.36.0` on PATH (`kind-aegisops-local` active)
- **k6**: `v2.2.0` on PATH (`240/240` burst checks passed)
- **kind / terraform**: Project-local `.local/bin/kind.exe` (`v0.27.0`) and `.local/bin/terraform.exe` (`v1.10.5`) verified
- **Ollama**: `0.40.10` CLI serving `nomic-embed-text:latest` (`768` dims) and `llama3.2:3b` on `127.0.0.1:11434`
- **Ports**: Live stack active on `53000`, `55173`, `55317/55318`, `55432`, `56379`, `58000`, `58080–58084`, `59090`, `59093`.

## Next Exact Action
- None — all local build, verification, chaos, and documentation tasks are complete (`scripts/reset.ps1` destructive wipe and remote GitHub Actions runner execution explicitly excluded and documented).
