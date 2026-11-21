import { useMemo, useState, type FormEvent } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { apiFetch } from '../lib/pkce';
import { Button } from './ui/Button';
import { Modal } from './ui/Modal';

interface Props {
  onClose: () => void;
  onVerified: () => void;
}

function readQrPalette(): { bg: string; fg: string } {
  if (typeof window === 'undefined') {
    return { bg: 'white', fg: 'black' };
  }
  const styles = window.getComputedStyle(document.documentElement);
  return {
    bg: styles.getPropertyValue('--qr-bg').trim() || 'white',
    fg: styles.getPropertyValue('--qr-fg').trim() || 'black',
  };
}

export function TotpModal({ onClose, onVerified }: Props) {
  const [uri, setUri] = useState<string | null>(null);
  const [mask, setMask] = useState<string>('');
  const [otp, setOtp] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const qrPalette = useMemo(() => readQrPalette(), []);

  async function startEnrollment() {
    setBusy(true);
    setError(null);
    try {
      const data = await apiFetch<{ provisioning_uri: string; secret_mask: string }>(
        '/api/v1/auth/totp/enroll',
        { method: 'POST' },
      );
      setUri(data.provisioning_uri);
      setMask(data.secret_mask);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Enrollment failed');
    } finally {
      setBusy(false);
    }
  }

  async function submitVerify(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch('/api/v1/auth/totp/verify-enrollment', {
        method: 'POST',
        body: JSON.stringify({ otp_code: otp.trim() }),
      });
      onVerified();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'OTP verification failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal titleId="totp-modal-title" title="Step-Up TOTP MFA Enrollment" onClose={onClose}>
      <p className="muted">
        TOTP seeds are encrypted with Fernet at rest and bound per-approver. Never reused.
      </p>

      {!uri ? (
        <Button variant="primary" loading={busy} onClick={startEnrollment}>
          {busy ? 'Generating Secret...' : 'Generate TOTP QR Secret'}
        </Button>
      ) : (
        <div className="totp-box">
          <div className="qr-frame">
            <QRCodeSVG value={uri} size={156} bgColor={qrPalette.bg} fgColor={qrPalette.fg} />
          </div>
          <p className="mono-small">Secret mask: {mask}</p>
          <form onSubmit={submitVerify} className="inline-form">
            <label htmlFor="totp-verify-code" className="sr-only">
              6-digit verification code from authenticator app
            </label>
            <input
              id="totp-verify-code"
              type="text"
              inputMode="numeric"
              maxLength={6}
              placeholder="6-digit OTP"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              aria-describedby={error ? 'totp-modal-error' : undefined}
              required
            />
            <Button type="submit" variant="primary" loading={busy}>
              {busy ? 'Verifying...' : 'Activate MFA'}
            </Button>
          </form>
        </div>
      )}
      {error && (
        <p id="totp-modal-error" role="alert" className="error-text">
          {error}
        </p>
      )}
    </Modal>
  );
}
