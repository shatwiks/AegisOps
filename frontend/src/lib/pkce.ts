function base64UrlEncode(bytes: Uint8Array): string {
  let str = '';
  for (let i = 0; i < bytes.length; i++) {
    str += String.fromCharCode(bytes[i]);
  }
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function generateRandomString(byteLen = 32): string {
  const arr = new Uint8Array(byteLen);
  crypto.getRandomValues(arr);
  return base64UrlEncode(arr);
}

export async function sha256Base64Url(input: string): Promise<string> {
  const encoded = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest('SHA-256', encoded);
  return base64UrlEncode(new Uint8Array(digest));
}

export function readCookie(name: string): string {
  const prefix = `${name}=`;
  const parts = document.cookie.split(';');
  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }
  return '';
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has('Content-Type') && init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  const method = (init.method || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    const csrf = readCookie('aegisops_csrf');
    if (csrf) {
      headers.set('X-CSRF-Token', csrf);
    }
  }

  const resp = await fetch(path, {
    ...init,
    credentials: 'include',
    headers,
  });

  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const errBody = (await resp.json()) as { detail?: string };
      if (errBody.detail) detail = errBody.detail;
    } catch {
      // ignore non-JSON body
    }
    const err = new Error(detail) as Error & { status?: number };
    err.status = resp.status;
    throw err;
  }
  return (await resp.json()) as T;
}

export async function apiDownloadFile(path: string, fallbackFilename: string): Promise<void> {
  const resp = await fetch(path, { method: 'GET', credentials: 'include' });
  if (!resp.ok) {
    throw new Error(`Export failed (HTTP ${resp.status})`);
  }
  const blob = await resp.blob();
  const disp = resp.headers.get('content-disposition') || '';
  const match = disp.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : fallbackFilename;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
