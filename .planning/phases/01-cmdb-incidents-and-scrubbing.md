# Phase 1 — CMDB, Incidents, and Privacy Boundary

## 1. Objective, Scope, Dependencies, and Requirement IDs
- **Objective**: Implement PostgreSQL/pgvector schema migrations, CMDB directed asset topology & seed script, cycle-safe recursive blast-radius queries, deterministic P1–P4 severity policy, canonical incident state machine, earliest-boundary PHI/PII scrubber with fail-closed fallback, authenticated Alertmanager webhook ingestion with atomic deduplication, and transactional outbox persistence.
- **Dependencies**: Phase 0 `VERIFIED` (running PostgreSQL 16 + `pgvector` and Redis).
- **Requirement IDs**: `REQ-ING-01..07`, `REQ-CMDB-01..08`.

## 2. Entry Criteria and Findings
- Phase 0 database connectivity and configuration system must be verified.

## 3. Implementation Tasks
- [x] Define SQLAlchemy 2.0 declarative models (`backend/app/models/entities.py`).
- [x] Configure Alembic (`backend/alembic.ini`, `backend/migrations/env.py`) and write `0001_initial_schema.py` including HNSW index (`768` dims), GIN FTS index, partial unique index for active alert dedup, and `DELETE` protection trigger on `audit_records`/`incident_events`.
- [x] Implement `backend/app/privacy/scrubber.py` (allowlist + regex/entity scrubbing + fail-closed fallback + synthetic healthcare corpus evaluator).
- [x] Implement `backend/app/cmdb/graph.py` (`WITH RECURSIVE` cycle-safe upstream/downstream blast-radius queries, unknown asset handling, deterministic `P1–P4` severity scoring).
- [x] Implement `backend/app/domain/state_machine.py` (canonical state transitions with `SELECT ... FOR UPDATE`, optimistic `version_id`, and atomic `IncidentEvent`/`AuditRecord` writes).
- [x] Implement `backend/app/api/webhooks.py` (`POST /api/v1/webhooks/alertmanager` with HMAC/Bearer auth, payload cap, rate limit, SSRF guard, scrubbing, deduplication, transactional outbox job creation).
- [x] Implement `backend/app/seed/cmdb_seed.py` and `scripts/send_synthetic_alert.py`.
- [x] Write unit, adversarial, and real-Postgres integration tests (`test_scrubber.py`, `test_cmdb_graph.py`, `test_state_machine.py`, `test_alertmanager_webhook.py`).

## 4. Interfaces, Schemas, Data Flow, and Phase Decisions
- Edge direction (`DEC-005`): `source_asset_id -> target_asset_id` means `source depends_on target`.
- Canonical States (`REQ-CMDB-06`): `OPEN -> TRIAGING -> READY_TO_REMEDIATE | AWAITING_APPROVAL | ESCALATED -> REMEDIATING -> VERIFYING -> RESOLVED | FAILED`.
- Alert deduplication key: `<alertname>:<cluster>:<namespace>:<service>:<fingerprint>` restricted via unique partial index where `state NOT IN ('RESOLVED', 'FAILED')`.

## 5. Acceptance Criteria (Observable Behavior)
1. Fresh `alembic upgrade head` succeeds on clean Postgres+pgvector; `seed` is idempotent across repeated invocations.
2. Cycle, diamond, disconnected, and duplicate-named multi-namespace CMDB graphs traverse cleanly without infinite recursion, reporting `truncated` when bounded.
3. Unknown assets create valid tracked incidents (`P2` + escalation note) without null FK failures.
4. Scrubber strips SSNs, Member IDs, emails, JWTs, IPv4s, and contextual names across nested/mixed-case/multiline payloads; simulated scrubber exception produces a minimal safe fallback event without raw payload leakage.
5. Concurrent/repeated webhook deliveries produce exactly one active `Incident` and one pending `TRIAGE_INCIDENT` `OutboxJob`.
6. Illegal state transitions and attempts to delete `audit_records` fail at both app and DB levels.

## 6. Verification Commands, Working Directory, and Expected Outcomes
- Working directory: repo root
- Required services: `aegisops-postgres`, `aegisops-redis`
- Commands:
  - `.\scripts\migrate.ps1` -> exit `0`
  - `.\scripts\seed.ps1 --cmdb-only` (run twice to prove idempotency) -> exit `0`
  - `.venv\Scripts\pytest.exe backend/tests/unit/test_scrubber.py backend/tests/unit/test_state_machine.py backend/tests/integration/test_cmdb_graph.py backend/tests/integration/test_alertmanager_webhook.py -v` -> all pass

## 7. Actual Results
- **Timestamp**: `2026-11-17T05:00:29+05:30`
- **Check Results**:
  - `.\scripts\migrate.ps1` -> `PASS` (`0001_initial_schema` applied to PostgreSQL 16 + pgvector)
  - `.\scripts\seed.ps1 -CmdbOnly` (x2) -> `PASS` (idempotent `{'assets': 8, 'dependencies': 9}`)
  - `evaluate_redaction_corpus()` -> `PASS` (`precision=1.0`, `recall=1.0`, `10` positives, `4` negatives, `0` FP/FN)
  - `ruff check` & `mypy` (14 source files) -> `PASS`
  - `pytest backend/tests -v` -> `PASS` (`42 passed in 6.17s`)
- **Evidence Path**: [phase-01-cmdb-privacy.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/evidence/phase-01-cmdb-privacy.txt)

## 8. Defects Found and Fixes Made
1. Missing `qualname` in `backend/alembic.ini` (`sqlalchemy`, `alembic` loggers) fixed.
2. `AsyncSession` attribute expiry after `session.rollback()` in `test_alertmanager_webhook.py` caused `MissingGreenlet` when reading `inc.id`; captured `inc_id = inc.id` before rollback.

## 9. Documentation Updates and Exit Checklist
- [x] Update `docs/DATA_MODEL.md` and `docs/SECURITY.md`.
- [x] Update `.planning/REQUIREMENTS.md` (`REQ-ING-*`, `REQ-CMDB-*`) and `.planning/STATE.md`.
- [x] Save sanitized test & redaction corpus benchmark output to `docs/evidence/phase-01-cmdb-privacy.txt`.

## 10. Current Status and Next Action
- **Status**: `VERIFIED`
- **Next Action**: Begin Phase 2 — Hybrid RAG and Refusal Gate (`02-hybrid-rag-and-refusal.md`).
