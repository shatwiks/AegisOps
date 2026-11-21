import { Button } from '../../components/ui/Button';
import type { ShowcaseOverview } from '../../types';

interface Props {
  overview: ShowcaseOverview;
  onStartGuidedReplay: () => void;
}

/** Executive onboarding banner displayed in Visitor Mode highlighting the 5 control-plane pillars. */
export function VisitorOverviewBanner({ overview, onStartGuidedReplay }: Props) {
  return (
    <section className="card" aria-label="Executive Overview" style={{ marginBottom: 'var(--space-4)' }}>
      <div className="section-head">
        <div>
          <strong>What AegisOps Does (Executive Overview)</strong>
          <p className="muted" style={{ fontSize: '0.82rem', margin: '0.2rem 0 0' }}>
            {overview.disclaimer}
          </p>
        </div>
        <Button variant="primary" onClick={onStartGuidedReplay}>
          Start Guided Demo (Recorded Replay)
        </Button>
      </div>
      <div className="pillars-grid">
        {overview.five_pillars.map((pillar) => (
          <div key={pillar.title} className="pillar-tile">
            <strong>{pillar.title}</strong>
            <div className="muted" style={{ fontSize: '0.76rem', marginTop: 2 }}>
              {pillar.detail}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
