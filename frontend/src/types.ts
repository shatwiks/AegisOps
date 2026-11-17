export interface AuthConfig {
  issuer: string;
  client_id: string;
  authorization_endpoint: string;
  end_session_endpoint: string;
}

export interface UserSession {
  sub: string;
  email: string;
  roles: string[];
  highest_role: 'viewer' | 'operator' | 'approver';
  auth_method: string;
  totp_enrolled: boolean;
  totp_verified: boolean;
}

export interface K8sLiveFacts {
  available: boolean;
  stale: boolean;
  virtual_cmdb_node?: boolean;
  source?: string;
  observed_at?: string;
  cluster?: string;
  namespace?: string;
  deployment?: string;
  container_name?: string;
  ready_replicas?: number;
  desired_replicas?: number;
  available_replicas?: number;
  updated_replicas?: number;
  replica_label: string;
  image?: string;
  memory_limit?: string;
  rollout_status: string;
  reason?: string;
  stale_reason?: string;
}

export interface RunDiffSummary {
  incident_id: string;
  playbook_id: string;
  status: string;
  before: {
    replicas?: number;
    ready_replicas?: number;
    image?: string;
    memory_limit?: string;
  };
  after: {
    replicas?: number;
    ready_replicas?: number;
    image?: string;
    memory_limit?: string;
    rollout_status?: string;
  };
}

export interface TopologyNode {
  id: string;
  slug: string;
  name: string;
  namespace: string;
  cluster: string;
  asset_type: string;
  criticality: string;
  stateless_eligible: boolean;
  owner_team?: string;
  active_incidents: Array<{ id: string; severity: string; state: string }>;
  downstream_impacted: boolean;
  k8s_live?: K8sLiveFacts;
  selected_run_diff?: RunDiffSummary | null;
}

export interface TopologyEdge {
  id: string;
  source_slug: string;
  target_slug: string;
  dependency_type: string;
  description: string;
}

