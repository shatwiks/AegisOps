import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { Skeleton } from '../../components/ui/Skeleton';
import type { QueueSort, QueueTab } from '../../hooks/useUrlConsoleState';
import type { IncidentListResponse, IncidentSummary, UserSession } from '../../types';

interface Props {
  user: UserSession | null;
  loading: boolean;
  incidents: IncidentSummary[];
  tabCounts: IncidentListResponse['tab_counts'];
  queueTab: QueueTab;
  queueSearch: string;
  queueSort: QueueSort;
  hideTestRuns: boolean;
  selectedIncidentId: string | null;
  onChangeTab: (tab: QueueTab) => void;
  onChangeSearch: (search: string) => void;
  onChangeSort: (sort: QueueSort) => void;
  onToggleHideTestRuns: (hide: boolean) => void;
  onSelectIncident: (id: string) => void;
  onRefresh: () => void;
  onStartReplay: () => void;
}

/** Filtered incident queue supporting SQL tab counts, debounced search, sort, and Visitor empty state. */
export function IncidentQueuePanel({
  user,
  loading,
  incidents,
  tabCounts,
  queueTab,
  queueSearch,
  queueSort,
  hideTestRuns,
  selectedIncidentId,
  onChangeTab,
  onChangeSearch,
  onChangeSort,
  onToggleHideTestRuns,
  onSelectIncident,
  onRefresh,
  onStartReplay,
}: Props) {
  const hasFilters = queueTab !== 'all' || queueSearch.trim() !== '' || !hideTestRuns;

  return (
    <section className="card" aria-label="Incident Queue">
      <div className="section-head">
        <h2>Incidents ({user ? tabCounts.all : 'Sign In Required'})</h2>
        <Button variant="ghost" size="sm" onClick={onRefresh}>
          Refresh
        </Button>
      </div>

      {!user ? (
        <EmptyState
          title="Visitor Read-Only Mode Active"
          description={
            <>
              Sign in via Keycloak OIDC above to inspect live incidents, approve high-risk TOTP actions,
              or export postmortems. Or launch a <strong>Recorded Replay</strong> to walk through the complete timeline safely.
            </>
          }
          action={
            <Button variant="secondary" size="sm" onClick={onStartReplay}>
              Start Guided Demo (Recorded Replay)
            </Button>
          }
        />
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
                role="tab"
                aria-selected={queueTab === tabKey}
                className={`tab-btn tabular-nums ${queueTab === tabKey ? 'active' : ''}`}
                onClick={() => onChangeTab(tabKey)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="inline-form" style={{ marginTop: 0, marginBottom: 8, alignItems: 'center' }}>
            <label htmlFor="incident-queue-search" className="sr-only">
              Search incidents by service, alert, or UUID
            </label>
            <input
              id="incident-queue-search"
              type="search"
              placeholder="Search service, alert, UUID..."
              value={queueSearch}
              onChange={(e) => onChangeSearch(e.target.value)}
              style={{ flex: 1, minWidth: 140 }}
            />
            <select
              aria-label="Sort incidents"
              value={queueSort}
              onChange={(e) => onChangeSort(e.target.value as QueueSort)}
            >
              <option value="newest">Newest</option>
              <option value="severity">Severity (P1-&gt;P4)</option>
              <option value="oldest">Oldest</option>
            </select>
            <label className="muted tabular-nums" style={{ fontSize: '0.76rem', display: 'flex', alignItems: 'center', gap: 4 }}>
              <input
                type="checkbox"
                checked={hideTestRuns}
                onChange={(e) => onToggleHideTestRuns(e.target.checked)}
              />
              Hide Test Runs ({tabCounts.hidden_test_count})
            </label>
          </div>

          {loading ? (
            <div className="detail-stack" aria-label="Loading incident queue">
              <Skeleton height={68} />
              <Skeleton height={68} />
              <Skeleton height={68} />
            </div>
          ) : incidents.length === 0 ? (
            <EmptyState
              description="No incidents matching this filter."
              action={
                hasFilters ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      onChangeTab('all');
                      onChangeSearch('');
                      onToggleHideTestRuns(true);
                    }}
                  >
                    Clear Filters
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <ul className="incident-list">
              {incidents.map((inc) => (
                <li key={inc.id}>
                  <button
                    type="button"
                    aria-pressed={selectedIncidentId === inc.id}
                    className={`incident-row ${selectedIncidentId === inc.id ? 'active' : ''}`}
                    onClick={() => onSelectIncident(inc.id)}
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
  );
}
