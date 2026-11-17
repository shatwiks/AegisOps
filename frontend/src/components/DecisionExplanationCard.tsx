import type { WhyThisAction } from '../types';

interface Props {
  data?: WhyThisAction;
  technicalMode: boolean;
}

export function DecisionExplanationCard({ data, technicalMode }: Props) {
  if (!data) return null;
  const { ai_recommendation_hypothesis: ai, policy_authorization: policy, questions: q } = data;

  return (
    <section className="card" aria-label="Why this action decision rationale">
      <div className="section-head">
        <h3>Why This Action? — Evidence & Policy Boundaries</h3>
        <span className="muted-pill">AI Hypothesis != Policy Authority</span>
      </div>

      <div className="separation-grid">
        <div className="sep-pane">
          <div className="sep-tag tag-ai">1. AI Recommendation (Hypothesis Only)</div>
          <p>
            <strong>Root cause hypothesis:</strong> {ai.root_cause_summary || 'Unavailable'}
          </p>
          <p className="muted" style={{ fontSize: '0.8rem' }}>
            Proposed playbook: <code>{ai.proposed_playbook_id || 'none'}</code> · Uncertainty:{' '}
            <strong>{ai.uncertainty_level || 'UNKNOWN'}</strong>
          </p>
          <p className="muted" style={{ fontSize: '0.76rem' }}>{ai.note}</p>
        </div>

        <div className="sep-pane">
          <div className="sep-tag tag-policy">2. Server Policy Authorization</div>
          <p>
            <strong>Approved Playbook:</strong> <code>{policy.proposed_playbook_id || 'REFUSED / NONE'}</code>
          </p>
          {policy.refusal_reason && (
            <p className="error-text" style={{ fontSize: '0.82rem' }}>{policy.refusal_reason}</p>
          )}
          <p className="muted" style={{ fontSize: '0.78rem' }}>
            MFA Requirement: {q.why_mfa_required.required ? 'REQUIRED' : 'Not required'} — {q.why_mfa_required.rule}
          </p>
        </div>

        <div className="sep-pane">
          <div className="sep-tag tag-exec">3. Execution & Observed Outcome</div>
          <p>
            <strong>Execution Status:</strong> {q.what_happened_afterward.execution_status || 'None executed'}
          </p>
          <p className="muted" style={{ fontSize: '0.8rem' }}>
            Final Incident State: <strong>{q.what_happened_afterward.final_state}</strong> · Recovered business probes:{' '}
            {q.what_happened_afterward.recovered_probes_count}
          </p>
          {q.what_can_prevent_execution.length > 0 && (
            <p className="muted" style={{ fontSize: '0.78rem' }}>
              Active blockers: {q.what_can_prevent_execution.join('; ')}
            </p>
          )}
        </div>
      </div>

      <details style={{ marginTop: '0.75rem' }} open={technicalMode}>
        <summary className="details-toggle">Full 7-Question Structured Audit Breakdown</summary>
        <table className="data-table">
          <thead>
            <tr>
              <th>Decision Question</th>
              <th>Persisted Evidence</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>What seems to have failed?</td>
              <td>
                <strong>{q.what_failed.alertname}</strong> on <code>{q.what_failed.target_asset || 'unknown'}</code> ({q.what_failed.severity}) — {q.what_failed.diagnosis_hypothesis}
              </td>
            </tr>
            <tr>
              <td>Why does the system think so?</td>
              <td>
                {q.why_system_thinks_so.citations.length} cited runbook(s);{' '}
                {q.why_system_thinks_so.failing_probes_count} failing business probe(s); quotes:{' '}
                <code>{(q.why_system_thinks_so.evidence_quotes || []).join(' | ') || 'none'}</code>
              </td>
            </tr>
            <tr>
              <td>What action is recommended?</td>
              <td>
                <code>{q.recommended_action.playbook_id || 'none (escalate)'}</code>{' '}
                {Object.keys(q.recommended_action.bounded_parameters || {}).length > 0 && (
                  <code>{JSON.stringify(q.recommended_action.bounded_parameters)}</code>
                )}
              </td>
            </tr>
            <tr>
              <td>Why allowed or blocked?</td>
              <td>
                {q.why_allowed_or_blocked.refusal_reason || 'All server preconditions passed'}{' '}
                {technicalMode && <code>{JSON.stringify(q.why_allowed_or_blocked.decision_checks)}</code>}
              </td>
            </tr>
            <tr>
              <td>Why is MFA required?</td>
              <td>{q.why_mfa_required.rule} (Approval: {q.why_mfa_required.approval_status || 'N/A'})</td>
            </tr>
            <tr>
              <td>What can prevent execution?</td>
              <td>{q.what_can_prevent_execution.join(' · ') || 'No blockers detected'}</td>
            </tr>
            <tr>
              <td>What happened afterward?</td>
              <td>
                Outcome: <strong>{q.what_happened_afterward.final_state}</strong> (Exec:{' '}
                {q.what_happened_afterward.execution_status || 'none'})
              </td>
            </tr>
          </tbody>
        </table>
      </details>
    </section>
  );
}
