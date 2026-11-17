import type { DemoRun } from '../types';

interface Props {
  active: boolean;
  paused: boolean;
  activeRun: DemoRun | null;
  replayNarration?: { step?: number; headline?: string; detail?: string; focus_panel?: string } | null;
  isReplay: boolean;
  onTogglePause: () => void;
  onSkipStep: () => void;
  onExit: () => void;
  onFocusPanel: (panel: string) => void;
}

const TOUR_STEPS = [
  '1. Requests fail',
  '2. PII stripped',
  '3. Impact mapped',
  '4. Runbook & AI',
  '5. Policy / MFA',
  '6. 60s Stability',
  '7. Outcome',
];

export function GuidedTourBar({
  active,
  paused,
  activeRun,
  replayNarration,
  isReplay,
  onTogglePause,
  onSkipStep,
  onExit,
  onFocusPanel,
}: Props) {
  if (!active) return null;

  const narration = isReplay ? replayNarration : activeRun?.narration_state;
  const stepNum = Math.max(1, Math.min(7, Number(narration?.step ?? 1)));
  const headline = narration?.headline || 'Observing backend events...';
  const detail =
    narration?.detail ||
    'Waiting for Alertmanager, Outbox Worker, and Kubernetes telemetry transitions.';
  const focus = narration?.focus_panel || 'detail';

  return (
    <aside className="tour-bar" aria-live="polite" aria-label="Guided demonstration tour">
      <div className="tour-head">
        <div>
          <span className="badge badge-ok" style={{ marginRight: 8 }}>
            {isReplay ? 'GUIDED TOUR (RECORDED REPLAY)' : 'GUIDED DEMO TOUR (LIVE CLUSTER)'}
          </span>
          <strong>{activeRun?.title || 'Interactive Walkthrough'}</strong>
          {paused && <span className="badge badge-warn" style={{ marginLeft: 8 }}>Narration Paused</span>}
        </div>
        <div className="header-controls">
          <button type="button" className="btn btn-secondary" onClick={() => onFocusPanel(focus)}>
            Focus Panel ({focus})
          </button>
          <button type="button" className="btn btn-secondary" onClick={onTogglePause}>
            {paused ? 'Resume Narration' : 'Pause Narration'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={onSkipStep}>
            Skip Explanation
          </button>
          <button type="button" className="btn btn-ghost" onClick={onExit}>
            Exit Tour
          </button>
        </div>
      </div>

      <div className="tour-body">
        <div className="tour-headline">
          Step {stepNum}/7: {headline}
        </div>
        <div className="muted" style={{ fontSize: '0.86rem' }}>{detail}</div>
      </div>

      <div className="tour-milestones">
        {TOUR_STEPS.map((label, idx) => (
          <span
            key={label}
            className={`tour-chip ${idx + 1 === stepNum ? 'current' : idx + 1 < stepNum ? 'done' : ''}`}
          >
            {label}
          </span>
        ))}
      </div>
      <div className="muted" style={{ fontSize: '0.74rem', marginTop: 4 }}>
        Note: Pausing or exiting tour narration only affects UI focus and never cancels backend workers or Kubernetes checks.
      </div>
    </aside>
  );
}
