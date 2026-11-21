import { useEffect, useState } from 'react';

export type MainNav = 'console' | 'knowledge' | 'evidence';
export type QueueTab = 'active' | 'resolved' | 'escalated' | 'failed' | 'all';
export type QueueSort = 'newest' | 'oldest' | 'severity';

const VALID_NAV: readonly MainNav[] = ['console', 'knowledge', 'evidence'];
const VALID_QTAB: readonly QueueTab[] = ['active', 'resolved', 'escalated', 'failed', 'all'];
const VALID_SORT: readonly QueueSort[] = ['newest', 'oldest', 'severity'];

function readInitialSearchState() {
  const params = new URLSearchParams(window.location.search);
  const nav = params.get('tab') as MainNav | null;
  const qtab = params.get('qtab') as QueueTab | null;
  const sort = params.get('sort') as QueueSort | null;
  const hideTestsRaw = params.get('hideTests');
  const viewRaw = params.get('view');

  return {
    mainNav: nav && VALID_NAV.includes(nav) ? nav : ('console' as MainNav),
    queueTab: qtab && VALID_QTAB.includes(qtab) ? qtab : ('all' as QueueTab),
    queueSearch: params.get('search') ?? '',
    queueSort: sort && VALID_SORT.includes(sort) ? sort : ('newest' as QueueSort),
    hideTestRuns: hideTestsRaw === null ? true : hideTestsRaw !== '0',
    technicalMode: viewRaw === 'technical',
    selectedIncidentId: params.get('incident') || null,
  };
}

/** Sync active workspace navigation, incident filters, and selected ID safely with URL query params. */
export function useUrlConsoleState(authLoading: boolean) {
  const [initial] = useState(readInitialSearchState);

  const [mainNav, setMainNav] = useState<MainNav>(initial.mainNav);
  const [queueTab, setQueueTab] = useState<QueueTab>(initial.queueTab);
  const [queueSearch, setQueueSearch] = useState<string>(initial.queueSearch);
  const [queueSort, setQueueSort] = useState<QueueSort>(initial.queueSort);
  const [hideTestRuns, setHideTestRuns] = useState<boolean>(initial.hideTestRuns);
  const [technicalMode, setTechnicalMode] = useState<boolean>(initial.technicalMode);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(initial.selectedIncidentId);

  useEffect(() => {
    if (authLoading) return;
    const current = new URLSearchParams(window.location.search);
    // Never clobber an active OIDC authorization callback until exchange finishes
    if (current.has('code') && current.has('state')) return;

    const next = new URLSearchParams();
    if (mainNav !== 'console') next.set('tab', mainNav);
    if (queueTab !== 'all') next.set('qtab', queueTab);
    if (queueSearch.trim()) next.set('search', queueSearch.trim());
    if (queueSort !== 'newest') next.set('sort', queueSort);
    if (!hideTestRuns) next.set('hideTests', '0');
    if (technicalMode) next.set('view', 'technical');
    if (selectedIncidentId) next.set('incident', selectedIncidentId);

    const qs = next.toString();
    const targetUrl = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
    const currentFull = `${window.location.pathname}${window.location.search}`;
    if (targetUrl !== currentFull) {
      window.history.replaceState({}, document.title, targetUrl);
    }
  }, [authLoading, mainNav, queueTab, queueSearch, queueSort, hideTestRuns, technicalMode, selectedIncidentId]);

  return {
    mainNav,
    setMainNav,
    queueTab,
    setQueueTab,
    queueSearch,
    setQueueSearch,
    queueSort,
    setQueueSort,
    hideTestRuns,
    setHideTestRuns,
    technicalMode,
    setTechnicalMode,
    selectedIncidentId,
    setSelectedIncidentId,
  };
}
