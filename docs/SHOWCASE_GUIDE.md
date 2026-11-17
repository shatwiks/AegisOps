# AegisOps Showcase Guide (`docs/SHOWCASE_GUIDE.md`)

> **Disclaimer:** AegisOps is an independent technical engineering demonstration operating strictly on synthetic healthcare data inside a local workstation cluster (`kind-aegisops-local`). It implies no affiliation with any healthcare organization, no regulatory certification (such as HIPAA/HITRUST), and no readiness for clinical use.

---

## 1. Ten-Second Plain-English Pitch

**AegisOps** watches synthetic microservices, strips sensitive identifiers before touching AI or databases, maps which dependent services are affected, searches engineering runbooks, fixes safe failures autonomously, holds high-risk fixes behind human MFA approval, checks 60 seconds of real recovery health, and records every proof in downloadable postmortems.

---

## 2. Audience Roles vs. Presentation Modes

AegisOps enforces a hard distinction between **UI detail level** (`Executive Overview` vs. `Technical Deep-Dive`) and **Server Authorization**:

| Role | Identity | What It Can Do | What It Cannot Do |
|---|---|---|---|
| **Visitor** (default unauthenticated view) | Anonymous | View Overview, CMDB Topology + Live K8s replicas, Recorded Incident Replay, Privacy Scrubber Playground, Runbook Browser, Hybrid Search Tester, Business Probe history, Engineering Evidence | Launch chaos scenarios, run live business probes, view operational incident queue/prompts, upload `.md` runbooks, reset baseline, approve MFA |
| **Viewer** | `viewer@aegisops.local` | All Visitor views + view live filtered Incident Queue (`Active` / `Resolved` / `Escalated` / `Failed` / `All`), Inspect Captured Prompts, Export `.md`/`.pdf` Postmortems | Launch chaos, trigger probes, upload runbooks, toggle pause, reset baseline, approve MFA |
| **Operator** | `operator@aegisops.local` | All Viewer capabilities + Launch 5 Chaos Lab scenarios, trigger `Check Patient Eligibility` probes, Upload validated `.md` runbooks, Toggle `Pause Automation`, Execute `Restore Demo Baseline` | Approve or deny `HIGH`-risk TOTP MFA actions (rollback / memory limit increase) |
| **Approver** | `approver@aegisops.local` | All Operator capabilities + Enroll TOTP authenticator (`Enroll TOTP MFA`) and approve/deny action-bound `HIGH`-risk playbooks | Bypass CMDB allowlist, register new playbooks via Markdown, or force database failover |

---

## 3. Five One-Click Chaos Lab Scenarios

1. **`traffic_spike` (`LOW` risk, autonomous)**: Sends sustained concurrent load to `provider-directory`; Prometheus tail-latency gauge triggers `ProviderDirectoryHighLatencyCpu`, Hybrid RAG matches `RB-003`, Kubernetes scales `1 -> 3` replicas, Watchdog confirms 60s stability.
2. **`db_pool_freeze` (`LOW` risk, autonomous)**: Saturates `eligibility-api` simulated DB connection pool (`ERR_PG_POOL_TIMEOUT_57P03`) while `postgres-claims-db` remains healthy; Hybrid RAG matches `RB-002`/`PM-001`, worker performs `stateless_deployment_restart`, Watchdog verifies recovery.
3. **`bad_canary_update` (`HIGH` risk, MFA required)**: Injects HTTP 500 regression on `eligibility-api` (`ERR_CANARY_IMG_SHA_BAD_9921`, `v1.9.0-broken`); policy forces target image from `assets.known_good_image` (`aegisops/eligibility-api:v1.0.0-good`) and waits for `approver` 6-digit TOTP before rolling back.
4. **`oom_memory_crash` (`HIGH` risk, MFA required)**: Triggers memory saturation on `claims-processor` (`ERR_OOM_EXIT_137_CLAIMS_BATCH`); policy requires `approver` TOTP before `memory_limit_increase_bounded` patches `192Mi -> 384Mi` (within `[128Mi, 512Mi]` ceiling).
5. **`pii_leak_and_db_failure` (`HIGH` risk, refusal/escalation)**: Injects synthetic PII/credentials (`SSN`, `Member ID`, `Email`, `Bearer` token) plus `ERR_PG_REPLICATION_LAG` targeting stateful `postgres-claims-db`; scrubber redacts tokens in memory before storage/AI, and `RB-011` refuses automation -> `ESCALATED`.

---

## 4. Walkthrough of Key Console Capabilities

- **Guided Demo & Recorded Replay**:
  - **Operators**: Click `Start Guided Demo` on any scenario card; narration follows persisted backend milestones cleanly without faking timers.
  - **Visitors**: Click `Start Guided Demo (Recorded Replay)` or `Recorded Replay` in the header to step/play/seek (`1x`/`2x`/`4x`) through recorded or illustrative timelines with a clear `RECORDED REPLAY — No live cluster changes` banner.
- **Business Transaction Recovery Probe (`BusinessProbeCard.tsx`)**: Click `Check Patient Eligibility` (or test `claims-processor`, `provider-directory`, `postgres-claims-db`) to verify real semantic JSON transaction recovery alongside latency.
- **Privacy Scrubber Playground (`PrivacyPromptDrawer.tsx`)**: Paste fictional log snippets or pick one of the 3 presets to observe exact token redactions in memory (8 KiB max, 30 req/60s rate limit, zero DB/log persistence).
- **Runbook Browser, Validated `.md` Upload & Hybrid Search Tester (`RunbookKnowledgePanel.tsx`)**: Inspect Markdown knowledge docs, upload custom `.md` runbooks (`UPLOADED -> VALIDATING -> INDEXING -> READY`, enforcing `PLAYBOOK_REGISTRY` checks), and run live `Test Hybrid Search` queries inspecting lexical FTS score vs `pgvector` cosine similarity vs RRF (`k=60`) vs `0.78` threshold.
- **Incident Lifecycle, Why This Action & Postmortem Export (`IncidentDetail.tsx`)**: Track real 7-step milestones including live `"Checking service stability: X of 60 seconds observed"`, inspect AI hypothesis vs policy boundaries, and download sanitized `.md` and multi-page `%PDF-1.4` postmortems.
- **Baseline Reset & Pause Automation (`ChaosLabPanel.tsx`)**: Preview exact deployment diffs with `Restore Demo Baseline` (audit history preserved; any interrupted active runs are labeled `manual_reset_assisted`), or pause new autonomous dispatches with `Pause Automation`.
