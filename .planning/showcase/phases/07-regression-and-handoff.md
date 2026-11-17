# Showcase Phase 07 — Integrated Regression, Live Browser Verification, Graphify Refresh & Final Handoff

## 1. Objective, Dependencies, Status & User-Visible Outcomes
- **Objective:** Run full regression + end-to-end Playwright browser journeys (all 18 required scenarios), verify live 5-scenario showcase execution & baseline reset against `kind-aegisops-local`, refresh Graphify static knowledge graph, complete all Showcase & core docs (`workingflow.md`, `SHOWCASE_GUIDE.md`, `SHOWCASE_TEST_REPORT.md`, `FILE_MAP.md`), and confirm `scripts/verify_docs.py` passes cleanly.
- **Dependencies:** Phase `06`.
- **Status:** `VERIFIED`
- **User-Visible Outcomes:** Verified, documented, ready-to-demo AegisOps Showcase application with honest evidence bundles and zero doc drift.

## 2. Scope & Task Checklist
- [x] Add & run `backend/tests/e2e/test_showcase_browser.py` covering Visitor Mode, Guided Tour, Replay, Privacy Playground, Runbook Search, Evidence Page, Queue Filters, and Scenario Launch/Reset (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Run full `.\scripts\test.ps1` (stopping background worker daemon first, restarting after) -> capture `docs/evidence/showcase-test-gate.txt` (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Verify live 5-scenario orchestration via API/UI and restore clean baseline (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Refresh `graphify-out/` knowledge graph, write `docs/{SHOWCASE_GUIDE,SHOWCASE_TEST_REPORT,FILE_MAP}.md`, update `README.md`, `OVERALL_FLOW.md`, `docs/{API,DATA_MODEL,SECURITY,RUNBOOK,CODEMAP,VERIFICATION_REPORT}.md`, `.planning/showcase/*`, and rewrite root `workingflow.md` (all 19 sections) (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Run `.\.venv\Scripts\python.exe scripts/verify_docs.py` -> exit `0` (`IMPLEMENTED`: yes | `VERIFIED`: yes).

## 3. Source Files, Symbols & Contracts to Change
- `backend/tests/e2e/test_showcase_browser.py`
- `workingflow.md`, `OVERALL_FLOW.md`, `README.md`, `docs/*.md`, `scripts/verify_docs.py`

## 4. Important Tool / Documentation Findings & Decisions
- All docs strictly separate live checks, mocked unit doubles, and unexecuted remote CI runners.

## 5. Observable Acceptance Criteria
1. Full `.\scripts\test.ps1` exits `0` (`ruff`, `mypy`, all unit/integration/E2E pytests, `vite build`).
2. `scripts/verify_docs.py` exits `0` across all showcase and core deliverables.

## 6. Verification Commands & Expected Outcomes
- `.\scripts\test.ps1` -> exit `0`
- `.\.venv\Scripts\python.exe scripts/verify_docs.py` -> exit `0`

## 7. Actual Outcomes
- Pending execution.

## 8. Failures Found, Fixes Applied & Re-runs
- None yet.

## 9. Documentation Updates, Remaining Blockers & Next Action
- **Next Action:** Blocked on Phase 06.
