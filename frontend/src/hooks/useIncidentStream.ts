import { useCallback, useEffect, useRef, useState } from 'react';

export type SseState = 'connecting' | 'live' | 'reconnecting';

/** Authenticated Server-Sent Events subscription with automatic reconnect and stale heartbeat tracking. */
export function useIncidentStream(enabled: boolean, onSnapshot: () => void) {
  const [sseState, setSseState] = useState<SseState>('connecting');
  const [isStale, setIsStale] = useState(false);
  const lastUpdateAtRef = useRef<number>(Date.now());
  const onSnapshotRef = useRef(onSnapshot);
  onSnapshotRef.current = onSnapshot;

  const markFresh = useCallback(() => {
    lastUpdateAtRef.current = Date.now();
    setIsStale(false);
  }, []);

  useEffect(() => {
    if (!enabled) {
      setSseState('connecting');
      setIsStale(false);
      return;
    }

    let es: EventSource | null = null;
    let reconnectTimer: number | undefined;
    let cancelled = false;

    const connectSse = () => {
      if (cancelled) return;
      setSseState('connecting');
      es = new EventSource('/api/v1/stream/incidents', { withCredentials: true });
      es.onopen = () => {
        setSseState('live');
        setIsStale(false);
        lastUpdateAtRef.current = Date.now();
      };
      es.addEventListener('incidents_snapshot', () => {
        lastUpdateAtRef.current = Date.now();
        setIsStale(false);
        onSnapshotRef.current();
      });
      es.onerror = () => {
        setSseState('reconnecting');
        es?.close();
        if (!cancelled) {
          reconnectTimer = window.setTimeout(connectSse, 3000);
        }
      };
    };

    connectSse();
    const staleTimer = window.setInterval(() => {
      if (Date.now() - lastUpdateAtRef.current > 20000) {
        setIsStale(true);
      }
    }, 5000);

    return () => {
      cancelled = true;
      es?.close();
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      window.clearInterval(staleTimer);
    };
  }, [enabled]);

  return { sseState, isStale, markFresh };
}
