import type { LifecycleStep } from '../types';

interface Props {
  steps: LifecycleStep[];
  verificationState?: {
    status?: string;
    window_seconds?: number;
    elapsed_healthy_seconds?: number;
    reset_count?: number;
    last_reset_reason?: string;
  };
}

export function LifecycleStepper({ steps, verificationState }: Props) {
  if (!steps || steps.length === 0) return null;

  const winSec = Number(verificationState?.window_seconds ?? 60);
  const elapsedSec = Number(verificationState?.elapsed_healthy_seconds ?? 0);
  const pct = winSec > 0 ? Math.min(100, Math.round((elapsedSec / winSec) * 100)) : 0;
  const isObserving = verificationState?.status === 'observing';

  return (
    <section className="card" aria-label="Incident 7-step lifecycle progress">
      <div className="section-head">
        <h3>7-Step Operational Lifecycle</h3>
        <span className="muted-pill">Event-driven from backend transitions</span>
      </div>

      <ol className="stepper-grid">
        {steps.map((s) => (
          <li key={s.key} className={`step-card step-${s.status}`}>
            <div className="step-top">
              <span className="step-num">Step {s.step}</span>
              <span className={`step-badge badge-${s.status}`}>{s.status.replace('_', ' ')}</span>
            </div>
            <div className="step-label">{s.label}</div>
            <div className="step-summary">{s.summary}</div>
            {s.timestamp && (
              <div className="mono-small" style={{ marginTop: 4 }}>
                {new Date(s.timestamp).toLocaleTimeString()}
              </div>
            )}
          </li>
        ))}
      </ol>

      {isObserving && (
        <div className="watchdog-progress-box" role="status" aria-live="polite">
          <div className="section-head" style={{ marginBottom: 6 }}>
            <strong>
              Checking service stability: {Math.round(elapsedSec)} of {Math.round(winSec)} seconds observed
            </strong>
            <span className="muted-pill">
              Resets: {verificationState?.reset_count ?? 0}
            </span>
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
          {verificationState?.last_reset_reason && (
            <div className="muted" style={{ fontSize: '0.78rem', marginTop: 4 }}>
              Window reset reason: {verificationState.last_reset_reason}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
