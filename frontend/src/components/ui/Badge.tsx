import type { ReactNode } from 'react';

export type BadgeTone = 'ok' | 'warn' | 'danger' | 'info' | 'neutral';

export interface BadgeProps {
  tone?: BadgeTone;
  withDot?: boolean;
  className?: string;
  children: ReactNode;
}

/** Semantic status pill pairing color with explicit text (and optional status indicator dot). */
export function Badge({ tone = 'neutral', withDot = false, className = '', children }: BadgeProps) {
  const legacyAlias = tone === 'ok' ? 'badge-ok' : tone === 'warn' ? 'badge-warn' : '';
  return (
    <span className={`badge ui-badge ui-badge--${tone} ${legacyAlias} ${className}`.trim()}>
      {withDot && <span className="status-dot" aria-hidden="true" />}
      {children}
    </span>
  );
}
