# AegisOps Demonstration Guide (`docs/DEMO.md`)

> **Status:** All 4 live Kubernetes chaos scenarios executed and verified end-to-end against `kind-aegisops-local` (`docs/evidence/chaos-scenarios-report.json`).

## Prerequisites & Startup
1. Ensure Docker Desktop (`pg16`, Redis, OTel Collector, Prometheus, Alertmanager, Keycloak, Langfuse), `kind-aegisops-local`, Ollama (`nomic-embed-text:latest`, `llama3.2:3b`), FastAPI (`58000`), Outbox Worker, and Vite (`55173`) are running:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\up.ps1
   powershell -ExecutionPolicy Bypass -File .\scripts\seed.ps1
   ```
2. Open the React SRE Console at `http://127.0.0.1:55173`, authenticate via Keycloak OIDC PKCE using an `approver` account defined in `.env` / `infra/compose/keycloak/realm-aegisops.json.tmpl`, and keep `Stream: live` open to watch topology impact, RAG citations, TOTP modals, and MTTR telemetry in real time.

## Automated Full Chaos Demonstration
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo.ps1 -Scenario all
```
Runs `chaos/run_scenario.py`, which injects controlled faults, polls control intervals, completes MFA-authenticated approvals for high-risk actions, waits for the 60-second sustained watchdog, and saves `docs/evidence/chaos-scenarios-report.json`.

## Verified Scenario Walkthroughs (Run `2026-11-17T02:10–02:23Z`)
1. **Scenario 1 — `claims-processor` OOM / Memory Pressure (HIGH Risk -> TOTP Approval)**
   - **Fault & Control Signal**: Controlled memory pressure triggering `503` on `/api/claims/adjudicate` and Alertmanager `ClaimsProcessorMemoryPressure`.
   - **Observed Incident & Remediation**: Incident `cff808b2-9876-462a-a10e-24a2ddbc84a9` (`P2`) -> policy required `approver` MFA step-up -> execution `9183a723-2efb-4210-83b5-f223f06a98ea` ran `memory_limit_increase_bounded` patching memory limit `192Mi -> 384Mi` (Deployment generation `13 -> 14`).
   - **Sustained Verification**: Watchdog confirmed recovery at `02:11:21Z` and marked `RESOLVED` after `60s+` at `02:12:26Z`.
2. **Scenario 2 — `eligibility-api` DB Pool Exhaustion (LOW Risk -> Autonomous Restart)**
   - **Fault & Control Signal**: Connection pool wedge yielding `503` on `/api/eligibility/check` while `postgres-claims-db` remained healthy; Prometheus fired `EligibilityDbPoolExhausted`.
   - **Observed Incident & Remediation**: Incident `262d9b1f-8e24-4edd-b323-5073cc42426c` (`P1` across dependent consumers) -> autonomous execution `fbe31922-f22d-481e-a381-945920a3fdcb` ran `stateless_deployment_restart` (generation `11 -> 12`).
   - **Sustained Verification**: First recovered `02:15:37Z` -> `RESOLVED` `02:16:38Z`.
3. **Scenario 3 — `provider-directory` Sustained Load Spike (LOW Risk -> Bounded Scale-Out)**
   - **Fault & Control Signal**: Sustained request saturation raised control latency to `0.673s` against `asyncio.Semaphore(2)`/`0.22s` simulated load; Prometheus fired `ProviderDirectoryHighLatencyCpu`.
   - **Observed Incident & Remediation**: Incident `e89ddb68-aac9-43cc-bad5-cf5d15d6984d` (`P3`) -> autonomous execution `597a5590-9ac6-4698-ac0e-e704953434bc` ran `replica_scale_out_bounded` (`1 -> 3` replicas, generation `18 -> 19`).
   - **Sustained Verification**: First recovered `02:18:41Z` -> `RESOLVED` `02:19:46Z`.
4. **Scenario 4 — `eligibility-api` Broken Canary Release `v1.9.0-broken` (HIGH Risk -> TOTP Rollback)**
   - **Fault & Control Signal**: Canary deployment emitted HTTP `500` on `/api/eligibility/check`; Prometheus fired `High5xxErrorRate`.
   - **Observed Incident & Remediation**: Incident `7710ecbf-e28c-4c67-b2e0-7dc23fc068f0` (`P1`) -> policy ignored LLM-supplied tags and bound rollback to server CMDB `known_good_image` -> MFA-approved execution `921d2a2d-efcd-49c3-b29a-646291dc002b` rolled back `v1.9.0-broken -> v1.0.0-good` (generation `13 -> 14`).
   - **Sustained Verification**: First recovered `02:21:30Z` -> `RESOLVED` `02:22:35Z`.
