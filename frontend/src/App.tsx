import { useCallback, useEffect, useRef, useState } from 'react';
import { BusinessProbeCard } from './components/BusinessProbeCard';
import { ChaosLabPanel } from './components/ChaosLabPanel';
import { EngineeringEvidenceView } from './components/EngineeringEvidenceView';
import { GuidedTourBar } from './components/GuidedTourBar';
import { IncidentDetail } from './components/IncidentDetail';
import { MetricsDashboard } from './components/MetricsDashboard';
import { PrivacyPromptDrawer } from './components/PrivacyPromptDrawer';
import { ReplayController } from './components/ReplayController';
import { RunbookKnowledgePanel } from './components/RunbookKnowledgePanel';
import { TopologyGraph } from './components/TopologyGraph';
import { TotpModal } from './components/TotpModal';
import { apiFetch, generateRandomString, sha256Base64Url } from './lib/pkce';
import type {
  AuthConfig,
  BusinessProbeSample,
  DemoRun,
  EvidenceResponse,
  IncidentDetailResponse,
  IncidentListResponse,
  IncidentSummary,
  MetricsSummaryResponse,
  ReadinessResponse,
  ReplayListItem,
  ReplayTimeline,
  ScenarioSpec,
  ShowcaseOverview,
  TopologyResponse,
  UserSession,
} from './types';

let inFlightPkceCode: string | null = null;
let inFlightPkcePromise: Promise<void> | null = null;

type QueueTab = 'active' | 'resolved' | 'escalated' | 'failed' | 'all';
type MainNav = 'console' | 'knowledge' | 'evidence';

