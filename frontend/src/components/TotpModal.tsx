import { useState, type FormEvent } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { apiFetch } from '../lib/pkce';

interface Props {
  onClose: () => void;
  onVerified: () => void;
}

export function TotpModal({ onClose, onVerified }: Props) {
  const [uri, setUri] = useState<string | null>(null);
  const [mask, setMask] = useState<string>('');
  const [otp, setOtp] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-card">
        <div className="modal-header">
          <h3>Step-Up TOTP MFA Enrollment</h3>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
        <p className="muted">
          TOTP seeds are encrypted with Fernet at rest and bound per-approver. Never reused.
        </p>

        {!uri ? (
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={startEnrollment}
          >
            {busy ? 'Generating Secret...' : 'Generate TOTP QR Secret'}
          </button>
        ) : (
          <div className="totp-box">
            <div className="qr-frame">
              <QRCodeSVG value={uri} size={156} bgColor="#ffffff" fgColor="#0f172a" />
            </div>
            <p className="mono-small">Secret mask: {mask}</p>
            <form onSubmit={submitVerify} className="inline-form">
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                placeholder="6-digit OTP"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                required
              />
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {busy ? 'Verifying...' : 'Activate MFA'}
              </button>
            </form>
          </div>
        )}
        {error && <p className="error-text">{error}</p>}
      </div>
    </div>
  );
}
