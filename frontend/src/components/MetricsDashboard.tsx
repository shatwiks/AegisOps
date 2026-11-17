import type { MetricsSummaryResponse, TimingSummary } from '../types';

interface Props {
  metrics: MetricsSummaryResponse | null;
  scope: 'live_and_demo' | 'automated_test' | 'all';
  baselineMinutesInput: string;
  technicalMode: boolean;
  onChangeScope: (scope: 'live_and_demo' | 'automated_test' | 'all') => void;
  onChangeBaselineInput: (val: string) => void;
  onApplyBaseline: () => void;
}

function TimingCard({ label, data }: { label: string; data: TimingSummary }) {
  return (
    <div className="metric-tile">
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {data.p50 !== null ? `${data.p50}s` : 'N/A'}
      </div>
      <div className="metric-sub">
        n={data.sample_count} · mean={data.mean ?? '—'}s · p95={data.p95 ?? '—'}s
      </div>
    </div>
  );
}

export function MetricsDashboard({
  metrics,
  scope,
  baselineMinutesInput,
  technicalMode,
  onChangeScope,
  onChangeBaselineInput,
  onApplyBaseline,
}: Props) {
  if (!metrics) {
    return <div className="card">Loading measured operational metrics...</div>;
  }

  const bv = metrics.business_value;
  const baseline = bv?.manual_baseline_comparison;

  return (
    <section className="card" aria-label="Measured Value & Operational Metrics">
      <div className="section-head">
        <div>
          <h3>Measured Value &amp; Operational Timings</h3>
          <span className="muted" style={{ fontSize: '0.8rem' }}>
            Total in scope: {metrics.total_incidents} · Sensitive identifiers redacted: {metrics.total_phi_pii_redactions}
          </span>
        </div>
        <div className="header-controls">
          <select
            aria-label="Metrics incident scope"
            value={scope}
            onChange={(e) => onChangeScope(e.target.value as 'live_and_demo' | 'automated_test' | 'all')}
          >
            <option value="live_and_demo">Scope: Live &amp; Demo</option>
            <option value="all">Scope: All Runs</option>
            <option value="automated_test">Scope: Automated Tests Only</option>
          </select>
        </div>
      </div>

      {bv && (
        <div className="metrics-grid" style={{ marginBottom: '0.75rem' }}>
          <div className="metric-tile tile-highlight">
            <div className="metric-label">Identifiers Redacted (Boundary)</div>
            <div className="metric-value">{bv.sensitive_identifiers_redacted}</div>
            <div className="metric-sub">Stripped tokens (not distinct patients)</div>
          </div>
          <div className="metric-tile">
            <div className="metric-label">Autonomously Contained</div>
            <div className="metric-value">{bv.incidents_contained_by_automation}</div>
            <div className="metric-sub">Resolved via verified rollout</div>
          </div>
          <div className="metric-tile">
            <div className="metric-label">MFA-Gated High-Risk Actions</div>
            <div className="metric-value">{bv.high_risk_actions_gated_by_mfa}</div>
            <div className="metric-sub">Action-bound TOTP enforcement</div>
          </div>
          <div className="metric-tile">
            <div className="metric-label">Business Probe Recoveries</div>
            <div className="metric-value">
              {bv.business_probe_recoveries_verified} PASS
            </div>
            <div className="metric-sub">
              {bv.business_probe_failures_observed} FAIL/DEGRADED observed
            </div>
          </div>
          <div className="metric-tile">
            <div className="metric-label">Manual Baseline Comparison</div>
            <div className="metric-value" style={{ fontSize: '1.05rem' }}>
              {baseline?.configured && baseline.estimated_engineer_minutes_saved !== null
                ? `~${baseline.estimated_engineer_minutes_saved} min saved`
                : 'Baseline not configured'}
            </div>
            <div className="metric-sub">{baseline?.label || 'No hardcoded baseline'}</div>
          </div>
        </div>
      )}

      {(technicalMode || baseline?.configured) && (
        <div className="inline-form" style={{ marginTop: 0, marginBottom: '0.75rem', alignItems: 'center' }}>
          <label htmlFor="baseline-min" className="muted" style={{ fontSize: '0.78rem' }}>
            Optional user-supplied manual remediation baseline (minutes):
          </label>
          <input
            id="baseline-min"
            type="number"
            min={1}
            max={1440}
            step={1}
            placeholder="e.g. 25"
            value={baselineMinutesInput}
            onChange={(e) => onChangeBaselineInput(e.target.value)}
            style={{ width: 95 }}
          />
          <button type="button" className="btn btn-secondary" onClick={onApplyBaseline}>
            Apply Baseline Assumption
          </button>
          {baseline?.method && <span className="muted" style={{ fontSize: '0.75rem' }}>{baseline.method}</span>}
        </div>
      )}

      <div className="metrics-grid">
        <TimingCard label="MTTD (p50)" data={metrics.timings_seconds.mttd} />
        <TimingCard label="Triage Latency (p50)" data={metrics.timings_seconds.triage_latency} />
        <TimingCard label="Action Latency (p50)" data={metrics.timings_seconds.action_latency} />
        <TimingCard label="60s Verification Window" data={metrics.timings_seconds.verification_window} />
        <TimingCard label="End-to-End MTTR (p50)" data={metrics.timings_seconds.mttr_end_to_end} />
      </div>
      <p className="muted" style={{ marginTop: '0.75rem', fontSize: '0.78rem' }}>
        {metrics.measurement_note} (MTTD unavailable samples: {metrics.mttd_unavailable_count}).
      </p>
    </section>
  );
}
