# Showcase Phase 02 — Incident Queue Filters, Provenance & 7-Step Lifecycle Progress

## 1. Objective, Dependencies, Status & User-Visible Outcomes
- **Objective:** Expose server-side queue tabs (`Active`, `Resolved`, `Escalated`, `Failed`, `All`), `Hide Test Runs` filtering (`source_provenance`), search, sorting, pagination, accurate SQL tab counts, ordered SSE catch-up (`after_seq`), and deterministic 7-step incident lifecycle derivation (`Features B, C`).
- **Dependencies:** Phase `01` (`VERIFIED`).
- **Status:** `VERIFIED`
- **User-Visible Outcomes:** Queue cleanly hides automated test rows by default without deleting history, restores filters via query parameters, displays accurate filtered SQL counts across pages, and computes honest 7-step lifecycle milestones (never rendering green Resolved for escalated/failed runs).

## 2. Scope & Task Checklist
- [x] Populate trusted `source_provenance` via `X-AegisOps-Provenance` header and active `DemoRun` correlation in `webhooks.py`; update `send_synthetic_alert.py`, `k6`, and existing test fixtures (`IMPLEMENTED` | `VERIFIED`).
- [x] Implement filtered/paginated `GET /api/v1/incidents` with `tab_counts`, `compute_lifecycle_steps`, and `build_why_this_action` in `backend/app/api/incidents.py` (`IMPLEMENTED` | `VERIFIED`).
- [x] Update `backend/app/api/stream.py` for monotonic `sequence_num` / `after_seq` catch-up and live `demo_runs` stream frames (`IMPLEMENTED` | `VERIFIED`).
- [x] Write & pass `backend/tests/integration/test_showcase_queue_and_lifecycle.py` + `test_alertmanager_webhook.py` (`IMPLEMENTED` | `VERIFIED`).

## 3. Source Files, Symbols & Contracts Changed
- `backend/app/api/webhooks.py`, `backend/app/api/incidents.py` (`serialize_incident`, `compute_lifecycle_steps`, `build_why_this_action`, `list_incidents`, `get_incident_detail`), `backend/app/api/stream.py`
- `scripts/send_synthetic_alert.py`, `chaos/k6/webhook_burst_and_api.js`, `backend/tests/integration/{test_alertmanager_webhook,test_k8s_remediation_kind,test_locks_and_reconciler,test_auth_and_approvals}.py`

## 4. Important Tool / Documentation Findings & Decisions
- Historical incidents retain `'unknown'` provenance (`SHOW-DEC-002`); `ACTIVE_STATES` separates active remediation/verifying vs `ESCALATED` vs `FAILED` vs `RESOLVED`.

## 5. Observable Acceptance Criteria
1. `tab_counts` match exact SQL row totals across `active`, `resolved`, `escalated`, `failed`, `all`, and `hidden_test_count`.
2. `compute_lifecycle_steps` accurately represents pending, running, completed, failed, blocked, and not-applicable across autonomous, MFA-gated, escalated, and verifying branches.

## 6. Verification Commands & Expected Outcomes
- `ruff check backend/`, `mypy backend/app backend/scripts`, `pytest -v backend/tests/integration/test_showcase_queue_and_lifecycle.py backend/tests/integration/test_alertmanager_webhook.py` -> all pass

## 7. Actual Outcomes
- **Timestamp:** `2026-11-17T10:19:46+05:30`
- **Results:** Ruff clean; Mypy clean (`45` files); Pytest `3 passed in 16.47s`.

## 8. Failures Found, Fixes Applied & Re-runs
- Replaced `Asset.slug.type` cast with explicit SQLAlchemy `cast(..., Text)` in `_apply_incident_filters` for strict typing; cleaned up synthetic rows via `finally:` after assertions.

## 9. Documentation Updates, Remaining Blockers & Next Action
- **Blockers:** None.
- **Next Action:** Execute Phase `03` (5-scenario Chaos Lab, Guided Tour narration contract & Business Transaction Probes).
