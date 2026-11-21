import { KeyRound, LogIn, LogOut, Shield } from 'lucide-react';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import type { SseState } from '../../hooks/useIncidentStream';
import type { UserSession } from '../../types';

interface Props {
  user: UserSession | null;
  sseState: SseState;
  isStale: boolean;
  onLogin: () => void;
  onLogout: () => void;
  onOpenTotp: () => void;
}

/** Sticky command header displaying system identity, live stream/visitor badge, and auth actions. */
export function CommandHeader({ user, sseState, isStale, onLogin, onLogout, onOpenTotp }: Props) {
  return (
    <header className="cmd-header">
      <div className="cmd-header__inner">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            <Shield size={18} strokeWidth={2.2} />
          </div>
          <div>
            <span className="eyebrow">Independent Synthetic Healthcare AIOps Demonstration</span>
            <h1 className="brand-title">
              {user ? 'AegisOps SRE Console' : 'AegisOps SRE Control Plane'}
            </h1>
          </div>
        </div>

        <div className="header-controls">
          {user ? (
            <>
              <Badge tone={sseState === 'live' ? 'ok' : 'warn'} withDot>
                Stream: {sseState}
                {isStale ? ' (stale)' : ''}
              </Badge>
              <span className="role-pill">
                {user.email} ({user.highest_role})
              </span>
              {user.highest_role === 'approver' && (
                <Button variant="secondary" size="sm" onClick={onOpenTotp}>
                  <KeyRound size={14} aria-hidden="true" />
                  {user.totp_verified ? 'Re-enroll TOTP MFA' : 'Enroll TOTP MFA'}
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={onLogout}>
                <LogOut size={14} aria-hidden="true" />
                Sign Out
              </Button>
            </>
          ) : (
            <>
              <Badge tone="warn" withDot>
                Visitor Mode (Read-Only)
              </Badge>
              <Button variant="primary" size="sm" onClick={onLogin}>
                <LogIn size={14} aria-hidden="true" />
                Sign In with Keycloak OIDC (PKCE)
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
