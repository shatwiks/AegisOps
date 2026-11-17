# Phase 4 — SSO, Step-Up Approval, and Working SRE Console

## 1. Objective, Scope, Dependencies, and Requirement IDs
- **Objective**: Integrate real local Keycloak OIDC (`Authorization Code + PKCE`), RS256 JWKS validation, role-based access control (`viewer`, `operator`, `approver`), Fernet-encrypted per-user TOTP enrollment & replay-protected verification, action-bound single-use high-risk approval, authenticated SSE stream, operational metrics API (`MTTD`/`MTTR`), and the complete React/TypeScript/Vite SRE Console with browser E2E tests.
- **Dependencies**: Phase 3 `VERIFIED`, Keycloak (`58080`), Backend (`58000`), Frontend (`55173`).
- **Requirement IDs**: `REQ-AUTH-01..08`, `REQ-OBS-03` (initial).

## 2. Entry Criteria and Findings
- Phase 3 remediation worker, execution ledger, and watchdog verified.

## 3. Implementation Tasks
- [x] Configure `infra/compose/keycloak/realm-aegisops.json` (`aegisops` realm, `aegisops-console` PKCE client, `viewer`/`operator`/`approver` users and roles).
- [x] Implement `backend/app/auth/oidc.py`, `backend/app/auth/totp.py`, `backend/app/api/auth.py`, and `backend/app/api/approvals.py`.
- [x] Implement `backend/app/api/{incidents,topology,metrics,stream}.py` with RBAC enforcement, CSRF protection, and sanitized SSE delivery.
- [x] Implement full React + TypeScript SRE Console in `frontend/src/` (`@xyflow/react` blast-radius graph, incident detail, citations, TOTP enrollment QR modal, step-up approval form, execution diff, watchdog progress, metrics dashboard, SSE reconnect/stale/session-expiry UI).
- [x] Write integration & Playwright browser E2E tests (`test_auth_and_approvals.py`, `test_browser_console.py`).

## 4. Interfaces, Schemas, Data Flow, and Phase Decisions
- Canonical approval state reconciled to `AWAITING_APPROVAL` (with `ApprovalRequest` holding MFA step-up requirement details).
- Server derives identity & roles exclusively from verified JWT claims; request-supplied `sre_email`/`sre_role` are ignored or rejected.
- Parallel approval attempts execute inside a single `SELECT ... FOR UPDATE` DB transaction consuming the `ApprovalRequest` once and invalidating stale approvals on target/action drift.

## 5. Acceptance Criteria (Observable Behavior)
1. Real browser OIDC PKCE login succeeds through Keycloak for `viewer`, `operator`, and `approver`; logout clears session.
2. Unauthorized roles (`viewer`, `operator`) receive `403` on approval routes; unauthenticated SSE/API requests receive `401`.
3. TOTP enrollment stores encrypted secret only (never in committed files/logs/bundles); invalid, rate-limited, or replayed OTP codes fail with `401`/`429`.
4. Parallel approval submissions schedule exactly one execution; changing playbook/params/target `resourceVersion` invalidates existing approval.
5. An MFA-approved rollback executes via K8s SDK and enters `VERIFYING -> RESOLVED`.
6. Playwright browser tests verify login, role badge, topology blast-radius view, TOTP enrollment, approval workflow, SSE live updates, and empty/error/stale/expiry states.

## 6. Verification Commands, Working Directory, and Expected Outcomes
- Working directory: repo root
- Required services: Keycloak (`58080`), Postgres, Redis, `kind-aegisops-local`, Backend (`58000`), Worker, Frontend (`55173`)
- Commands:
  - `.venv\Scripts\pytest.exe backend/tests/integration/test_auth_and_approvals.py -v` -> all pass
  - `.venv\Scripts\pytest.exe backend/tests/e2e/test_browser_console.py -v` -> all pass
  - `npm --prefix frontend run lint && npm --prefix frontend run build` -> exit `0`

## 7. Actual Results
- **Status of Checks**: `PASS` (`2026-11-17T06:14:00+05:30`).
- **Measured Result**:
  - `ruff check`: `All checks passed!`.
  - `mypy`: `Success: no issues found in 41 source files`.
  - `npm --prefix frontend run typecheck` & `build`: `tsc --noEmit` + Vite `59 modules transformed`, built in `5.17s`.
  - `pytest` (Phase 4): `2 passed in 26.95s` (`test_oidc_rbac_totp_replay_drift_and_concurrent_approval_race` against real Keycloak/Postgres/kind + Playwright Chromium 136 E2E `test_browser_oidc_pkce_login_topology_and_metrics` verifying PKCE login, `@xyflow/react` topology, live SSE `Stream: live`, TOTP QR modal, and Sign Out).
- **Evidence Path**: `docs/evidence/phase-04-auth-console.txt`.

## 8. Defects Found and Fixes Made
- **PKCE `<StrictMode>` Double-Mount Race**: `frontend/src/App.tsx` read & cleared `sessionStorage` PKCE items on first mount before `await apiFetch('/api/v1/auth/oidc/exchange')` completed, causing the second StrictMode mount to hit state mismatch; resolved with module-level `inFlightPkcePromise` deduplication.
- **SSE Effect Reconnect Loop**: `frontend/src/App.tsx` included `lastUpdateAt` state in the SSE `useEffect` dependency array, causing every `onopen` / snapshot update to close and re-open `/api/v1/stream/incidents`; replaced with `lastUpdateAtRef`.
- **Re-enrollment Button Label**: `test_browser_console.py` updated to match both `Enroll TOTP MFA` and `Re-enroll TOTP MFA`.

## 9. Documentation Updates and Exit Checklist
- [x] Update `docs/API.md` and `docs/SECURITY.md`.
- [x] Update `.planning/REQUIREMENTS.md` (`REQ-AUTH-*`, `REQ-OBS-03`) and `.planning/STATE.md`.
- [x] Save sanitized test & browser evidence to `docs/evidence/phase-04-auth-console.txt`.

## 10. Current Status and Next Action
- **Status**: `VERIFIED`
- **Next Action**: Proceed to Phase 5 (`Chaos Scenarios, Benchmarks, Ragas Evaluation, Graphify & Final Docs`).
