# Showcase Phase 04 — Technical Inspectors, Knowledge Base Upload & Live K8s Topology

## 1. Objective, Dependencies, Status & User-Visible Outcomes
- **Objective:** Deliver zero-persistence Privacy Scrubber Playground, Sanitized Prompt Inspector + 7-question "Why This Action?" card, searchable Runbook Browser with validated `.md` upload (`UPLOADED -> VALIDATING -> INDEXING -> READY/FAILED`) and Hybrid Search Tester, plus live Kubernetes facts attached to CMDB topology nodes (`Features E, F, G, K`).
- **Dependencies:** Phases `01`, `02`, `03`.
- **Status:** `VERIFIED`
- **User-Visible Outcomes:** Visitors/reviewers inspect real privacy redactions, exact captured LLM prompts (when authorized), live pod replicas/images/memory limits, `.md` runbook uploads with strict playbook policy validation, and lexical/vector/RRF search scores.

## 2. Scope & Task Checklist
- [x] Add `/api/v1/showcase/privacy/preview` and `GET /api/v1/incidents/{id}/prompt` (with `why_this_action` breakdown) (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Implement `backend/app/api/runbooks.py` (`GET /api/v1/runbooks`, `GET /{slug}`, `POST /upload`, `POST /search`, `POST /{slug}/retry-index`) and `INDEX_RUNBOOK` handler in `runner.py` (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Enhance `backend/app/api/topology.py` with bounded cached `k8s_live` deployment facts and unavailable/stale states (`IMPLEMENTED`: yes | `VERIFIED`: yes).
- [x] Write & pass `backend/tests/integration/test_showcase_inspectors_and_runbooks.py` (`IMPLEMENTED`: yes | `VERIFIED`: yes).

## 3. Source Files, Symbols & Contracts to Change
- `backend/app/api/{showcase,incidents,runbooks,topology}.py`
- `backend/app/worker/runner.py`, `backend/app/seed/runbook_seed.py`

## 4. Important Tool / Documentation Findings & Decisions
- Uploaded `.md` files cannot register new executable commands, alter risk tier below `PLAYBOOK_REGISTRY`, or pass XSS tags.

## 5. Observable Acceptance Criteria
1. Privacy preview leaves zero logs/DB rows containing raw input.
2. Malicious/invalid `.md` uploads (oversized, missing frontmatter, unknown `permitted_playbook_id`, downgraded risk tier) are rejected cleanly with HTTP `400`/`422`.
3. `POST /api/v1/runbooks/search` exposes exact vector similarity, lexical rank, and RRF scores plus explicit `0.78` cosine threshold policy note.

## 6. Verification Commands & Expected Outcomes
- `.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_showcase_inspectors_and_runbooks.py` -> all pass

## 7. Actual Outcomes
- `.\.venv\Scripts\ruff.exe check --config backend/pyproject.toml backend` -> `All checks passed!`
- `.\.venv\Scripts\mypy.exe --config-file backend/pyproject.toml backend/app` -> `Success: no issues found in 47 source files`
- `.\.venv\Scripts\pytest.exe -c backend/pyproject.toml backend/tests/integration/test_showcase_inspectors_and_runbooks.py backend/tests/integration/test_hybrid_rag.py -v` -> `3 passed in 19.80s`.

## 8. Failures Found, Fixes Applied & Re-runs
- Zero failures on first run; cleanly verified privacy 8 KiB + 30/60s rate limit, captured/legacy prompt inspection, XSS/unknown-playbook/risk-downgrade `.md` upload rejections, real Ollama indexing, `0.78` hybrid search explanation, and live `k8s_live` topology facts.

## 9. Documentation Updates, Remaining Blockers & Next Action
- **Next Action:** Proceed to Phase 05 (`05-replay-and-postmortems.md`).
