import { useState } from 'react';
import { apiFetch } from '../lib/pkce';
import type { BusinessProbeSample } from '../types';

interface Props {
  probes: BusinessProbeSample[];
  canRunProbes: boolean;
  selectedIncidentId: string | null;
  activeDemoRunId: string | null;
  onProbeCompleted: (sample: BusinessProbeSample) => void;
}

const PROBE_TARGETS = [
  { slug: 'eligibility-api', label: 'Check Patient Eligibility (POST /api/eligibility/check)' },
  { slug: 'claims-processor', label: 'Check Claims Adjudication (POST /claims/adjudicate)' },
  { slug: 'provider-directory', label: 'Check Clinic Directory (GET /providers/search)' },
  { slug: 'postgres-claims-db', label: 'Check Demo DB Health (postgres-claims-db)' },
];

export function BusinessProbeCard({
  probes,
  canRunProbes,
  selectedIncidentId,
  activeDemoRunId,
  onProbeCompleted,
}: Props) {
  const [target, setTarget] = useState('eligibility-api');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function runProbe(svc: string) {
    setBusy(true);
    setErr(null);
    try {
      const resp = await apiFetch<{ probe: BusinessProbeSample }>('/api/v1/showcase/probes/run', {
        method: 'POST',
        body: JSON.stringify({
          target_service: svc,
          incident_id: selectedIncidentId,
          demo_run_id: activeDemoRunId,
        }),
      });
      onProbeCompleted(resp.probe);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Probe execution failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-label="Business transaction recovery probes">
      <div className="section-head">
        <div>
          <h3>Synthetic Business Transaction Recovery Probe</h3>
          <span className="muted" style={{ fontSize: '0.8rem' }}>
            Tests real semantic JSON success on allowlisted demo endpoints (no arbitrary URLs).
          </span>
        </div>
        <div className="probe-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canRunProbes || busy}
            title={canRunProbes ? 'Execute synthetic patient eligibility check' : 'Operator sign-in required'}
            onClick={() => runProbe('eligibility-api')}
          >
            {busy ? 'Probing...' : 'Check Patient Eligibility'}
          </button>
        </div>
      </div>

      <div className="inline-form" style={{ marginTop: 0, marginBottom: '0.75rem' }}>
        <select
          aria-label="Allowlisted probe target"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
        >
          {PROBE_TARGETS.map((t) => (
            <option key={t.slug} value={t.slug}>
              {t.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={!canRunProbes || busy}
          onClick={() => runProbe(target)}
        >
          Run Selected Probe
        </button>
        {!canRunProbes && (
          <span className="muted" style={{ fontSize: '0.8rem', alignSelf: 'center' }}>
            Read-only history shown; sign in as Operator/Approver to trigger live probes.
          </span>
        )}
      </div>

      {err && <p className="error-text">{err}</p>}

      {probes.length === 0 ? (
        <div className="empty-state">No business transaction probes recorded yet.</div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Checked</th>
              <th>Service</th>
              <th>Result</th>
              <th>HTTP / Latency</th>
              <th>Semantic Observation</th>
            </tr>
          </thead>
          <tbody>
            {probes.slice(0, 8).map((p) => (
              <tr key={p.id}>
                <td className="mono-small">{new Date(p.checked_at).toLocaleTimeString()}</td>
                <td><code>{p.target_service}</code></td>
                <td>
                  <span className={`probe-pill probe-${p.status}`}>{p.status}</span>
                </td>
                <td className="mono-small">
                  {p.http_status ?? '—'} · {p.latency_ms !== null ? `${p.latency_ms}ms` : '—'}
                </td>
                <td>{p.summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
