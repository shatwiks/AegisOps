# AegisOps Showcase Upgrade — Requirement Traceability Matrix

> Updated across Showcase Phases `00–07`; all 15 features (`Features A–O`) implemented and verified.

| Requirement ID | Implemented Backend Symbols / Routes | Implemented Frontend Components | Verified Tests | Status |
|---|---|---|---|---|
| `REQ-SHOW-A01..A03` | `backend/app/showcase/scenarios.py`, `backend/app/api/showcase.py` (`/scenarios`, `/scenarios/{id}/launch`, `/runs/{id}`), `worker/runner.py` | `ChaosLabPanel.tsx` | `test_showcase_scenarios_and_probes.py`, `test_showcase_browser.py` | `VERIFIED` |
| `REQ-SHOW-B01..B03` | `watchdog.py::verify_sustained_recovery` (`on_sample_callback`), `incidents.py` (`compute_lifecycle_steps`), `stream.py` (`after_seq`) | `LifecycleStepper.tsx`, `IncidentDetail.tsx` | `test_showcase_queue_and_lifecycle.py` | `VERIFIED` |
| `REQ-SHOW-C01..C02` | `entities.py::Incident.source_provenance`, `webhooks.py`, `incidents.py::list_incidents` | `App.tsx` (queue tabs, `Hide Test Runs`, search, sort) | `test_showcase_queue_and_lifecycle.py`, `test_showcase_browser.py` | `VERIFIED` |
| `REQ-SHOW-D01..D02` | `metrics.py::get_metrics_summary`, `api/showcase.py` (`/overview`) | `MetricsDashboard.tsx` | `test_showcase_readiness_and_controls.py`, `test_showcase_browser.py` | `VERIFIED` |
| `REQ-SHOW-E01..E02` | `api/showcase.py` (`/privacy/presets`, `/privacy/preview`), `diagnosis.py::generate_diagnosis_with_record`, `incidents.py` (`/prompt`) | `PrivacyPromptDrawer.tsx` | `test_showcase_inspectors_and_runbooks.py`, `test_showcase_readiness_and_controls.py`, `test_showcase_browser.py` | `VERIFIED` |
| `REQ-SHOW-F01..F03` | `backend/app/api/runbooks.py` (`/api/v1/runbooks`, `/upload`, `/search`, `/{slug}/retry-index`), `worker/runner.py` | `RunbookKnowledgePanel.tsx` | `test_showcase_inspectors_and_runbooks.py`, `test_showcase_browser.py` | `VERIFIED` |
| `REQ-SHOW-G01` | `topology.py::get_topology` + live `KubernetesExecutor.read_deployment_snapshot` 3s TTL cache | `TopologyGraph.tsx` (graph + accessible table) | `test_showcase_inspectors_and_runbooks.py`, `test_showcase_browser.py` | `VERIFIED` |
| `REQ-SHOW-H01` | `showcase/postmortem.py`, `showcase/pdf_renderer.py`, `incidents.py` (`/postmortem.md`, `/postmortem.pdf`) | `IncidentDetail.tsx` | `test_showcase_replay_and_postmortem.py` | `VERIFIED` |
| `REQ-SHOW-I01` | `DemoRun.narration_state_json`, `replay.py` | `GuidedTourBar.tsx`, `App.tsx` | `test_showcase_browser.py` | `VERIFIED` |
| `REQ-SHOW-J01` | `showcase/probes.py`, `entities.py::BusinessProbeSample`, `api/showcase.py` (`/probes`, `/probes/run`) | `BusinessProbeCard.tsx` | `test_showcase_scenarios_and_probes.py`, `test_showcase_browser.py` | `VERIFIED` |
| `REQ-SHOW-K01` | `incidents.py` (`build_why_this_action` structured card payload) | `DecisionExplanationCard.tsx` | `test_showcase_queue_and_lifecycle.py`, `test_showcase_inspectors_and_runbooks.py` | `VERIFIED` |
| `REQ-SHOW-L01` | `showcase/replay.py`, `api/showcase.py` (`/replays`, `/replays/{id}`) | `ReplayController.tsx`, `App.tsx` | `test_showcase_replay_and_postmortem.py`, `test_showcase_browser.py` | `VERIFIED` |
| `REQ-SHOW-M01..M03` | `api/showcase.py` (`/readiness`, `/reset/preview`, `/reset/execute`, `/controls/automation`) | `ChaosLabPanel.tsx`, `App.tsx` | `test_showcase_readiness_and_controls.py`, `test_showcase_browser.py` | `VERIFIED` |
| `REQ-SHOW-N01` | `api/showcase.py` (`/evidence`) parsing real `docs/evidence/*` & git metadata | `EngineeringEvidenceView.tsx` | `test_showcase_browser.py` | `VERIFIED` |
| `REQ-SHOW-O01..O02` | `oidc.py::optional_authenticate_request`, route dependency guards | `App.tsx` (Visitor Mode + Executive/Technical view toggle) | `test_showcase_readiness_and_controls.py`, `test_showcase_browser.py` | `VERIFIED` |
