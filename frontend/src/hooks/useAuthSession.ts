import { useCallback, useEffect, useState } from 'react';
import { apiFetch, generateRandomString, sha256Base64Url } from '../lib/pkce';
import type { AuthConfig, UserSession } from '../types';

// Preserves single-use PKCE exchange semantics across React 18 StrictMode double-mounts
let inFlightPkceCode: string | null = null;
let inFlightPkcePromise: Promise<void> | null = null;

/** Manages Keycloak S256 OIDC PKCE session lifecycle and role state. */
export function useAuthSession() {
  const [user, setUser] = useState<UserSession | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);

  useEffect(() => {
    let active = true;
    async function initAuth() {
      const params = new URLSearchParams(window.location.search);
      const code = params.get('code');
      const state = params.get('state');

      if (code && state) {
        try {
          if (inFlightPkceCode !== code || !inFlightPkcePromise) {
            inFlightPkceCode = code;
            inFlightPkcePromise = (async () => {
              const expectedState = sessionStorage.getItem('aegisops_pkce_state');
              const verifier = sessionStorage.getItem('aegisops_pkce_verifier');
              const nonce = sessionStorage.getItem('aegisops_pkce_nonce');
              sessionStorage.removeItem('aegisops_pkce_state');
              sessionStorage.removeItem('aegisops_pkce_verifier');
              sessionStorage.removeItem('aegisops_pkce_nonce');

              if (!verifier || expectedState !== state) {
                throw new Error('OIDC PKCE state mismatch');
              }
              await apiFetch('/api/v1/auth/oidc/exchange', {
                method: 'POST',
                body: JSON.stringify({
                  code,
                  code_verifier: verifier,
                  redirect_uri: `${window.location.origin}/`,
                  nonce,
                }),
              });
              window.history.replaceState({}, document.title, '/');
            })();
          }
          await inFlightPkcePromise;
        } catch (err) {
          if (active) setAuthError(err instanceof Error ? err.message : 'OIDC login failed');
        }
      }

      try {
        const me = await apiFetch<UserSession>('/api/v1/auth/me');
        if (active) {
          setUser(me);
          setSessionExpired(false);
        }
      } catch {
        if (active) setUser(null);
      } finally {
        if (active) setAuthLoading(false);
      }
    }
    initAuth();
    return () => {
      active = false;
    };
  }, []);

  const handleLogin = useCallback(async () => {
    setAuthError(null);
    try {
      const cfg = await apiFetch<AuthConfig>('/api/v1/auth/config');
      const verifier = generateRandomString(48);
      const challenge = await sha256Base64Url(verifier);
      const state = generateRandomString(24);
      const nonce = generateRandomString(24);

      sessionStorage.setItem('aegisops_pkce_verifier', verifier);
      sessionStorage.setItem('aegisops_pkce_state', state);
      sessionStorage.setItem('aegisops_pkce_nonce', nonce);

      const url = new URL(cfg.authorization_endpoint);
      url.searchParams.set('client_id', cfg.client_id);
      url.searchParams.set('response_type', 'code');
      url.searchParams.set('scope', 'openid profile email');
      url.searchParams.set('redirect_uri', `${window.location.origin}/`);
      url.searchParams.set('state', state);
      url.searchParams.set('nonce', nonce);
      url.searchParams.set('code_challenge', challenge);
      url.searchParams.set('code_challenge_method', 'S256');
      window.location.assign(url.toString());
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : 'Unable to start OIDC login');
    }
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await apiFetch('/api/v1/auth/logout', { method: 'POST' });
    } catch {
      // Session already cleared or expired
    }
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    const me = await apiFetch<UserSession>('/api/v1/auth/me');
    setUser(me);
    setSessionExpired(false);
  }, []);

  const markSessionExpired = useCallback(() => {
    setSessionExpired(true);
    setUser(null);
  }, []);

  return {
    user,
    authLoading,
    authError,
    sessionExpired,
    handleLogin,
    handleLogout,
    refreshUser,
    markSessionExpired,
  };
}
