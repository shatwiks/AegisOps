import { HeartPulse, Lock, ShieldCheck, Timer, Zap } from 'lucide-react';
import type { MetricsSummaryResponse, TimingSummary } from '../types';
import { Button } from './ui/Button';
import { Skeleton } from './ui/Skeleton';

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
    <div className="hairline-cell">
      <div className="metric-head">
        <span className="metric-label">{label}</span>
        <Timer size={13} aria-hidden="true" />
      </div>
      <div className="metric-value">
        {data.p50 !== null ? `${data.p50}s` : 'N/A'}
      </div>
      <div className="metric-sub">
        n={data.sample_count} · mean={data.mean ?? '—'}s · p95={data.p95 ?? '—'}s
      </div>
    </div>
  );
}

/** Hairline-divided KPI & timing strip with JetBrains Mono tabular numerals. */
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
    return (
      <section className="card" aria-label="Measured Value & Operational Metrics">
        <div className="section-head">
          <Skeleton height={24} width={280} />
          <Skeleton height={30} width={180} />
        </div>
        <div className="hairline-grid-5">
          <Skeleton height={86} />
          <Skeleton height={86} />
          <Skeleton height={86} />
          <Skeleton height={86} />
          <Skeleton height={86} />
        </div>
      </section>
    );
  }

  const bv = metrics.business_value;
  const baseline = bv?.manual_baseline_comparison;

  return (
    <section className="card" aria-label="Measured Value & Operational Metrics">
      <div className="section-head">
        <div>
          <h3>Measured Value &amp; Operational Timings</h3>
          <span className="mono-small">
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
        <div className="hairline-grid-5" style={{ marginBottom: '0.75rem' }}>
          <div className="hairline-cell hairline-cell--highlight">
            <div className="metric-head">
              <span className="metric-label">Identifiers Redacted (Boundary)</span>
              <ShieldCheck size={14} aria-hidden="true" />
            </div>
            <div className="metric-value">{bv.sensitive_identifiers_redacted}</div>
            <div className="metric-sub">Stripped tokens (not distinct patients)</div>
          </div>

          <div className="hairline-cell">
            <div className="metric-head">
              <span className="metric-label">Autonomously Contained</span>
              <Zap size={14} aria-hidden="true" />
            </div>
            <div className="metric-value">{bv.incidents_contained_by_automation}</div>
            <div className="metric-sub">Resolved via verified rollout</div>
          </div>

          <div className="hairline-cell">
            <div className="metric-head">
              <span className="metric-label">MFA-Gated High-Risk Actions</span>
              <Lock size={14} aria-hidden="true" />
            </div>
            <div className="metric-value">{bv.high_risk_actions_gated_by_mfa}</div>
            <div className="metric-sub">Action-bound TOTP enforcement</div>
          </div>

          <div className="hairline-cell">
            <div className="metric-head">
              <span className="metric-label">Business Probe Recoveries</span>
              <HeartPulse size={14} aria-hidden="true" />
            </div>
            <div className="metric-value">{bv.business_probe_recoveries_verified} PASS</div>
            <div className="metric-sub">
              {bv.business_probe_failures_observed} FAIL/DEGRADED observed
            </div>
          </div>

          <div className="hairline-cell">
            <div className="metric-head">
              <span className="metric-label">Manual Baseline Comparison</span>
              <Timer size={14} aria-hidden="true" />
            </div>
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
          <Button variant="secondary" size="sm" onClick={onApplyBaseline}>
            Apply Baseline Assumption
          </Button>
          {baseline?.method && <span className="muted" style={{ fontSize: '0.75rem' }}>{baseline.method}</span>}
        </div>
      )}

      <div className="hairline-grid-5">
        <TimingCard label="MTTD (p50)" data={metrics.timings_seconds.mttd} />
        <TimingCard label="Triage Latency (p50)" data={metrics.timings_seconds.triage_latency} />
        <TimingCard label="Action Latency (p50)" data={metrics.timings_seconds.action_latency} />
        <TimingCard label="60s Verification Window" data={metrics.timings_seconds.verification_window} />
        <TimingCard label="End-to-End MTTR (p50)" data={metrics.timings_seconds.mttr_end_to_end} />
      </div>
      <p className="mono-small" style={{ marginTop: '0.75rem', marginBottom: 0 }}>
        {metrics.measurement_note} (MTTD unavailable samples: {metrics.mttd_unavailable_count}).
      </p>
    </section>
  );
}