export function App() {
  const [user, setUser] = useState<UserSession | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);

  const [mainNav, setMainNav] = useState<MainNav>('console');
  const [technicalMode, setTechnicalMode] = useState(false);

  const [overview, setOverview] = useState<ShowcaseOverview | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioSpec[]>([]);
  const [recentRuns, setRecentRuns] = useState<DemoRun[]>([]);
  const [probes, setProbes] = useState<BusinessProbeSample[]>([]);
  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);

  const [topology, setTopology] = useState<TopologyResponse | null>(null);
  const [selectedAssetSlug, setSelectedAssetSlug] = useState<string | null>(null);

  const [queueTab, setQueueTab] = useState<QueueTab>('all');
  const [hideTestRuns, setHideTestRuns] = useState(true);
  const [queueSearch, setQueueSearch] = useState('');
  const [queueSort, setQueueSort] = useState<'newest' | 'oldest' | 'severity'>('newest');
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [tabCounts, setTabCounts] = useState({
    active: 0,
    resolved: 0,
    escalated: 0,
    failed: 0,
    all: 0,
    hidden_test_count: 0,
  });

  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<IncidentDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [metricsScope, setMetricsScope] = useState<'live_and_demo' | 'automated_test' | 'all'>('live_and_demo');
  const [baselineInput, setBaselineInput] = useState('');
  const [appliedBaseline, setAppliedBaseline] = useState<number | null>(null);
  const [metrics, setMetrics] = useState<MetricsSummaryResponse | null>(null);

  const [sseState, setSseState] = useState<'connecting' | 'live' | 'reconnecting'>('connecting');
  const lastUpdateAtRef = useRef<number>(Date.now());
  const [isStale, setIsStale] = useState(false);
  const [showTotpModal, setShowTotpModal] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);

  // Guided Tour state (restorable across refresh via sessionStorage)
  const [tourActive, setTourActive] = useState<boolean>(() => sessionStorage.getItem('aegisops_tour_active') === '1');
  const [tourPaused, setTourPaused] = useState(false);
  const [activeTourRun, setActiveTourRun] = useState<DemoRun | null>(null);

  // Recorded Replay state (strictly isolated from live state)
  const [replays, setReplays] = useState<ReplayListItem[]>([]);
  const [activeReplay, setActiveReplay] = useState<ReplayTimeline | null>(null);
  const [replayFrameIdx, setReplayFrameIdx] = useState(0);

  const selectedIdRef = useRef<string | null>(null);
  selectedIdRef.current = selectedIncidentId;

  const canOperate = Boolean(user && (user.highest_role === 'operator' || user.highest_role === 'approver'));

  const loadPublicShowcaseData = useCallback(async () => {
    try {
      const mParams = new URLSearchParams({ scope: metricsScope });
      if (appliedBaseline !== null) {
        mParams.set('manual_baseline_minutes', String(appliedBaseline));
      }
      const topoQs = selectedIdRef.current ? `?incident_id=${encodeURIComponent(selectedIdRef.current)}` : '';
      const [ovResp, rdResp, scResp, prResp, tpResp, mtResp, rpResp] = await Promise.all([
        apiFetch<ShowcaseOverview>('/api/v1/showcase/overview'),
        apiFetch<ReadinessResponse>('/api/v1/showcase/readiness'),
        apiFetch<{ scenarios: ScenarioSpec[]; recent_runs: DemoRun[] }>('/api/v1/showcase/scenarios'),
        apiFetch<{ items: BusinessProbeSample[] }>('/api/v1/showcase/probes?limit=25'),
        apiFetch<TopologyResponse>(`/api/v1/topology${topoQs}`),
        apiFetch<MetricsSummaryResponse>(`/api/v1/metrics/summary?${mParams.toString()}`),
        apiFetch<{ items: ReplayListItem[] }>('/api/v1/showcase/replays'),
      ]);
      setOverview(ovResp);
      setReadiness(rdResp);
      setScenarios(scResp.scenarios);
      setRecentRuns(scResp.recent_runs);
      setProbes(prResp.items);
      setTopology(tpResp);
      setMetrics(mtResp);
      setReplays(rpResp.items);

      const savedRunId = sessionStorage.getItem('aegisops_tour_run_id');
      if (savedRunId && !activeReplay) {
        const matched = scResp.recent_runs.find((r) => r.id === savedRunId);
        if (matched) setActiveTourRun(matched);
      }
      setDataError(null);
    } catch (err) {
      setDataError(err instanceof Error ? err.message : 'Failed to load showcase telemetry');
    }
  }, [metricsScope, appliedBaseline, activeReplay]);

  const loadAuthorizedQueue = useCallback(async () => {
    if (!user) return;
    try {
      const params = new URLSearchParams({
        tab: queueTab,
        hide_test_runs: String(hideTestRuns),
        sort: queueSort,
        limit: '50',
      });
      if (queueSearch.trim()) {
        params.set('search', queueSearch.trim());
      }
      const incResp = await apiFetch<IncidentListResponse>(`/api/v1/incidents?${params.toString()}`);
      setIncidents(incResp.items);
      setTabCounts(incResp.tab_counts);
      lastUpdateAtRef.current = Date.now();
      setIsStale(false);
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 401) {
        setSessionExpired(true);
        setUser(null);
      } else {
        setDataError(err instanceof Error ? err.message : 'Failed to load incident queue');
      }
    }
  }, [user, queueTab, hideTestRuns, queueSort, queueSearch]);

  const loadIncidentDetail = useCallback(async (id: string) => {
    if (!user) return;
    setDetailLoading(true);
    try {
      const detail = await apiFetch<IncidentDetailResponse>(`/api/v1/incidents/${id}`);
      setSelectedDetail(detail);
      setSelectedAssetSlug(detail.incident.asset_slug);
      const topo = await apiFetch<TopologyResponse>(`/api/v1/topology?incident_id=${encodeURIComponent(id)}`);
      setTopology(topo);
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 401) {
        setSessionExpired(true);
        setUser(null);
      } else {
        setDataError(err instanceof Error ? err.message : 'Failed to load incident detail');
      }
    } finally {
      setDetailLoading(false);
    }
  }, [user]);

  const refreshAll = useCallback(() => {
    loadPublicShowcaseData();
    if (user) {
      loadAuthorizedQueue();
      if (selectedIdRef.current) {
        loadIncidentDetail(selectedIdRef.current);
      }
    }
  }, [loadPublicShowcaseData, loadAuthorizedQueue, loadIncidentDetail, user]);

  // Bootstrap OIDC session (never forces redirect; visitors stay in read-only Showcase mode)
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

  // Load showcase data for both Visitor Mode and Authenticated Mode
  useEffect(() => {
    if (authLoading) return;
    loadPublicShowcaseData();
    if (user) {
      loadAuthorizedQueue();
    }
  }, [authLoading, user, loadPublicShowcaseData, loadAuthorizedQueue]);

  // Lazy load Engineering Evidence when Reviewer tab opens
  useEffect(() => {
    if (mainNav === 'evidence' && !evidence) {
      apiFetch<EvidenceResponse>('/api/v1/showcase/evidence')
        .then(setEvidence)
        .catch(() => {
          // handled silently
        });
    }
  }, [mainNav, evidence]);

  // Live SSE subscription when authenticated
  useEffect(() => {
    if (!user) return;
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
        loadPublicShowcaseData();
        loadAuthorizedQueue();
        if (selectedIdRef.current) {
          loadIncidentDetail(selectedIdRef.current);
        }
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
  }, [user, loadPublicShowcaseData, loadAuthorizedQueue, loadIncidentDetail]);

  async function handleLogin() {
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
  }

  async function handleLogout() {
    try {
      await apiFetch('/api/v1/auth/logout', { method: 'POST' });
    } catch {
      // ignore if already expired
    }
    setUser(null);
    setSelectedDetail(null);
    setSelectedIncidentId(null);
  }

  async function openReplay(replayId: string, startTourWithReplay = false) {
    try {
      const res = await apiFetch<{ replay: ReplayTimeline }>(`/api/v1/showcase/replays/${encodeURIComponent(replayId)}`);
      setActiveReplay(res.replay);
      setReplayFrameIdx(0);
      setMainNav('console');
      if (startTourWithReplay) {
        setTourActive(true);
        setTourPaused(false);
        sessionStorage.setItem('aegisops_tour_active', '1');
      }
    } catch (e) {
      setDataError(e instanceof Error ? e.message : 'Unable to load replay timeline');
    }
  }

  if (authLoading) {
    return <main className="shell">Checking OIDC authentication session...</main>;
  }

  const currentReplayFrame = activeReplay?.frames[replayFrameIdx];

  return (
    <main className="shell">
      <header className="shell-header">
        <div>
          <span className="eyebrow">Independent Synthetic Healthcare AIOps Demonstration</span>
          <h1>{user ? 'AegisOps SRE Console' : 'AegisOps SRE Control Plane'}</h1>
        </div>
        <div className="header-controls">
          {user ? (
            <>
              <span className={`badge ${sseState === 'live' ? 'badge-ok' : 'badge-warn'}`}>
                Stream: {sseState}
                {isStale ? ' (stale)' : ''}
              </span>
              <span className="role-pill">
                {user.email} ({user.highest_role})
              </span>
              {user.highest_role === 'approver' && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowTotpModal(true)}
                >
                  {user.totp_verified ? 'Re-enroll TOTP MFA' : 'Enroll TOTP MFA'}
                </button>
              )}
              <button type="button" className="btn btn-ghost" onClick={handleLogout}>
                Sign Out
              </button>
            </>
          ) : (
            <>
              <span className="badge badge-warn">Visitor Mode (Read-Only)</span>
              <button type="button" className="btn btn-primary" onClick={handleLogin}>
                Sign In with Keycloak OIDC (PKCE)
              </button>
            </>
          )}
        </div>
      </header>

      {sessionExpired && (
        <div className="alert-banner alert-warn">
          Your session expired. You are currently in Visitor Mode; sign in again for live operations.
        </div>
      )}
      {authError && <p className="error-text">{authError}</p>}
      {dataError && <div className="alert-banner alert-err">API Error: {dataError}</div>}

      <nav className="subnav-bar" aria-label="Console navigation and presentation controls">
        <div className="tab-group" role="tablist">
          <button
            type="button"
            className={`tab-btn ${mainNav === 'console' ? 'active' : ''}`}
            onClick={() => setMainNav('console')}
          >
            Operations Console
          </button>
          <button
            type="button"
            className={`tab-btn ${mainNav === 'knowledge' ? 'active' : ''}`}
            onClick={() => setMainNav('knowledge')}
          >
            Knowledge Base &amp; Privacy Playground
          </button>
          <button
            type="button"
            className={`tab-btn ${mainNav === 'evidence' ? 'active' : ''}`}
            onClick={() => setMainNav('evidence')}
          >
            Engineering Evidence
          </button>
        </div>

        <div className="header-controls">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setTechnicalMode((m) => !m)}
          >
            View: {technicalMode ? 'Technical Deep-Dive' : 'Executive Overview'}
          </button>
          {replays.length > 0 && !activeReplay && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => openReplay(replays[0].replay_id, true)}
            >
              Recorded Replay ({replays.length})
            </button>
          )}
        </div>
      </nav>

      {overview && !user && (
        <section className="card" style={{ marginBottom: '1rem' }}>
          <div className="section-head">
            <div>
              <strong>What AegisOps Does (Executive Overview)</strong>
              <p className="muted" style={{ fontSize: '0.82rem', margin: '0.2rem 0 0' }}>
                {overview.disclaimer}
              </p>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => openReplay('fixture-traffic-spike-recovery', true)}
            >
              Start Guided Demo (Recorded Replay)
            </button>
          </div>
          <div className="pillars-grid">
            {overview.five_pillars.map((p) => (
              <div key={p.title} className="pillar-tile">
                <strong>{p.title}</strong>
                <div className="muted" style={{ fontSize: '0.76rem', marginTop: 2 }}>{p.detail}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeReplay && (
        <ReplayController
          replays={replays}
          activeReplay={activeReplay}
          frameIndex={replayFrameIdx}
          onSelectReplay={(rid) => openReplay(rid, tourActive)}
          onChangeFrame={setReplayFrameIdx}
          onExitReplay={() => {
            setActiveReplay(null);
            setTourActive(false);
            sessionStorage.removeItem('aegisops_tour_active');
          }}
        />
      )}

      <GuidedTourBar
        active={tourActive}
        paused={tourPaused}
        activeRun={activeTourRun}
        isReplay={Boolean(activeReplay)}
        replayNarration={
          currentReplayFrame
            ? {
                step: currentReplayFrame.lifecycle_step,
                headline: currentReplayFrame.headline,
                detail: currentReplayFrame.narration,
                focus_panel: currentReplayFrame.active_panel,
              }
            : null
        }
        onTogglePause={() => setTourPaused((p) => !p)}
        onSkipStep={() => {
          if (activeReplay && replayFrameIdx < activeReplay.frames.length - 1) {
            setReplayFrameIdx((i) => i + 1);
          }
        }}
        onExit={() => {
          setTourActive(false);
          sessionStorage.removeItem('aegisops_tour_active');
        }}
        onFocusPanel={(panel) => {
          if (panel === 'runbooks' || panel === 'privacy') setMainNav('knowledge');
          else setMainNav('console');
        }}
      />

      {mainNav === 'console' && (
        <div className="detail-stack">
          <MetricsDashboard
            metrics={metrics}
            scope={metricsScope}
            baselineMinutesInput={baselineInput}
            technicalMode={technicalMode}
            onChangeScope={setMetricsScope}
            onChangeBaselineInput={setBaselineInput}
            onApplyBaseline={() => {
              const num = Number(baselineInput);
              setAppliedBaseline(baselineInput.trim() && Number.isFinite(num) && num >= 1 ? num : null);
            }}
          />

          <ChaosLabPanel
            scenarios={scenarios}
            recentRuns={recentRuns}
            readiness={readiness}
            canOperate={canOperate}
            onRefresh={refreshAll}
            onRunLaunched={(run, startTour) => {
              setActiveReplay(null);
              setActiveTourRun(run);
              if (startTour) {
                setTourActive(true);
                sessionStorage.setItem('aegisops_tour_active', '1');
                sessionStorage.setItem('aegisops_tour_run_id', run.id);
              }
              refreshAll();
            }}
            onStartReplayFixture={(fid) => openReplay(fid, true)}
          />

          <div className="console-grid" style={{ marginTop: 0 }}>
            <section className="card">
              <div className="section-head">
                <h2>CMDB Dependency &amp; Blast-Radius Topology</h2>
                <span className="muted-pill">edge: source depends_on target</span>
              </div>
              <TopologyGraph
                topology={topology}
                selectedSlug={selectedAssetSlug}
                onSelectAsset={(slug) => setSelectedAssetSlug(slug)}
              />
            </section>

            <section className="card">
              <div className="section-head">
                <h2>Incidents ({user ? tabCounts.all : 'Sign In Required'})</h2>
                <button type="button" className="btn btn-ghost" onClick={refreshAll}>
                  Refresh
                </button>
              </div>

              {!user ? (
                <div className="empty-state">
                  Sign in via Keycloak OIDC above to inspect live incidents, approve high-risk TOTP actions,
                  or export postmortems. Or launch a <strong>Recorded Replay</strong> to walk through the complete timeline safely.
                </div>
              ) : (
                <>
                  <div className="tab-group" style={{ marginBottom: 8 }} role="tablist" aria-label="Incident queue tabs">
                    {(
                      [
                        ['active', `Active (${tabCounts.active})`],
                        ['resolved', `Resolved (${tabCounts.resolved})`],
                        ['escalated', `Escalated (${tabCounts.escalated})`],
                        ['failed', `Failed (${tabCounts.failed})`],
                        ['all', `All (${tabCounts.all})`],
                      ] as const
                    ).map(([tabKey, label]) => (
                      <button
                        key={tabKey}
                        type="button"
                        className={`tab-btn ${queueTab === tabKey ? 'active' : ''}`}
                        onClick={() => setQueueTab(tabKey)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>

                  <div className="inline-form" style={{ marginTop: 0, marginBottom: 8, alignItems: 'center' }}>
                    <input
                      type="search"
                      placeholder="Search service, alert, UUID..."
                      value={queueSearch}
                      onChange={(e) => setQueueSearch(e.target.value)}
                      style={{ flex: 1, minWidth: 140 }}
                    />
                    <select
                      aria-label="Sort incidents"
                      value={queueSort}
                      onChange={(e) => setQueueSort(e.target.value as 'newest' | 'oldest' | 'severity')}
                    >
                      <option value="newest">Newest</option>
                      <option value="severity">Severity (P1-&gt;P4)</option>
                      <option value="oldest">Oldest</option>
                    </select>
                    <label className="muted" style={{ fontSize: '0.76rem', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <input
                        type="checkbox"
                        checked={hideTestRuns}
                        onChange={(e) => setHideTestRuns(e.target.checked)}
                      />
                      Hide Test Runs ({tabCounts.hidden_test_count})
                    </label>
                  </div>

                  {incidents.length === 0 ? (
                    <div className="empty-state">No incidents matching this filter.</div>
                  ) : (
                    <ul className="incident-list">
                      {incidents.map((inc) => (
                        <li key={inc.id}>
                          <button
                            type="button"
                            className={`incident-row ${selectedIncidentId === inc.id ? 'active' : ''}`}
                            onClick={() => {
                              setSelectedIncidentId(inc.id);
                              loadIncidentDetail(inc.id);
                            }}
                          >
                            <div className="row-top">
                              <span className={`sev-pill sev-${inc.severity}`}>{inc.severity}</span>
                              <span className="state-pill">{inc.state}</span>
                            </div>
                            <div className="row-title">{inc.title}</div>
                            <div className="row-sub">
                              {inc.asset_slug || 'unknown'} · {inc.source_provenance || 'unknown'} ·{' '}
                              {new Date(inc.ingested_at).toLocaleString()}
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </section>
          </div>

          <BusinessProbeCard
            probes={probes}
            canRunProbes={canOperate}
            selectedIncidentId={selectedIncidentId}
            activeDemoRunId={activeTourRun?.id || null}
            onProbeCompleted={(sample) => setProbes((prev) => [sample, ...prev].slice(0, 25))}
          />

          {user && (
            <IncidentDetail
              detail={selectedDetail}
              loading={detailLoading}
              user={user}
              technicalMode={technicalMode}
              onRefresh={refreshAll}
              onOpenPromptInspector={() => setMainNav('knowledge')}
            />
          )}
        </div>
      )}

      {mainNav === 'knowledge' && (
        <div className="detail-stack">
          <PrivacyPromptDrawer
            selectedIncidentId={selectedIncidentId}
            canInspectPrompts={Boolean(user)}
          />
          <RunbookKnowledgePanel canUpload={canOperate} />
        </div>
      )}

      {mainNav === 'evidence' && <EngineeringEvidenceView evidence={evidence} />}

      {showTotpModal && (
        <TotpModal
          onClose={() => setShowTotpModal(false)}
          onVerified={async () => {
            setShowTotpModal(false);
            const me = await apiFetch<UserSession>('/api/v1/auth/me');
            setUser(me);
          }}
        />
      )}
    </main>
  );
}
