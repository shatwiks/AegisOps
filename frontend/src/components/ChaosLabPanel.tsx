import { useState } from 'react';
import { ChevronDown, ChevronRight, Flame, Pause, Play, RotateCcw } from 'lucide-react';
import { apiFetch } from '../lib/pkce';
import type { DemoRun, ReadinessResponse, ScenarioSpec } from '../types';
import { Button } from './ui/Button';
import { Modal } from './ui/Modal';

interface Props {
  scenarios: ScenarioSpec[];
  recentRuns: DemoRun[];
  readiness: ReadinessResponse | null;
  canOperate: boolean;
  onRefresh: () => void;
  onRunLaunched: (run: DemoRun, startTour: boolean) => void;
  onStartReplayFixture: (fixtureId: string) => void;
}

interface ResetPreviewResult {
  scope_namespace: string;
  cluster_context: string;
  preserves_history: boolean;
  preserves_unrelated_namespaces: boolean;
  active_demo_runs_count: number;
  active_incidents_to_close_count: number;
  resources: Array<{
    deployment: string;
    namespace: string;
    needs_k8s_patch: boolean;
    diffs?: Record<string, unknown>;
    will_reset_fault_flags?: boolean;
    error?: string;
  }>;
}

export function ChaosLabPanel({
  scenarios,
  recentRuns,
  readiness,
  canOperate,
  onRefresh,
  onRunLaunched,
  onStartReplayFixture,
}: Props) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [infoMsg, setInfoMsg] = useState<string | null>(null);
  const [showReadinessDetails, setShowReadinessDetails] = useState(false);

  const [resetPreview, setResetPreview] = useState<ResetPreviewResult | null>(null);
  const [resetBusy, setResetBusy] = useState(false);
  const [forceActive, setForceActive] = useState(false);

  const paused = readiness?.automation_control?.automation_paused ?? false;

  async function launchScenario(scenarioId: string, startTour: boolean) {
    setBusyId(scenarioId);
    setErrorMsg(null);
    setInfoMsg(null);
    try {
      const idemKey = `ui-${scenarioId}-${Date.now()}`;
      const resp = await apiFetch<{ demo_run: DemoRun; deduplicated: boolean }>(
        `/api/v1/showcase/scenarios/${scenarioId}/launch`,
        {
          method: 'POST',
          body: JSON.stringify({ idempotency_key: idemKey }),
        },
      );
      setInfoMsg(`Launched scenario '${resp.demo_run.title}' (Run ID: ${resp.demo_run.id}).`);
      onRunLaunched(resp.demo_run, startTour);
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : 'Failed to launch scenario');
    } finally {
      setBusyId(null);
    }
  }

  async function togglePauseAutomation() {
    setErrorMsg(null);
    setInfoMsg(null);
    try {
      await apiFetch('/api/v1/showcase/controls/automation', {
        method: 'POST',
        body: JSON.stringify({
          automation_paused: !paused,
          reason: !paused ? 'Paused via SRE Console Chaos Lab bar' : 'Resumed via SRE Console',
        }),
      });
      setInfoMsg(
        !paused
          ? 'Automation paused cleanly. Pending/future dispatches will hold without rolling back completed mutations.'
          : 'Automation resumed cleanly.',
      );
      onRefresh();
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : 'Failed to toggle automation pause');
    }
  }

  async function openResetPreview() {
    setErrorMsg(null);
    try {
      const prev = await apiFetch<ResetPreviewResult>('/api/v1/showcase/reset/preview', {
        method: 'POST',
      });
      setForceActive(false);
      setResetPreview(prev);
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : 'Failed to load reset preview');
    }
  }

  async function confirmResetExecute() {
    setResetBusy(true);
    setErrorMsg(null);
    try {
      const res = await apiFetch<{ status: string; closed_incident_ids?: string[] }>(
        '/api/v1/showcase/reset/execute',
        {
          method: 'POST',
          body: JSON.stringify({ force_active_runs: forceActive }),
        },
      );
      setResetPreview(null);
      const closedCount = res.closed_incident_ids?.length ?? 0;
      setInfoMsg(
        `Demo baseline restored (${res.status}).${closedCount > 0 ? ` ${closedCount} open incident(s) marked manual_reset_assisted.` : ''}`,
      );
      onRefresh();
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : 'Baseline reset failed');
    } finally {
      setResetBusy(false);
    }
  }

  const globalReady = readiness?.global_status || 'Unknown';
  const activeRun = recentRuns.find((r) => !['COMPLETED', 'ESCALATED', 'FAILED', 'CANCELLED'].includes(r.status));
  const hasActiveWork =
    resetPreview !== null &&
    (resetPreview.active_demo_runs_count > 0 || resetPreview.active_incidents_to_close_count > 0);

  return (
    <section className="card" aria-label="One-Click Chaos Lab and Environment Readiness">
      <div className="section-head">
        <div>
          <h3>Chaos Lab &amp; Self-Healing Scenarios (5 Scenarios)</h3>
          <span className="muted" style={{ fontSize: '0.8rem' }}>
            Inject controlled failures directly into the local Kind demo namespace (or preview via Recorded Replay in Visitor Mode).
          </span>
        </div>
        <div className="header-controls">
          <button
            type="button"
            aria-expanded={showReadinessDetails}
            className={`badge ${globalReady === 'Ready' ? 'badge-ok' : 'badge-warn'}`}
            onClick={() => setShowReadinessDetails((v) => !v)}
            style={{ cursor: 'pointer' }}
          >
            {showReadinessDetails ? (
              <ChevronDown size={13} aria-hidden="true" />
            ) : (
              <ChevronRight size={13} aria-hidden="true" />
            )}
            Readiness: {globalReady}
          </button>
          <Button
            variant={paused ? 'danger' : 'secondary'}
            size="sm"
            disabled={!canOperate}
            title={
              canOperate
                ? 'Pauses future remediation dispatches (does not roll back completed K8s patches)'
                : 'Operator sign-in required'
            }
            onClick={togglePauseAutomation}
          >
            {paused ? <Play size={13} aria-hidden="true" /> : <Pause size={13} aria-hidden="true" />}
            {paused ? 'Automation PAUSED (Resume)' : 'Pause Automation'}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={!canOperate}
            title={canOperate ? 'Preview and restore healthy demo replicas/images' : 'Operator sign-in required'}
            onClick={openResetPreview}
          >
            <RotateCcw size={13} aria-hidden="true" />
            Restore Demo Baseline
          </Button>
        </div>
      </div>

      {showReadinessDetails && readiness && (
        <div className="readiness-grid">
          {Object.entries(readiness.checks || {}).map(([name, info]) => (
            <div key={name} className="readiness-item">
              <div className="row-top">
                <strong>{name}</strong>
                <span className={`probe-pill probe-${info.status === 'Ready' ? 'PASS' : info.status === 'Blocked' ? 'FAIL' : 'DEGRADED'}`}>
                  {info.status}
                </span>
              </div>
              <div className="muted" style={{ fontSize: '0.74rem' }}>
                {info.detail || (info.context ? `Cluster ${info.context}` : 'Status checked')}
              </div>
            </div>
          ))}
        </div>
      )}

      {paused && (
        <div className="alert-banner alert-warn">
          <strong>Automation Paused:</strong> New remediation executions will remain in <code>READY_TO_REMEDIATE</code> hold until resumed. Completed Kubernetes patches are preserved.
        </div>
      )}

      {activeRun && (
        <div className="alert-banner alert-info">
          <strong>Active Demo Run:</strong> {activeRun.title} (<code>{activeRun.status}</code>) on <code>{activeRun.target_service}</code>
        </div>
      )}

      {errorMsg && <div className="alert-banner alert-err">{errorMsg}</div>}
      {infoMsg && <div className="alert-banner alert-ok">{infoMsg}</div>}

      <div className="scenario-grid">
        {scenarios.map((sc) => {
          const scStatus = readiness?.scenarios?.[sc.scenario_id]?.status || 'Unknown';
          const scReasons = readiness?.scenarios?.[sc.scenario_id]?.reasons || [];
          const blocked = scStatus === 'Blocked';
          return (
            <div
              key={sc.scenario_id}
              className={`scenario-card ${sc.risk_tier === 'HIGH' ? 'scenario-card--high' : 'scenario-card--low'}`}
            >
              <div className="row-top">
                <span className={`sev-pill ${sc.risk_tier === 'HIGH' ? 'sev-P1' : 'sev-P3'}`}>
                  {sc.risk_tier} RISK {sc.requires_mfa ? '· MFA' : '· AUTO'}
                </span>
                <span className="muted-pill">{sc.target_service}</span>
              </div>
              <div className="scenario-title">{sc.title}</div>
              <p className="muted" style={{ fontSize: '0.78rem', margin: '0.35rem 0' }}>
                {sc.summary}
              </p>
              <div className="muted" style={{ fontSize: '0.74rem', marginBottom: '0.55rem' }}>
                Expected: {sc.expected_outcome}
                {scReasons.length > 0 && ` · Note: ${scReasons[0]}`}
              </div>
              <div className="scenario-actions">
                {canOperate ? (
                  <>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={busyId !== null || blocked}
                      onClick={() => launchScenario(sc.scenario_id, true)}
                    >
                      <Play size={12} aria-hidden="true" />
                      {busyId === sc.scenario_id ? 'Launching...' : 'Start Guided Demo'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busyId !== null || blocked}
                      onClick={() => launchScenario(sc.scenario_id, false)}
                    >
                      <Flame size={12} aria-hidden="true" />
                      1-Click Crash Only
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() =>
                      onStartReplayFixture(
                        sc.scenario_id === 'pii_leak_and_db_failure'
                          ? 'fixture-db-escalation-boundary'
                          : 'fixture-traffic-spike-recovery',
                      )
                    }
                  >
                    <Play size={12} aria-hidden="true" />
                    Watch Recorded Tour (Visitor)
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {resetPreview && (
        <Modal
          titleId="baseline-reset-title"
          title="Restore Demo Baseline — Concrete Preview"
          wide
          onClose={() => setResetPreview(null)}
        >
          <p className="muted" style={{ fontSize: '0.84rem' }}>
            Scoped strictly to demo workloads in <code>{resetPreview.scope_namespace}</code> on{' '}
            <code>{resetPreview.cluster_context}</code>. Control-plane databases, audit history, and uploaded runbooks are preserved.
          </p>
          <table className="data-table">
            <thead>
              <tr>
                <th>Deployment</th>
                <th>Planned K8s Diff</th>
                <th>Fault Reset</th>
              </tr>
            </thead>
            <tbody>
              {resetPreview.resources.map((r) => (
                <tr key={r.deployment}>
                  <td><code>{r.deployment}</code></td>
                  <td>
                    {r.error
                      ? r.error
                      : r.needs_k8s_patch
                        ? JSON.stringify(r.diffs)
                        : 'Already matches baseline'}
                  </td>
                  <td>{r.will_reset_fault_flags ? 'Clear simulated faults' : 'None needed'}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {hasActiveWork && (
            <div className="alert-banner alert-warn" style={{ marginTop: '0.75rem' }}>
              Active demo runs/incidents detected ({resetPreview.active_demo_runs_count} runs,{' '}
              {resetPreview.active_incidents_to_close_count} open incidents). Closing them via reset marks recovery as{' '}
              <code>manual_reset_assisted</code> rather than autonomous success.
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 }}>
                <input
                  type="checkbox"
                  checked={forceActive}
                  onChange={(e) => setForceActive(e.target.checked)}
                />
                Confirm override &amp; close active incidents as <code>manual_reset_assisted</code>
              </label>
            </div>
          )}

          <div className="header-controls" style={{ justifyContent: 'flex-end', marginTop: '1rem' }}>
            <Button variant="ghost" onClick={() => setResetPreview(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={resetBusy}
              disabled={resetBusy || (hasActiveWork && !forceActive)}
              onClick={confirmResetExecute}
            >
              {resetBusy ? 'Restoring...' : 'Confirm Restore Baseline'}
            </Button>
          </div>
        </Modal>
      )}
    </section>
  );
}
