# Showcase Phase 03 — Five-Scenario Chaos Lab, Guided Tour & Business Transaction Probes

## 1. Objective, Dependencies, Status & User-Visible Outcomes
- **Objective:** Implement durable 5-scenario Chaos Lab orchestration (`DemoRun` + `OutboxJob(RUN_DEMO_SCENARIO)` + idempotency + target conflict exclusion), allowlisted business transaction recovery probes (`BusinessProbeSample`), and real event-driven Guided Tour narration (`Features A, I, J`).
- **Dependencies:** Phases `01`, `02`.
- **Status:** `VERIFIED`
- **User-Visible Outcomes:** Authorized demo operators launch any of the 5 showcase scenarios in 1 click without PowerShell; conflicting/duplicate launches fail safely showing blocking IDs; Scenario 5 proves fictional PII scrubbing + safe `RB-011` DB escalation; business probes validate real JSON request recovery.

## 2. Scope & Task Checklist
- [x] Implement allowlisted business transaction probes in `backend/app/showcase/probes.py` and `/api/v1/showcase/probes{,/run}` (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Implement 5-scenario catalog & durable worker orchestration in `backend/app/showcase/scenarios.py` + `worker/runner.py` (`RUN_DEMO_SCENARIO`), with conflict locks, idempotency keys, Scenario 1–4 real K8s/fault injections, Scenario 5 fictional PII + `postgres-claims-db` fault annotation + `RB-011` escalation, and `narration_state_json` updates (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Write & pass `backend/tests/integration/test_showcase_scenarios_and_probes.py` (`IMPLEMENTED`: yes | `VERIFIED`: yes).

## 3. Source Files, Symbols & Contracts to Change
- `backend/app/showcase/{__init__,probes,scenarios}.py`
- `backend/app/worker/runner.py`, `backend/app/api/showcase.py`

## 4. Important Tool / Documentation Findings & Decisions
- Scenario 4 (OOM) strictly preserves MFA human approval before `192Mi -> 384Mi` adjustment; Scenario 5 never targets control-plane Postgres (`SHOW-DEC-005`).

## 5. Observable Acceptance Criteria
1. Launching a conflicting scenario returns HTTP `409` naming the active blocking run/incident.
2. Duplicate `idempotency_key` returns the accepted run without duplicating workload faults.
3. Business probes record semantic pass/fail/degraded + latency without arbitrary URL fetching.

## 6. Verification Commands & Expected Outcomes
- `.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_showcase_scenarios_and_probes.py` -> all pass

## 7. Actual Outcomes
- `.\.venv\Scripts\ruff.exe check --config backend/pyproject.toml backend` -> `All checks passed!`
- `.\.venv\Scripts\mypy.exe --config-file backend/pyproject.toml backend/app` -> `Success: no issues found in 46 source files`
- `.\.venv\Scripts\pytest.exe -c backend/pyproject.toml backend/tests/integration/test_showcase_scenarios_and_probes.py -v` -> `1 passed in 38.98s` (verified Visitor catalog read, RBAC 401/403 + SSRF 400 rejection on probes, live `eligibility-api` & `provider-directory` probes, idempotency deduplication, target conflict `409`, Scenario 5 fictional PII scrubbing + `postgres-claims-db` `RB-011` `ESCALATED` path, and safe baseline restoration).

## 8. Failures Found, Fixes Applied & Re-runs
- Fixed 2 Mypy variable-narrowing/redefinition issues (`body` -> `resp_body` in `backend/app/showcase/probes.py` and explicit `found_inc: Incident = row[0]` in `backend/app/api/showcase.py`), restarted FastAPI daemon (`58000`), and re-ran cleanly.

## 9. Documentation Updates, Remaining Blockers & Next Action
- **Next Action:** Proceed to Phase 04 (`04-technical-inspectors.md`).
