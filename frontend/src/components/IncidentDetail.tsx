import { useState, type FormEvent } from 'react';
import { apiDownloadFile, apiFetch } from '../lib/pkce';
import type { IncidentDetailResponse, UserSession } from '../types';
import { DecisionExplanationCard } from './DecisionExplanationCard';
import { LifecycleStepper } from './LifecycleStepper';

interface Props {
  detail: IncidentDetailResponse | null;
  loading: boolean;
  user: UserSession | null;
  technicalMode: boolean;
  onRefresh: () => void;
  onOpenPromptInspector: () => void;
}

export function IncidentDetail({
  detail,
  loading,
  user,
  technicalMode,
  onRefresh,
  onOpenPromptInspector,
}: Props) {
  const [otp, setOtp] = useState('');
  const [reason, setReason] = useState('Verified rollback/limit increase by SRE approver');
  const [actionBusy, setActionBusy] = useState(false);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [exportErr, setExportErr] = useState<string | null>(null);

  if (loading) {
    return <div className="card">Loading incident telemetry, citations, and audit history...</div>;
  }
  if (!detail) {
    return (
      <div className="card empty-state">
        Select an incident from the queue to inspect CMDB blast radius, Hybrid RAG citations,
        7-step progress, policy decisions, MFA approvals, and recovery verification.
      </div>
    );
  }

  const { incident, events, approvals, executions, blast_radius, lifecycle_steps, why_this_action } = detail;
  const pendingApproval = approvals.find((a) => a.status === 'PENDING');
  const canApprove =
    user !== null &&
    user.highest_role === 'approver' &&
    incident.state === 'AWAITING_APPROVAL' &&
    pendingApproval !== undefined;

  async function handleApprove(e: FormEvent) {
    e.preventDefault();
    if (!pendingApproval) return;
    setActionBusy(true);
    setActionErr(null);
    setActionMsg(null);
    try {
      await apiFetch(`/api/v1/incidents/${incident.id}/approve`, {
        method: 'POST',
        body: JSON.stringify({
          otp_code: otp.trim(),
          expected_playbook_id: pendingApproval.playbook_id,
          expected_target_slug: pendingApproval.target_asset_slug,
          expected_parameters_hash: pendingApproval.parameters_hash,
          reason,
        }),
      });
      setOtp('');
      setActionMsg('MFA approval consumed; remediation scheduled.');
      onRefresh();
    } catch (err) {
      setActionErr(err instanceof Error ? err.message : 'Approval rejected');
    } finally {
      setActionBusy(false);
    }
  }

  async function handleDeny() {
    setActionBusy(true);
    setActionErr(null);
    setActionMsg(null);
    try {
      await apiFetch(`/api/v1/incidents/${incident.id}/deny`, {
        method: 'POST',
        body: JSON.stringify({ reason: reason || 'Denied by approver' }),
      });
      setActionMsg('Approval denied; incident escalated.');
      onRefresh();
    } catch (err) {
      setActionErr(err instanceof Error ? err.message : 'Deny failed');
    } finally {
      setActionBusy(false);
    }
  }

  async function handleDownload(ext: 'md' | 'pdf') {
    setExportErr(null);
    try {
      await apiDownloadFile(
        `/api/v1/incidents/${incident.id}/postmortem.${ext}`,
        `aegisops-postmortem-${incident.id}.${ext}`,
      );
    } catch (e) {
      setExportErr(e instanceof Error ? e.message : `Unable to download .${ext}`);
    }
  }

  return (
    <div className="detail-stack">
      <section className="card">
        <div className="detail-header">
          <div>
            <span className={`sev-pill sev-${incident.severity}`}>{incident.severity}</span>
            <span className="state-pill" style={{ marginLeft: 6 }}>{incident.state}</span>
            {incident.source_provenance && (
              <span className="muted-pill" style={{ marginLeft: 6 }}>
                source: {incident.source_provenance}
              </span>
            )}
            <span className="muted-pill" style={{ marginLeft: 6 }}>
              Redacted tokens: {incident.redaction_stats?.total_redactions ?? 0}
            </span>
          </div>
          <div className="header-controls">
            {user && (
              <>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => handleDownload('md')}
                >
                  Export Postmortem .md
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => handleDownload('pdf')}
                >
                  Export Postmortem .pdf
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={onOpenPromptInspector}
                >
                  Inspect Prompt
                </button>
              </>
            )}
          </div>
        </div>
        {exportErr && <p className="error-text">{exportErr}</p>}
        <h2>{incident.title}</h2>
        <p>{incident.summary_sanitized}</p>
        <div className="mono-small" style={{ marginBottom: 8 }}>Incident ID: {incident.id}</div>
        {incident.refusal_reason && (
          <div className="alert-banner alert-warn">
            <strong>Policy Refusal / Escalation:</strong> {incident.refusal_reason}
          </div>
        )}
        <div className="meta-grid">
          <div>
            <strong>Target Asset:</strong> {incident.asset_slug || 'unknown'}
          </div>
          <div>
            <strong>Proposed Playbook:</strong> {incident.proposed_playbook_id || 'none'}
          </div>
          <div>
            <strong>Upstream Causes:</strong>{' '}
            {blast_radius.upstream_dependencies.map((u) => `${u.slug}(${u.hop})`).join(', ') || 'none'}
          </div>
          <div>
            <strong>Downstream Potential Impact:</strong>{' '}
            {blast_radius.downstream_impacts.map((d) => `${d.slug}(${d.hop})`).join(', ') || 'none'}
          </div>
        </div>
      </section>

      {lifecycle_steps && (
        <LifecycleStepper steps={lifecycle_steps} verificationState={incident.verification_state} />
      )}

      {incident.state === 'AWAITING_APPROVAL' && pendingApproval && (
        <section className="card mfa-card">
          <h3>High-Risk Step-Up MFA Approval Required</h3>
          <div className="meta-grid">
            <div>
              <strong>Playbook:</strong> {pendingApproval.playbook_id} v{pendingApproval.playbook_version}
            </div>
            <div>
              <strong>Target UID:</strong> <span className="mono-small">{pendingApproval.target_k8s_uid}</span>
            </div>
            <div>
              <strong>ResourceVersion:</strong> {pendingApproval.target_resource_version}
            </div>
            <div>
              <strong>Parameters:</strong> <code>{JSON.stringify(pendingApproval.parameters)}</code>
            </div>
          </div>

          {canApprove ? (
            <form onSubmit={handleApprove} className="mfa-form">
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                placeholder="Enter 6-digit TOTP"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                required
              />
              <input
                type="text"
                placeholder="Approval rationale"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                required
              />
              <button type="submit" className="btn btn-primary" disabled={actionBusy}>
                {actionBusy ? 'Submitting...' : 'Approve with TOTP'}
              </button>
              <button type="button" className="btn btn-danger" disabled={actionBusy} onClick={handleDeny}>
                Deny &amp; Escalate
              </button>
            </form>
          ) : (
            <p className="muted">
              Approval requires the <code>approver</code> role (current role: <code>{user?.highest_role || 'visitor'}</code>).
            </p>
          )}
          {actionErr && <p className="error-text">{actionErr}</p>}
          {actionMsg && <p className="ok-text">{actionMsg}</p>}
        </section>
      )}

      {why_this_action && (
        <DecisionExplanationCard data={why_this_action} technicalMode={technicalMode} />
      )}

      {incident.diagnosis && (technicalMode || (incident.diagnosis.citations?.length ?? 0) > 0) && (
        <section className="card">
          <h3>Hybrid RAG Diagnosis &amp; Retrieved Citations</h3>
          {incident.diagnosis.proposal && (
            <div className="diag-box">
              <p>
                <strong>Root Cause Hypothesis:</strong> {incident.diagnosis.proposal.root_cause_summary}
              </p>
              {technicalMode && (
                <p>
                  <strong>Reasoning:</strong> {incident.diagnosis.proposal.reasoning}
                </p>
              )}
              <p>
                <strong>Uncertainty:</strong> {incident.diagnosis.proposal.uncertainty_level} ·{' '}
                <strong>Cited Runbooks:</strong>{' '}
                {incident.diagnosis.proposal.cited_runbook_ids.join(', ') || 'none'}
              </p>
            </div>
          )}
          {incident.diagnosis.citations && incident.diagnosis.citations.length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Runbook / Postmortem</th>
                  <th>Type</th>
                  <th>Cosine Sim</th>
                  <th>Lexical Score</th>
                  <th>RRF Score</th>
                </tr>
              </thead>
              <tbody>
                {incident.diagnosis.citations.map((c) => (
                  <tr key={c.slug}>
                    <td>{c.slug}</td>
                    <td>{c.doc_type}</td>
                    <td>{c.vector_similarity.toFixed(4)}</td>
                    <td>{c.lexical_score.toFixed(4)}</td>
                    <td>{c.rrf_score.toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {executions.length > 0 && (
        <section className="card">
          <h3>Kubernetes Execution Ledger &amp; Before/After Diff</h3>
          {executions.map((ex) => (
            <div key={ex.id} className="exec-item">
              <div className="exec-head">
                <strong>{ex.playbook_id}</strong>
                <span className="state-pill">{ex.status}</span>
              </div>
              <div className="diff-grid">
                <div>
                  <div className="muted">Before State</div>
                  <pre className="json-box">{JSON.stringify(ex.before_state, null, 2)}</pre>
                </div>
                <div>
                  <div className="muted">After State</div>
                  <pre className="json-box">{JSON.stringify(ex.after_state ?? {}, null, 2)}</pre>
                </div>
              </div>
              {ex.error && <p className="error-text">{ex.error}</p>}
            </div>
          ))}
        </section>
      )}

      <section className="card">
        <h3>Incident Timeline ({events.length})</h3>
        <ul className="timeline">
          {events.map((ev) => (
            <li key={ev.id}>
              <span className="mono-small">{new Date(ev.created_at).toLocaleTimeString()}</span>{' '}
              <strong>{ev.event_type}</strong>{' '}
              {ev.to_state && (
                <span className="muted">
                  ({ev.from_state || 'INIT'} -&gt; {ev.to_state})
                </span>
              )}{' '}
              <span className="mono-small">by {ev.actor}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
