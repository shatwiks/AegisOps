# Showcase Phase 06 — Value Metrics, Engineering Evidence Page & Complete Frontend Upgrade

## 1. Objective, Dependencies, Status & User-Visible Outcomes
- **Objective:** Upgrade metrics & evidence APIs (`Features D, N`) and build the dual-audience React SRE Showcase UI supporting Visitor Mode, `Executive Overview` vs `Technical Deep-Dive` views, 5-scenario Chaos Lab, 7-step Lifecycle Stepper, Filterable Queue, Topology Live K8s + Table View, Business Probes, Privacy Playground & Prompt Inspector, Runbook Browser/Upload/Search, Recorded Replay, Postmortem Downloads, Guided Demo Tour, Readiness/Reset Bar, and Engineering Evidence page (`Features A–O`).
- **Dependencies:** Phases `02`–`05`.
- **Status:** `VERIFIED`
- **User-Visible Outcomes:** Non-technical visitors understand AegisOps in 10 seconds and run guided tours/replays; operators run 1-click scenarios, probes, uploads, and resets; reviewers inspect raw evidence cleanly.

## 2. Scope & Task Checklist
- [x] Upgrade `backend/app/api/metrics.py` (`scope`, probe recovery counts, optional user-supplied manual baseline defaulting to `"Baseline not configured"`) & add `/api/v1/showcase/{overview,evidence}` (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Implement new frontend components (`ChaosLabPanel`, `GuidedTourBar`, `LifecycleStepper`, `DecisionExplanationCard`, `BusinessProbeCard`, `PrivacyPromptDrawer`, `RunbookKnowledgePanel`, `ReplayController`, `EngineeringEvidenceView`) and upgrade `App`, `TopologyGraph`, `IncidentDetail`, `MetricsDashboard`, `types.ts`, `styles.css` (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Run `npm --prefix frontend run typecheck` and `npm --prefix frontend run build` cleanly (`IMPLEMENTED`: yes | `VERIFIED`: yes).

## 3. Source Files, Symbols & Contracts to Change
- `backend/app/api/{metrics,showcase}.py`
- `frontend/src/{App,types,styles.css,lib/pkce.ts}`
- `frontend/src/components/*.tsx`

## 4. Important Tool / Documentation Findings & Decisions
- Preserves existing Playwright E2E selectors (`Sign In with Keycloak OIDC (PKCE)`, `AegisOps SRE Console`, `CMDB Dependency & Blast-Radius Topology`, `Stream: live`, `[Re-]enroll TOTP MFA`, `Sign Out`).

## 5. Observable Acceptance Criteria
1. Strict TypeScript check + Vite production bundle pass with zero warnings/errors.
2. Responsive desktop/mobile layout, keyboard navigation, dialog focus traps, `prefers-reduced-motion`, and contrast verified in headless Chromium.

## 6. Verification Commands & Expected Outcomes
- `npm --prefix frontend run typecheck && npm --prefix frontend run build` -> exit `0`

## 7. Actual Outcomes
- `.\.venv\Scripts\ruff.exe check --config backend/pyproject.toml backend` -> `All checks passed!`
- `.\.venv\Scripts\mypy.exe --config-file backend/pyproject.toml backend/app` -> `Success: no issues found in 50 source files`
- `npm --prefix frontend run typecheck && npm --prefix frontend run build` -> `68 modules transformed`, `built in 3.12s`, zero TypeScript or Vite errors.

## 8. Failures Found, Fixes Applied & Re-runs
- Fixed `apiFetch` in `frontend/src/lib/pkce.ts` to avoid overriding `Content-Type` header on `FormData` multipart runbook uploads, and added `apiDownloadFile` for authenticated `.md`/`.pdf` exports.

## 9. Documentation Updates, Remaining Blockers & Next Action
- **Next Action:** Proceed to Phase 07 (`07-regression-and-handoff.md`).
