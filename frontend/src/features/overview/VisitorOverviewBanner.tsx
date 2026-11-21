import { Play } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import type { ShowcaseOverview } from '../../types';

interface Props {
  overview: ShowcaseOverview;
  onStartGuidedReplay: () => void;
}

/** Editorial split hero pairing plain-English value summary with a live-pulsing control-plane diagram. */
export function VisitorOverviewBanner({ overview, onStartGuidedReplay }: Props) {
  return (
    <section className="hero-surface" aria-label="Executive Overview" data-enter="true">
      <div className="hero-split">
        <div>
          <span className="eyebrow">Zero-Trust Kubernetes Self-Healing</span>
          <h2 className="hero-headline">What AegisOps Does (Executive Overview)</h2>
          <p className="hero-copy">{overview.disclaimer}</p>
          <Button variant="primary" onClick={onStartGuidedReplay}>
            <Play size={14} aria-hidden="true" />
            Start Guided Demo (Recorded Replay)
          </Button>
        </div>

        <div className="hero-diagram-box" aria-hidden="true">
          <svg viewBox="0 0 560 156" className="hero-svg" role="presentation">
            <line
              x1="70"
              y1="62"
              x2="490"
              y2="62"
              stroke="var(--accent-highlight)"
              strokeOpacity="0.65"
              strokeWidth="2"
              className="hero-wire"
            />
            <circle r="4" fill="var(--accent-highlight)">
              <animateMotion dur="3.4s" repeatCount="indefinite" path="M 70 62 L 490 62" />
            </circle>

            {/* Node 1: Scrub */}
            <g transform="translate(12, 30)">
              <rect
                width="112"
                height="64"
                rx="8"
                fill="var(--bg-elevated)"
                stroke="var(--border-strong)"
              />
              <text x="12" y="25" fill="var(--accent-highlight)" fontSize="10" fontWeight="700">
                01. EDGE SCRUB
              </text>
              <text x="12" y="45" fill="var(--text-secondary)" fontSize="11" fontWeight="600">
                PII Redacted
              </text>
            </g>

            {/* Node 2: CMDB + RAG */}
            <g transform="translate(152, 30)">
              <rect
                width="116"
                height="64"
                rx="8"
                fill="var(--bg-elevated)"
                stroke="var(--border-strong)"
              />
              <text x="12" y="25" fill="var(--status-info-text)" fontSize="10" fontWeight="700">
                02. CMDB + RAG
              </text>
              <text x="12" y="45" fill="var(--text-secondary)" fontSize="11" fontWeight="600">
                Impact + Ollama
              </text>
            </g>

            {/* Node 3: Policy / TOTP */}
            <g transform="translate(296, 30)">
              <rect
                width="112"
                height="64"
                rx="8"
                fill="var(--bg-elevated)"
                stroke="var(--status-warning-border)"
              />
              <text x="12" y="25" fill="var(--status-warning-text)" fontSize="10" fontWeight="700">
                03. POLICY GATE
              </text>
              <text x="12" y="45" fill="var(--text-secondary)" fontSize="11" fontWeight="600">
                Auto / MFA / Safe
              </text>
            </g>

            {/* Node 4: 60s Watchdog */}
            <g transform="translate(436, 30)">
              <rect
                width="112"
                height="64"
                rx="8"
                fill="var(--bg-elevated)"
                stroke="var(--status-success-border)"
              />
              <text x="12" y="25" fill="var(--status-success-text)" fontSize="10" fontWeight="700">
                04. WATCHDOG
              </text>
              <text x="12" y="45" fill="var(--text-secondary)" fontSize="11" fontWeight="600">
                60s Verified PDF
              </text>
            </g>

            <text x="12" y="132" fill="var(--text-muted)" fontSize="10.5">
              100% local AI diagnosis paired with server-enforced Kubernetes guardrails.
            </text>
          </svg>
        </div>
      </div>

      <div className="pillars-strip">
        {overview.five_pillars.map((pillar) => (
          <div key={pillar.title} className="pillar-cell">
            <strong>{pillar.title}</strong>
            <span className="muted" style={{ fontSize: '0.75rem' }}>
              {pillar.detail}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
