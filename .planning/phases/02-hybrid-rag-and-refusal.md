# Phase 2 — Hybrid RAG and Refusal Gate

## 1. Objective, Scope, Dependencies, and Requirement IDs
- **Objective**: Author 18 SRE runbooks and synthetic postmortems, generate verified 768-dim Ollama embeddings (`nomic-embed-text:latest`), implement PostgreSQL FTS + `pgvector` hybrid retrieval with Reciprocal Rank Fusion (`k=60`), implement Ollama `llama3.2:3b` schema-constrained diagnosis with prompt-injection boundaries, enforce server-side policy refusal/eligibility gates, and wire sanitized Langfuse tracing and Ragas evaluation.
- **Dependencies**: Phase 1 `VERIFIED`, Ollama running on `127.0.0.1:11434`.
- **Requirement IDs**: `REQ-RAG-01..09`, `REQ-OBS-04` (initial).

## 2. Entry Criteria and Findings
- Phase 1 `runbooks` schema, `incidents`, `outbox_jobs`, and `scrubber` must be verified.

## 3. Implementation Tasks
- [x] Author 15 SRE runbooks + 3 synthetic postmortems under `runbooks/` covering all demo scenarios plus non-automatable escalation cases (`RB-011` DB failover boundary).
- [x] Implement `backend/app/rag/embeddings.py` (Ollama `/api/embed`, 768-dim validation, digest tracking, reindex check).
- [x] Implement `backend/app/rag/retriever.py` (PG FTS `ts_rank_cd`, pgvector cosine similarity, RRF fusion).
- [x] Implement `backend/app/rag/diagnosis.py` (Ollama `/api/chat` JSON schema `DiagnosisProposal`, XML untrusted delimiters, Pydantic validation).
- [x] Implement `backend/app/policy/engine.py` (applicability check, similarity/lexical gate, playbook registry binding, refusal/escalation vs approval vs auto-execute).
- [x] Implement `backend/app/observability/langfuse_tracer.py` and `backend/app/observability/ragas_eval.py`.
- [x] Update `backend/app/seed/runbook_seed.py` and `scripts/seed.ps1`.
- [x] Write unit & live-Ollama integration tests (`test_policy_refusal.py`, `test_hybrid_rag.py`, `test_ollama_diagnosis.py`).

## 4. Interfaces, Schemas, Data Flow, and Phase Decisions
- Model output never directly controls shell commands, K8s namespaces, targets, image tags, or risk tiers; policy resolves those solely from `PLAYBOOK_REGISTRY` and `assets` rows.
- `0.78` cosine similarity is treated as an explicit configurable heuristic alongside lexical match checks, distinct from RRF rank and model uncertainty.

## 5. Acceptance Criteria (Observable Behavior)
1. 18 runbooks/postmortems ingest idempotently with 768-dim vectors and FTS `tsvector`.
2. Lexical retrieval boosts exact error-code matches (`ERR_PG_POOL_TIMEOUT_57P03`) above vector-only retrieval in test cases.
3. Dimension mismatch or embedding model change triggers explicit reindex/failure guard rather than silent corruption.
4. Real Ollama smoke test produces valid Pydantic `DiagnosisProposal` citing seeded runbooks.
5. Prompt-injection payloads, out-of-distribution alerts, unknown playbooks, malformed LLM output, and Ollama timeouts result in safe `ESCALATED` refusal with zero command execution.

## 6. Verification Commands, Working Directory, and Expected Outcomes
- Working directory: repo root
- Required services: `aegisops-postgres`, `aegisops-redis`, Ollama (`127.0.0.1:11434`)
- Commands:
  - `.\scripts\seed.ps1` -> embeds and seeds all 18 runbooks/postmortems
  - `.venv\Scripts\pytest.exe backend/tests/unit/test_policy_refusal.py backend/tests/integration/test_hybrid_rag.py backend/tests/integration/test_ollama_diagnosis.py -v` -> all pass

## 7. Actual Results
- **Timestamp**: `2026-11-17T05:27:31+05:30`
- **Check Results**:
  - `.\scripts\seed.ps1` -> `PASS` (`{'runbooks': 15, 'postmortems': 3, 'total': 18}` embedded with `nomic-embed-text:latest` 768 dims)
  - `ruff check` & `mypy` (26 source files) -> `PASS`
  - `pytest -c backend/pyproject.toml backend/tests -v` -> `PASS` (`50 passed in 23.70s` including live Ollama `llama3.2:3b` structured diagnosis, injection refusal, OOD refusal, and lexical FTS RRF boost)
- **Evidence Path**: [phase-02-hybrid-rag-refusal.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/evidence/phase-02-hybrid-rag-refusal.txt)

## 8. Defects Found and Fixes Made
1. Initial `Start-Process ollama serve` exited with the ephemeral PowerShell session; started `ollama serve` via persistent daemon (`IsDaemon: true`) on `127.0.0.1:11434`.
2. `llama3.2:3b` omitted `cited_runbook_ids` until `DiagnosisProposal` marked `cited_runbook_ids` and `evidence_quotes` required (`...`, `min_length=1`) with clear `Field(description=...)` guidance in `backend/app/rag/diagnosis.py`.
3. Updated `test_hybrid_rag.py` lexical check to assert `hits[0].lexical_rank in (1, 2)` and `vector_rank > 5` (reflecting that `pm-001` and `rb-002` tied on `ts_rank_cd=0.3` and RRF pushed `rb-002` from vector rank 12 to rank 1 overall).

## 9. Documentation Updates and Exit Checklist
- [x] Record exact Ollama digests/versions in `docs/DEPENDENCIES.md`.
- [x] Update `.planning/REQUIREMENTS.md` (`REQ-RAG-*`) and `.planning/STATE.md`.
- [x] Save sanitized test results to `docs/evidence/phase-02-hybrid-rag-refusal.txt`.

## 10. Current Status and Next Action
- **Status**: `VERIFIED`
- **Next Action**: Begin Phase 3 — Durable Remediation and Verified Recovery (`03-remediation-and-recovery.md`).