export interface TopologyResponse {
  edge_semantics: string;
  observed_at?: string;
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

export interface LifecycleStep {
  key: string;
  step: number;
  label: string;
  status: 'completed' | 'running' | 'blocked' | 'failed' | 'pending' | 'not_applicable';
  summary: string;
  timestamp: string | null;
  evidence: Record<string, unknown>;
}

export interface WhyThisAction {
  ai_recommendation_hypothesis: {
    root_cause_summary: string | null;
    proposed_playbook_id: string | null;
    uncertainty_level: string | null;
    reasoning: string | null;
    note: string;
  };
  policy_authorization: {
    proposed_playbook_id: string | null;
    proposed_parameters: Record<string, unknown> | null;
    checks: Record<string, unknown>;
    refusal_reason: string | null;
    state: string;
  };
  questions: {
    what_failed: {
      alertname: string;
      target_asset: string | null;
      severity: string;
      diagnosis_hypothesis: string;
    };
    why_system_thinks_so: {
      sanitized_summary: string;
      evidence_quotes: string[];
      citations: Array<{ slug: string; title: string; vector_similarity: number; lexical_score: number; rrf_score: number }>;
      failing_probes_count: number;
    };
    recommended_action: {
      playbook_id: string | null;
      bounded_parameters: Record<string, unknown>;
    };
    why_allowed_or_blocked: {
      decision_checks: Record<string, unknown>;
      refusal_reason: string | null;
      automation_paused: boolean;
    };
    why_mfa_required: {
      required: boolean;
      rule: string;
      approval_status: string | null;
    };
    what_can_prevent_execution: string[];
    what_happened_afterward: {
      execution_status: string | null;
      before_state: Record<string, unknown> | null;
      after_state: Record<string, unknown> | null;
      verification_state: Record<string, unknown>;
      recovered_probes_count: number;
      final_state: string;
    };
  };
}

export interface IncidentSummary {
  id: string;
  dedup_key: string;
  alert_fingerprint: string;
  alertname: string;
  title: string;
  summary_sanitized: string;
  asset_slug: string | null;
  unknown_asset_identifier: string | null;
  severity: 'P1' | 'P2' | 'P3' | 'P4';
  severity_explanation: Record<string, unknown>;
  state: string;
  source_provenance?: string;
  demo_run_id?: string | null;
  has_captured_prompt?: boolean;
  proposed_playbook_id: string | null;
  proposed_parameters: Record<string, unknown> | null;
  confidence_score: number | null;
  refusal_reason: string | null;
  diagnosis: {
    proposal?: {
      root_cause_summary: string;
      cited_runbook_ids: string[];
      evidence_quotes: string[];
      proposed_playbook_id: string | null;
      uncertainty_level: string;
      refusal_recommended: boolean;
      reasoning: string;
    };
    citations?: Array<{
      slug: string;
      title: string;
      doc_type: string;
      vector_similarity: number;
      lexical_score: number;
      rrf_score: number;
    }>;
    policy_checks?: Record<string, unknown>;
  } | null;
  redaction_stats: {
    total_redactions?: number;
    redaction_counts?: Record<string, number>;
    scrubber_failed_fallback?: boolean;
  };
  verification_state?: {
    status?: string;
    window_seconds?: number;
    elapsed_healthy_seconds?: number;
    reset_count?: number;
    last_reset_reason?: string;
  };
  fault_onset_at: string | null;
  detected_at: string | null;
  ingested_at: string;
  triaged_at: string | null;
  approved_at: string | null;
  mutated_at: string | null;
  first_recovered_at: string | null;
  resolved_at: string | null;
  version_id: number;
  updated_at: string;
}

export interface BusinessProbeSample {
  id: string;
  target_service: string;
  endpoint_path: string;
  probe_type: string;
  status: 'PASS' | 'FAIL' | 'DEGRADED' | 'UNAVAILABLE';
  http_status: number | null;
  latency_ms: number | null;
  summary: string;
  checked_at: string;
}

export interface IncidentDetailResponse {
  incident: IncidentSummary;
  lifecycle_steps?: LifecycleStep[];
  why_this_action?: WhyThisAction;
  business_probes?: BusinessProbeSample[];
  events: Array<{
    id: string;
    sequence_num?: number;
    event_type: string;
    from_state: string | null;
    to_state: string | null;
    actor: string;
    details: Record<string, unknown>;
    created_at: string;
  }>;
  approvals: Array<{
    id: string;
    playbook_id: string;
    playbook_version: string;
    parameters_hash: string;
    parameters: Record<string, unknown>;
    target_asset_slug: string;
    target_k8s_uid: string;
    target_resource_version: string;
    status: string;
    requested_at: string;
    expires_at: string;
    decided_by_email: string | null;
    decided_at: string | null;
    reason: string | null;
  }>;
  executions: Array<{
    id: string;
    playbook_id: string;
    status: string;
    before_state: Record<string, unknown>;
    after_state: Record<string, unknown> | null;
    error: string | null;
    started_at: string;
    completed_at: string | null;
  }>;
  audits: Array<{
    id: string;
    actor_sub: string;
    actor_role: string;
    action_type: string;
    policy_decision: string;
    created_at: string;
  }>;
  blast_radius: {
    upstream_dependencies: Array<{ slug: string; criticality: string; hop: number }>;
    downstream_impacts: Array<{ slug: string; criticality: string; hop: number }>;
    truncated: boolean;
    cycle_detected: boolean;
  };
}

export interface IncidentListResponse {
  items: IncidentSummary[];
  total_filtered: number;
  tab_counts: {
    active: number;
    resolved: number;
    escalated: number;
    failed: number;
    all: number;
    hidden_test_count: number;
  };
  pagination: { offset: number; limit: number; has_more: boolean };
}

export interface TimingSummary {
  sample_count: number;
  mean: number | null;
  p50: number | null;
  p95: number | null;
  min: number | null;
  max: number | null;
}

export interface MetricsSummaryResponse {
  scope?: string;
  total_incidents: number;
  state_counts: Record<string, number>;
  total_phi_pii_redactions: number;
  mttd_unavailable_count: number;
  timings_seconds: {
    mttd: TimingSummary;
    triage_latency: TimingSummary;
    action_latency: TimingSummary;
    verification_window: TimingSummary;
    mttr_end_to_end: TimingSummary;
  };
  business_value?: {
    sensitive_identifiers_redacted: number;
    redaction_definition: string;
    incidents_contained_by_automation: number;
    high_risk_actions_gated_by_mfa: number;
    cmdb_potential_downstream_services: number;
    observed_active_degraded_assets: number;
    business_probe_recoveries_verified: number;
    business_probe_failures_observed: number;
    manual_baseline_comparison: {
      configured: boolean;
      label: string;
      manual_baseline_minutes: number | null;
      observed_mean_autonomous_mttr_minutes?: number | null;
      estimated_engineer_minutes_saved: number | null;
      source: string;
      method?: string;
      note?: string;
    };
  };
  measurement_note: string;
}

export interface ShowcaseOverview {
  project_name: string;
  subtitle: string;
  disclaimer: string;
  role: 'visitor' | 'viewer' | 'operator' | 'approver';
  is_visitor: boolean;
  capabilities: Record<string, boolean>;
  five_pillars: Array<{ title: string; detail: string }>;
}

export interface ReadinessResponse {
  checked_at: string;
  global_status: 'Ready' | 'Degraded' | 'Blocked' | 'Unknown';
  cluster_context?: string;
  namespace?: string;
  automation_control: {
    automation_paused: boolean;
    reason?: string;
    updated_by_email?: string;
    updated_at?: string;
  };
  checks: Record<string, { status: string; detail?: string; context?: string; [k: string]: unknown }>;
  scenarios: Record<string, { status: string; reasons: string[] }>;
}

export interface ScenarioSpec {
  scenario_id: string;
  order: number;
  title: string;
  target_service: string;
  risk_tier: 'LOW' | 'HIGH';
  requires_mfa: boolean;
  expected_outcome: string;
  summary: string;
  replay_fixture_id?: string;
}

export interface DemoRun {
  id: string;
  scenario_id: string;
  title: string;
  target_service: string;
  status: string;
  incident_id: string | null;
  narration_state: {
    step?: number;
    headline?: string;
    detail?: string;
    focus_panel?: string;
  };
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface RunbookSummary {
  id: string;
  slug: string;
  title: string;
  doc_type: 'RUNBOOK' | 'POSTMORTEM';
  service_slug: string;
  alertnames: string[];
  risk_tier: 'LOW' | 'HIGH';
  permitted_playbook_id: string | null;
  executable_in_registry: boolean;
  approval_mode: string;
  version: string;
  source: string;
  tags: string[];
  indexing_status: 'UPLOADED' | 'VALIDATING' | 'INDEXING' | 'READY' | 'FAILED';
  indexing_error: string | null;
  embedding_model: string;
  embedding_dimensions: number;
  symptoms_preview: string;
  updated_at: string;
}

export interface ReplayListItem {
  replay_id: string;
  title: string;
  scenario_id: string | null;
  target_service: string;
  severity: string;
  final_state: string;
  source_type: 'captured_live_run' | 'illustrative_fixture';
  source_badge: string;
  captured_at: string;
}

export interface ReplayFrame {
  frame_index: number;
  seq: number;
  timestamp: string;
  elapsed_seconds: number;
  lifecycle_step: number;
  state: string;
  event_type: string;
  headline: string;
  narration: string;
  active_panel: string;
  watchdog_progress: { status?: string; elapsed_seconds?: number; window_seconds?: number; reset_count?: number };
  topology_overlay: {
    root_service: string;
    downstream_impacted: string[];
    historical_k8s_snapshot: unknown;
  };
  probes_up_to_frame: Array<{ target_service: string; status: string; latency_ms: number | null; summary: string }>;
  why_this_action_snapshot: Record<string, unknown>;
}

export interface ReplayTimeline {
  replay_id: string;
  title: string;
  scenario_id: string | null;
  target_service: string;
  severity: string;
  final_state: string;
  source_type: 'captured_live_run' | 'illustrative_fixture';
  source_badge: string;
  captured_at: string;
  disclaimer: string;
  downstream_impacts: string[];
  frames: ReplayFrame[];
}

export interface EvidenceResponse {
  build: {
    app_version: string;
    python_version: string;
    alembic_revision: string;
    chat_model: string;
    embedding_model: string;
    embedding_dimensions: number;
    cosine_threshold: number;
    sustained_recovery_seconds: number;
    commit: string;
    branch: string;
    dirty_working_tree: boolean | null;
  };
  architecture_boundaries: string[];
  benchmarks: {
    ragas: { model?: string; embedding_model?: string; sample_count?: number; metrics?: Record<string, number>; limitations?: string } | null;
    k6: { total_requests?: number; http_req_duration_p95_ms?: number; checks_passed?: number; checks_failed?: number } | null;
    chaos_scenarios_report_present: boolean;
  };
  test_reports: Array<{ filename: string; modified_at_utc: string; size_bytes: number; excerpt: string }>;
  documentation_links: Array<{ label: string; path: string }>;
}
