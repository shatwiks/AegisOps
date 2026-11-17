# Graph Report - AegisOps An Autonomous AIOps, CMDB Blast-Radius & Self-Healing Kubernetes Control  (2026-11-17)

## Corpus Check
- 203 files · ~97,571 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 12 file(s) not represented in the graph (top: (none) 5, .tmpl 2, .example 1)

## Summary
- 1569 nodes · 3727 edges · 98 communities (75 shown, 23 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 385 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 97

## God Nodes (most connected - your core abstractions)
1. `Settings` - 87 edges
2. `Asset` - 67 edges
3. `Incident` - 64 edges
4. `KubernetesExecutor` - 54 edges
5. `get_settings()` - 53 edges
6. `AuthenticatedUser` - 50 edges
7. `create_app()` - 34 edges
8. `ApprovalRequest` - 34 edges
9. `OutboxJob` - 31 edges
10. `IncidentEvent` - 30 edges

## Surprising Connections (you probably didn't know these)
- `main_async()` --calls--> `get_settings()`  [EXTRACTED]
  chaos/run_scenario.py → backend/app/config.py
- `main()` --calls--> `get_settings()`  [EXTRACTED]
  scripts/send_synthetic_alert.py → backend/app/config.py
- `approve_high_risk_action()` --uses--> `AuthenticatedUser`  [INFERRED]
  backend/app/api/approvals.py → backend/app/auth/oidc.py
- `approve_high_risk_action()` --uses--> `Settings`  [INFERRED]
  backend/app/api/approvals.py → backend/app/config.py
- `approve_high_risk_action()` --uses--> `IncidentState`  [INFERRED]
  backend/app/api/approvals.py → backend/app/domain/state_machine.py

## Import Cycles
- None detected.

## Communities (98 total, 23 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (22): build_json_log_audit_safe(), _extract_section(), get_runbook_detail(), HybridSearchTestRequest, index_runbook_by_slug(), list_runbooks(), parse_and_validate_uploaded_markdown(), process_runbook_indexing_job() (+14 more)

### Community 1 - "Community 1"
Cohesion: 0.11
Nodes (8): Asset, AuditRecord, Base, IncidentEvent, SystemControlFlag, utcnow(), _fetch_token(), test_readiness_rbac_pause_control_and_baseline_reset()

### Community 2 - "Community 2"
Cohesion: 0.10
Nodes (23): AutomationControlRequest, BusinessProbeRunRequest, PrivacyPreviewRequest, _read_git_meta_sync(), ResetExecuteRequest, _safe_read_json(), ScenarioLaunchRequest, showcase_engineering_evidence() (+15 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (14): record_sanitized_llm_trace(), run_local_ragas_evaluation(), evaluate_redaction_corpus(), _normalize_key(), scrub_alertmanager_payload(), scrub_text(), scrub_value(), ScrubResult (+6 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (18): PlaybookSpec, validate_playbook_for_asset(), evaluate_remediation_policy(), PolicyDecision, build_diagnosis_prompt(), DiagnosisInvocationError, DiagnosisProposal, generate_diagnosis() (+10 more)

### Community 5 - "Community 5"
Cohesion: 0.10
Nodes (10): execute_remediation_attempt(), KubernetesExecutor, _patch(), _read(), KubernetesGuardError, TargetSnapshot, execute_demo_baseline_reset(), RedisTargetLease (+2 more)

### Community 6 - "Community 6"
Cohesion: 0.05
Nodes (40): env, runs-on, services, steps, AEGISOPS_DATABASE_URL, AEGISOPS_ENV, AEGISOPS_REDIS_URL, AEGISOPS_SESSION_SECRET (+32 more)

### Community 7 - "Community 7"
Cohesion: 0.06
Nodes (37): env, image, imagePullPolicy, livenessProbe, name, ports, readinessProbe, resources (+29 more)

### Community 8 - "Community 8"
Cohesion: 0.06
Nodes (37): env, image, imagePullPolicy, livenessProbe, name, ports, readinessProbe, resources (+29 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (37): env, image, imagePullPolicy, livenessProbe, name, ports, readinessProbe, resources (+29 more)

### Community 10 - "Community 10"
Cohesion: 0.11
Nodes (11): build_engine(), build_session_factory(), get_db_session(), AssetDependency, _main(), seed_cmdb(), _main(), test_cycle_safe_traversal_and_duplicate_names_across_namespaces() (+3 more)

### Community 11 - "Community 11"
Cohesion: 0.07
Nodes (33): env, image, name, ports, readinessProbe, resources, apiVersion, kind (+25 more)

### Community 12 - "Community 12"
Cohesion: 0.13
Nodes (16): OutboxJob, execute_demo_scenario_job(), _AutomationPausedHold, claim_next_outbox_job(), _dispatch_claimed_job(), _handle_execute_job(), _handle_triage_job(), _handle_verify_job() (+8 more)

### Community 13 - "Community 13"
Cohesion: 0.07
Nodes (32): image, name, ports, readinessProbe, resources, apiVersion, kind, metadata (+24 more)

### Community 14 - "Community 14"
Cohesion: 0.08
Nodes (30): dependencies, lucide-react@0.474.0, qrcode.react@4.2.0, react@18.3.1, react-dom@18.3.1, @xyflow/react@12.4.4, devDependencies, @types/react@18.3.18 (+22 more)

### Community 15 - "Community 15"
Cohesion: 0.10
Nodes (8): check_postgres_ready(), create_app(), lifespan(), readyz(), get_app(), get_request_session(), build_redis_client(), check_redis_ready()

### Community 16 - "Community 16"
Cohesion: 0.22
Nodes (11): _drive_traffic(), _get_approver_token_and_totp(), main(), main_async(), _patch_k8s_raw(), run_scenario_1(), run_scenario_2(), run_scenario_3() (+3 more)

### Community 17 - "Community 17"
Cohesion: 0.14
Nodes (9): auth_logout(), auth_me(), auth_public_config(), oidc_pkce_exchange(), PkceExchangeRequest, totp_enroll(), totp_verify_enrollment(), TotpVerifyRequest (+1 more)

### Community 18 - "Community 18"
Cohesion: 0.19
Nodes (10): _apply_incident_filters(), build_why_this_action(), export_postmortem_markdown(), export_postmortem_pdf(), get_incident_detail(), get_incident_prompt_inspector(), list_incidents(), _load_postmortem_snapshot() (+2 more)

### Community 19 - "Community 19"
Cohesion: 0.13
Nodes (12): compute_lifecycle_steps(), showcase_get_run(), ApprovalRequest, DemoRun, Incident, build_narration_from_incident(), _conflicting_services(), launch_demo_scenario() (+4 more)

### Community 20 - "Community 20"
Cohesion: 0.14
Nodes (10): collect_health_sample(), HealthProbeSample, query_prometheus_scalar(), verify_sustained_recovery(), _elig_asset(), test_watchdog_refuses_readiness_when_metrics_missing_or_unhealthy(), test_watchdog_requires_unbroken_sustained_healthy_window(), fake_probe() (+2 more)

### Community 21 - "Community 21"
Cohesion: 0.08
Nodes (23): timeout, verbosity, exporters, debug, endpoint, endpoint, exporters, processors (+15 more)

### Community 22 - "Community 22"
Cohesion: 0.16
Nodes (5): PdfLine, sanitize_pdf_text(), SimplePdfDocument, render_postmortem_pdf(), _extract_pdf_text()

### Community 23 - "Community 23"
Cohesion: 0.11
Nodes (6): do_run_migrations(), run_async_migrations(), run_migrations_offline(), run_migrations_online(), upgrade(), upgrade()

### Community 24 - "Community 24"
Cohesion: 0.14
Nodes (7): authenticate_request(), derive_roles_from_claims(), exchange_pkce_code(), optional_authenticate_request(), require_role(), _dependency(), verify_session_cookie()

### Community 25 - "Community 25"
Cohesion: 0.18
Nodes (17): App(), handleLogin(), handleLogout(), initAuth(), IncidentDetail(), handleApprove(), handleDeny(), handleDownload() (+9 more)

### Community 26 - "Community 26"
Cohesion: 0.15
Nodes (17): DecisionExplanationCard(), Props, Props, LifecycleStepper(), Props, AuthConfig, IncidentDetailResponse, IncidentListResponse (+9 more)

### Community 27 - "Community 27"
Cohesion: 0.14
Nodes (6): get_asset_blast_radius(), get_topology(), BlastRadiusNode, compute_severity(), get_blast_radius(), _traverse_direction()

### Community 28 - "Community 28"
Cohesion: 0.19
Nodes (6): _sign_body(), test_webhook_auth_ssrf_scrubbing_dedup_and_append_only_audit(), test_outbox_skip_locked_and_expired_lease_recovery(), test_redis_lease_ownership_contention_and_loss(), _fetch_token(), test_privacy_playground_prompt_inspector_runbook_upload_search_and_live_topology()

### Community 29 - "Community 29"
Cohesion: 0.18
Nodes (9): adjudicate_claim(), _get_memory_limit_bytes(), _get_working_set_mb(), healthz(), MemoryFaultRequest, readyz(), _refresh_memory_gauges(), set_memory_demand() (+1 more)

### Community 30 - "Community 30"
Cohesion: 0.11
Nodes (17): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleDetection, moduleResolution (+9 more)

### Community 31 - "Community 31"
Cohesion: 0.13
Nodes (6): _contains_forbidden_fetch_directive(), _enforce_rate_limit(), ingest_alertmanager_webhook(), _parse_iso_timestamp(), _resolve_asset(), _verify_webhook_auth()

### Community 32 - "Community 32"
Cohesion: 0.22
Nodes (5): _fetch_keycloak_token(), test_oidc_rbac_totp_replay_drift_and_concurrent_approval_race(), _fetch_token(), test_business_probes_launch_conflicts_and_scenario5_pii_db_escalation(), main()

### Community 33 - "Community 33"
Cohesion: 0.21
Nodes (13): MainNav, QueueTab, Props, ResetPreviewResult, EngineeringEvidenceView(), Props, GuidedTourBar(), Props (+5 more)

### Community 34 - "Community 34"
Cohesion: 0.12
Nodes (17): DATABASE_URL, ENCRYPTION_KEY, LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES, LANGFUSE_INIT_ORG_ID, LANGFUSE_INIT_ORG_NAME, LANGFUSE_INIT_PROJECT_ID, LANGFUSE_INIT_PROJECT_NAME, LANGFUSE_INIT_PROJECT_PUBLIC_KEY (+9 more)

### Community 35 - "Community 35"
Cohesion: 0.12
Nodes (16): alerting, alertmanagers, static_configs, global, evaluation_interval, scrape_interval, cluster, namespace (+8 more)

### Community 36 - "Community 36"
Cohesion: 0.17
Nodes (5): approve_high_risk_action(), ApproveActionRequest, deny_high_risk_action(), DenyActionRequest, transition_incident()

### Community 37 - "Community 37"
Cohesion: 0.17
Nodes (4): get_settings(), _gather_samples(), main(), test_healthz_and_readyz_against_real_postgres_and_redis()

### Community 39 - "Community 39"
Cohesion: 0.17
Nodes (7): ExecutionAttempt, get_replay_timeline(), list_available_replays(), _panel_for_event(), _step_for_state(), _fetch_token(), test_recorded_replay_and_unified_markdown_pdf_postmortem_exports()

### Community 40 - "Community 40"
Cohesion: 0.15
Nodes (4): configure_telemetry(), metrics(), prometheus_middleware(), _refresh_recent_p95()

### Community 41 - "Community 41"
Cohesion: 0.12
Nodes (15): description, summary, groups, name, rules, cluster, error_code, namespace (+7 more)

### Community 42 - "Community 42"
Cohesion: 0.22
Nodes (6): BlastRadiusResult, build_postmortem_snapshot(), _delta_seconds(), _escape_md(), render_postmortem_markdown(), _safe_text()

### Community 43 - "Community 43"
Cohesion: 0.13
Nodes (15): KC_BOOTSTRAP_ADMIN_PASSWORD, KC_BOOTSTRAP_ADMIN_USERNAME, KC_HOSTNAME, KC_HOSTNAME_STRICT, KC_HTTP_ENABLED, command, container_name, environment (+7 more)

### Community 44 - "Community 44"
Cohesion: 0.20
Nodes (6): _check_dependencies(), check_eligibility(), FaultToggle, healthz(), readyz(), set_fault()

### Community 45 - "Community 45"
Cohesion: 0.14
Nodes (3): Import-DotEnv(), New-FernetKey(), New-RandomHex()

### Community 46 - "Community 46"
Cohesion: 0.14
Nodes (13): jobs, live-cluster-e2e, runs-on, steps, name, on, workflow_dispatch, if (+5 more)

### Community 47 - "Community 47"
Cohesion: 0.18
Nodes (14): interval, retries, test, timeout, healthcheck, command, container_name, healthcheck (+6 more)

### Community 48 - "Community 48"
Cohesion: 0.24
Nodes (6): CpuFaultToggle, healthz(), _is_pressure_enabled(), readyz(), search_providers(), toggle_cpu_pressure()

### Community 49 - "Community 49"
Cohesion: 0.26
Nodes (5): IncidentState, InvalidStateTransitionError, validate_transition(), test_illegal_transitions_rejected(), test_valid_transitions_allowed()

### Community 50 - "Community 50"
Cohesion: 0.17
Nodes (11): apiVersion, containerPort, hostPort, listenAddress, protocol, kind, name, nodes (+3 more)

### Community 51 - "Community 51"
Cohesion: 0.17
Nodes (12): apiVersion, kind, metadata, roleRef, subjects, ClusterRoleBinding aegisops-kube-state-metrics, apiGroup, kind (+4 more)

### Community 52 - "Community 52"
Cohesion: 0.31
Nodes (4): enroll_user_totp(), _fernet(), verify_and_consume_totp(), UserTotpSecret

### Community 53 - "Community 53"
Cohesion: 0.18
Nodes (11): POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER, container_name, environment, image, networks, ports (+3 more)

### Community 54 - "Community 54"
Cohesion: 0.20
Nodes (6): Props, RunbookKnowledgePanel(), retryIndex(), SearchHit, SearchResponse, RunbookSummary

### Community 55 - "Community 55"
Cohesion: 0.20
Nodes (10): command, container_name, extra_hosts, image, networks, ports, profiles, restart (+2 more)

### Community 56 - "Community 56"
Cohesion: 0.20
Nodes (10): postgres, container_name, depends_on, image, networks, ports, profiles, restart (+2 more)

### Community 57 - "Community 57"
Cohesion: 0.20
Nodes (10): command, container_name, extra_hosts, image, networks, ports, profiles, restart (+2 more)

### Community 58 - "Community 58"
Cohesion: 0.20
Nodes (10): command, container_name, extra_hosts, image, networks, ports, profiles, restart (+2 more)

### Community 60 - "Community 60"
Cohesion: 0.25
Nodes (5): BusinessProbeCard(), PROBE_TARGETS, Props, BusinessProbeSample, react

### Community 61 - "Community 61"
Cohesion: 0.22
Nodes (9): Service kube-state-metrics, nodePort, port, targetPort, apiVersion, kind, spec, ports (+1 more)

### Community 62 - "Community 62"
Cohesion: 0.39
Nodes (4): collect_system_readiness(), get_automation_flag(), preview_demo_baseline_reset(), set_automation_flag()

### Community 64 - "Community 64"
Cohesion: 0.25
Nodes (5): Preset, PreviewResult, PrivacyPromptDrawer(), PromptInspectorData, Props

### Community 65 - "Community 65"
Cohesion: 0.25
Nodes (8): apiVersion, kind, metadata, rules, ClusterRole aegisops-kube-state-metrics, apiGroups, resources, verbs

### Community 66 - "Community 66"
Cohesion: 0.38
Nodes (3): execute_business_probe(), list_business_probes(), serialize_probe()

### Community 67 - "Community 67"
Cohesion: 0.38
Nodes (3): test_invalid_settings_rejected(), test_valid_settings_succeed(), _valid_kwargs()

### Community 68 - "Community 68"
Cohesion: 0.43
Nodes (6): NODE_POSITIONS, Props, shortImageTag(), TopologyGraph(), TopologyInner(), TopologyResponse

### Community 69 - "Community 69"
Cohesion: 0.29
Nodes (6): driver, name, name, networks, aegisops_net, services

### Community 70 - "Community 70"
Cohesion: 0.29
Nodes (7): name, name, name, volumes, aegisops_pgdata, aegisops_promdata, aegisops_redisdata

### Community 71 - "Community 71"
Cohesion: 0.29
Nodes (6): apiVersion, kind, ServiceAccount kube-state-metrics, Deployment kube-state-metrics, apiVersion, kind

### Community 73 - "Community 73"
Cohesion: 0.47
Nodes (5): MetricsDashboard(), Props, TimingCard(), MetricsSummaryResponse, TimingSummary

### Community 74 - "Community 74"
Cohesion: 0.47
Nodes (5): Props, ReplayController(), ReplayFrame, ReplayListItem, ReplayTimeline

### Community 75 - "Community 75"
Cohesion: 0.33
Nodes (6): args, image, name, ports, resources, containers

### Community 76 - "Community 76"
Cohesion: 0.33
Nodes (6): spec, app, app, matchLabels, replicas, selector

### Community 77 - "Community 77"
Cohesion: 0.33
Nodes (6): app, labels, serviceAccountName, template, metadata, spec

### Community 82 - "Community 82"
Cohesion: 0.60
Nodes (5): metadata, name, namespace, metadata, metadata

## Knowledge Gaps
- **1 isolated node(s):** `aegisops-backend`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 727 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Community 38` to `Community 0`, `Community 1`, `Community 3`, `Community 4`, `Community 5`, `Community 10`, `Community 12`, `Community 15`, `Community 17`, `Community 19`, `Community 20`, `Community 24`, `Community 31`, `Community 36`, `Community 37`, `Community 52`, `Community 62`, `Community 66`, `Community 67`, `Community 78`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Are the 46 inferred relationships involving `Settings` (e.g. with `approve_high_risk_action()` and `auth_public_config()`) actually correct?**
  _`Settings` has 46 INFERRED edges - model-reasoned connections that need verification._
- **What connects `aegisops-backend` to the rest of the system?**
  _1 weakly-connected nodes found - possible missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.0642243328810493 - nodes in this community are weakly interconnected._
- **Why does `Incident` connect `Community 19` to `Community 32`, `Community 1`, `Community 2`, `Community 36`, `Community 5`, `Community 39`, `Community 72`, `Community 27`, `Community 42`, `Community 10`, `Community 12`, `Community 18`, `Community 59`, `Community 28`, `Community 62`, `Community 31`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Are the 36 inferred relationships involving `Asset` (e.g. with `approve_high_risk_action()` and `_apply_incident_filters()`) actually correct?**
  _`Asset` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.10693877551020409 - nodes in this community are weakly interconnected._