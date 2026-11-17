# AegisOps Showcase Upgrade — Architecture & Engineering Decisions

## `SHOW-DEC-001`: Zero-New-Dependency Pure-Python `%PDF-1.4` Postmortem Generator
- **Context**: Feature H requires multi-page `.pdf` postmortem export from the same server snapshot model as `.md`, without fetching remote resources or risking heavy native Chromium/WeasyPrint system-library fragility on Windows.
- **Decision**: Implement `backend/app/showcase/pdf_renderer.py` directly using standards-compliant `%PDF-1.4` object streams with built-in Helvetica/Helvetica-Bold/Courier Type1 fonts, line-wrapping, table grids, automatic page breaks, Latin-1/ASCII safe escaping, and zlib stream compression. Zero external network calls or third-party binaries required.

## `SHOW-DEC-002`: Trusted Provenance Column Instead of Title String Matching
- **Context**: Filtering out `pytest`/`k6` runs by guessing incident titles (`"KindScaleTest"`, etc.) fails security and provenance honesty rules.
- **Decision**: Add `incidents.source_provenance` (`live_alert`, `interactive_demo`, `automated_test`, `recorded_replay`, `unknown`) populated strictly by authenticated webhook headers (`X-AegisOps-Provenance`), active `DemoRun` correlation, or test harnesses. Historical rows default honestly to `'unknown'`.

## `SHOW-DEC-003`: Safe Visitor Mode + Read-Only Sanitized Showcase Namespace
- **Context**: Non-technical recruiters/visitors opening `http://127.0.0.1:55173` must understand the product and explore replays, fictional scrubber playground, hybrid search tester, and engineering evidence immediately—without weakening operational RBAC.
- **Decision**: Add `optional_authenticate_request` (`visitor` tier when unauthenticated). Visitors can access `/api/v1/showcase/{overview,readiness,replays,evidence,privacy/preview}` and read-only runbook/topology summaries (`k8s_live` scrubbed + CMDB structure + `recorded_replay` runs), while live incident operational details (`GET /api/v1/incidents/{id}/prompt`, operational approval history, chaos launch, probes, `.md` uploads, and baseline resets) remain gated behind Keycloak OIDC authentication + RBAC (`viewer` / `operator` / `approver`).

## `SHOW-DEC-004`: Bounded Worker Semaphore (`4`) for Concurrent Chaos + Recovery Execution
- **Context**: Launching a scenario via `OutboxJob(RUN_DEMO_SCENARIO)` triggers fault traffic, waits for Prometheus/Alertmanager ingestion, while `TRIAGE_INCIDENT`, `EXECUTE_REMEDIATION`, and `VERIFY_RECOVERY` must run in parallel for that incident without deadlocking a single sequential `run_worker_once` loop.
- **Decision**: Keep `run_worker_once()` intact for deterministic single-step tests, and run `run_worker_loop()` with `asyncio.Semaphore(4)` dispatching separate async tasks cleanly on claimed `SKIP LOCKED` outbox rows.

## `SHOW-DEC-005`: Scenario 5 Fault Isolation (`aegisops-healthcare` Demo DB vs Control-Plane DB)
- **Context**: Feature A requires Scenario 5 to combine fictional PII in logs with a failing database dependency triggering human escalation.
- **Decision**: Scenario 5 never mutates control-plane `aegisops-postgres` (`55432`). Instead, it sets a reversible fault annotation/config marker on the target workload `postgres-claims-db` inside `aegisops-healthcare` (causing business probe check failure), injects an authenticated Alertmanager webhook bearing explicitly fictional identifiers (`MBR-90001234`, `000-12-3456`, etc.), proves scrubber redaction prior to persistence/LLM, and triggers `RB-011` (`REFUSE_AND_ESCALATE`).
