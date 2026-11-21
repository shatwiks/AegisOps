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
import { Button } from './components/ui/Button';
import { Skeleton } from './components/ui/Skeleton';
import { IncidentQueuePanel } from './features/incidents/IncidentQueuePanel';
import { VisitorOverviewBanner } from './features/overview/VisitorOverviewBanner';
import { CommandHeader } from './features/shell/CommandHeader';
import { WorkspaceNav } from './features/shell/WorkspaceNav';
import { useAuthSession } from './hooks/useAuthSession';
import { useDebouncedValue } from './hooks/useDebouncedValue';
import { useIncidentStream } from './hooks/useIncidentStream';
import { useUrlConsoleState } from './hooks/useUrlConsoleState';
import { apiFetch } from './lib/pkce';
import type {
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
} from './types';

export function App() {
  const {
    user,
    authLoading,
    authError,
    sessionExpired,
    handleLogin,
    handleLogout,
    refreshUser,
    markSessionExpired,
  } = useAuthSession();

  const {
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
  } = useUrlConsoleState(authLoading);

  const debouncedSearch = useDebouncedValue(queueSearch, 200);

  const [overview, setOverview] = useState<ShowcaseOverview | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioSpec[]>([]);
  const [recentRuns, setRecentRuns] = useState<DemoRun[]>([]);
  const [probes, setProbes] = useState<BusinessProbeSample[]>([]);
  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  const [topology, setTopology] = useState<TopologyResponse | null>(null);
  const [selectedAssetSlug, setSelectedAssetSlug] = useState<string | null>(null);

  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [queueLoading, setQueueLoading] = useState(false);
  const [tabCounts, setTabCounts] = useState<IncidentListResponse['tab_counts']>({
    active: 0,
    resolved: 0,
    escalated: 0,
    failed: 0,
    all: 0,
    hidden_test_count: 0,
  });

  const [selectedDetail, setSelectedDetail] = useState<IncidentDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [metricsScope, setMetricsScope] = useState<'live_and_demo' | 'automated_test' | 'all'>('live_and_demo');
  const [baselineInput, setBaselineInput] = useState('');
  const [appliedBaseline, setAppliedBaseline] = useState<number | null>(null);
  const [metrics, setMetrics] = useState<MetricsSummaryResponse | null>(null);

  const [showTotpModal, setShowTotpModal] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);

  const [tourActive, setTourActive] = useState<boolean>(() => sessionStorage.getItem('aegisops_tour_active') === '1');
  const [tourPaused, setTourPaused] = useState(false);
  const [activeTourRun, setActiveTourRun] = useState<DemoRun | null>(null);

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

  const loadAuthorizedQueue = useCallback(async (showLoader = false) => {
    if (!user) return;
    if (showLoader) setQueueLoading(true);
    try {
      const params = new URLSearchParams({
        tab: queueTab,
        hide_test_runs: String(hideTestRuns),
        sort: queueSort,
        limit: '50',
      });
      if (debouncedSearch.trim()) {
        params.set('search', debouncedSearch.trim());
      }
      const incResp = await apiFetch<IncidentListResponse>(`/api/v1/incidents?${params.toString()}`);
      setIncidents(incResp.items);
      setTabCounts(incResp.tab_counts);
      setDataError(null);
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 401) {
        markSessionExpired();
      } else {
        setDataError(err instanceof Error ? err.message : 'Failed to load incident queue');
      }
    } finally {
      if (showLoader) setQueueLoading(false);
    }
  }, [user, queueTab, hideTestRuns, queueSort, debouncedSearch, markSessionExpired]);

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
        markSessionExpired();
      } else {
        setDataError(err instanceof Error ? err.message : 'Failed to load incident detail');
      }
    } finally {
      setDetailLoading(false);
    }
  }, [user, markSessionExpired]);

  const loadEvidence = useCallback(() => {
    setEvidenceError(null);
    apiFetch<EvidenceResponse>('/api/v1/showcase/evidence')
      .then((res) => setEvidence(res))
      .catch((err) => {
        setEvidenceError(err instanceof Error ? err.message : 'Failed to load engineering evidence');
      });
  }, []);

  const refreshAll = useCallback(() => {
    loadPublicShowcaseData();
    if (user) {
      loadAuthorizedQueue(false);
      if (selectedIdRef.current) {
        loadIncidentDetail(selectedIdRef.current);
      }
    }
  }, [loadPublicShowcaseData, loadAuthorizedQueue, loadIncidentDetail, user]);

  const { sseState, isStale } = useIncidentStream(Boolean(user), refreshAll);

  useEffect(() => {
    if (authLoading) return;
    loadPublicShowcaseData();
    if (user) {
      loadAuthorizedQueue(true);
      if (selectedIdRef.current) {
        loadIncidentDetail(selectedIdRef.current);
      }
    }
  }, [authLoading, user, loadPublicShowcaseData, loadAuthorizedQueue, loadIncidentDetail]);

  useEffect(() => {
    if (mainNav === 'evidence' && !evidence && !evidenceError) {
      loadEvidence();
    }
  }, [mainNav, evidence, evidenceError, loadEvidence]);

  async function onSignOutClick() {
    await handleLogout();
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
    return (
      <div className="shell-main" aria-label="Checking OIDC authentication session">
        <div className="detail-stack">
          <Skeleton height={60} />
          <Skeleton height={220} />
          <Skeleton height={380} />
        </div>
      </div>
    );
  }

  const currentReplayFrame = activeReplay?.frames[replayFrameIdx];

  return (
    <div>
      <CommandHeader
        user={user}
        sseState={sseState}
        isStale={isStale}
        onLogin={handleLogin}
        onLogout={onSignOutClick}
        onOpenTotp={() => setShowTotpModal(true)}
      />

      <WorkspaceNav
        mainNav={mainNav}
        technicalMode={technicalMode}
        replaysCount={replays.length}
        replayActive={Boolean(activeReplay)}
        onChangeNav={setMainNav}
        onToggleTechnicalMode={() => setTechnicalMode((m) => !m)}
        onStartReplay={() => {
          if (replays.length > 0) openReplay(replays[0].replay_id, true);
        }}
      />

      <main className="shell-main">
        {sessionExpired && (
          <div className="alert-banner alert-warn" role="status">
            Your session expired. You are currently in Visitor Mode; sign in again for live operations.
          </div>
        )}
        {authError && (
          <p className="error-text" role="alert">
            {authError}
          </p>
        )}
        {dataError && (
          <div
            className="alert-banner alert-err"
            role="alert"
            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}
          >
            <span>API Error: {dataError}</span>
            <Button variant="ghost" size="sm" onClick={refreshAll}>
              Retry
            </Button>
          </div>
        )}

        {overview && !user && (
          <VisitorOverviewBanner
            overview={overview}
            onStartGuidedReplay={() => openReplay('fixture-traffic-spike-recovery', true)}
          />
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
              <section className="card" aria-label="CMDB Dependency and Blast-Radius Topology">
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

              <IncidentQueuePanel
                user={user}
                loading={queueLoading}
                incidents={incidents}
                tabCounts={tabCounts}
                queueTab={queueTab}
                queueSearch={queueSearch}
                queueSort={queueSort}
                hideTestRuns={hideTestRuns}
                selectedIncidentId={selectedIncidentId}
                onChangeTab={setQueueTab}
                onChangeSearch={setQueueSearch}
                onChangeSort={setQueueSort}
                onToggleHideTestRuns={setHideTestRuns}
                onSelectIncident={(id) => {
                  setSelectedIncidentId(id);
                  loadIncidentDetail(id);
                }}
                onRefresh={refreshAll}
                onStartReplay={() => openReplay('fixture-traffic-spike-recovery', true)}
              />
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

        {mainNav === 'evidence' && (
          <EngineeringEvidenceView
            evidence={evidence}
            error={evidenceError}
            onRetry={loadEvidence}
          />
        )}

        {showTotpModal && (
          <TotpModal
            onClose={() => setShowTotpModal(false)}
            onVerified={async () => {
              setShowTotpModal(false);
              await refreshUser();
            }}
          />
        )}
      </main>
    </div>
  );
}
