# Showcase Phase 05 — Recorded Incident Replay and Postmortem Exports (Markdown & PDF)

## 1. Objective, Dependencies, Status & User-Visible Outcomes
- **Objective:** Implement isolated Recorded Incident Replay frame reconstruction and a unified server-side postmortem snapshot generator exporting both escaped Markdown (`.md`) and pure-Python standards-compliant `%PDF-1.4` (`.pdf`) reports (`Features H, L`).
- **Dependencies:** Phases `01`, `02`, `03`.
- **Status:** `VERIFIED`
- **User-Visible Outcomes:** Visitors replay captured/illustrative incidents step by step without touching live cluster state; authorized users download matching `.md` and multi-page `.pdf` reports for resolved, escalated, or failed runs without secret/TOTP leakage.

## 2. Scope & Task Checklist
- [x] Implement `backend/app/showcase/replay.py` and `/api/v1/showcase/replays{,/{id}}` distinguishing `captured_live_run` vs `illustrative_fixture` (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Implement `backend/app/showcase/postmortem.py` + `backend/app/showcase/pdf_renderer.py` and `/api/v1/incidents/{id}/postmortem.{md,pdf}` (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Write & pass `backend/tests/integration/test_showcase_replay_and_postmortem.py` (`IMPLEMENTED`: yes | `VERIFIED`: yes).

## 3. Source Files, Symbols & Contracts to Change
- `backend/app/showcase/{replay,postmortem,pdf_renderer}.py`
- `backend/app/api/{showcase,incidents}.py`

## 4. Important Tool / Documentation Findings & Decisions
- Uses `SHOW-DEC-001` (pure-Python zlib-compressed `%PDF-1.4` writer with Type1 fonts, word wrapping, page breaks, non-ASCII safety, zero remote fetches).

## 5. Observable Acceptance Criteria
1. Replay endpoints never write to DB, Redis, or Kubernetes.
2. `.md` and `.pdf` outputs derive from identical snapshot fields and never expose TOTP seeds, OTP codes, session cookies, or raw PII.

## 6. Verification Commands & Expected Outcomes
- `.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_showcase_replay_and_postmortem.py` -> all pass

## 7. Actual Outcomes
- `.\.venv\Scripts\ruff.exe check --config backend/pyproject.toml backend` -> `All checks passed!`
- `.\.venv\Scripts\mypy.exe --config-file backend/pyproject.toml backend/app` -> `Success: no issues found in 50 source files`
- `.\.venv\Scripts\pytest.exe -c backend/pyproject.toml backend/tests/integration/test_showcase_replay_and_postmortem.py -v` -> `1 passed in 10.76s` (verified illustrative fixture + 32-frame captured replay reconstruction without live K8s bleed-through, `.md` XSS sanitization + non-leaking TOTP, and multi-page `%PDF-1.4` FlateDecode output for both resolved and escalated incidents).

## 8. Failures Found, Fixes Applied & Re-runs
- Fixed 3 SQLAlchemy `Sequence` vs `list` type annotations in `backend/app/showcase/replay.py` before passing all checks cleanly.

## 9. Documentation Updates, Remaining Blockers & Next Action
- **Next Action:** Proceed to Phase 06 (`06-value-evidence-and-polish.md`).
