import { useCallback, useMemo, useState } from 'react';
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { TopologyResponse } from '../types';
import { Skeleton } from './ui/Skeleton';

interface Props {
  topology: TopologyResponse | null;
  selectedSlug: string | null;
  onSelectAsset: (slug: string) => void;
}

const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  'member-portal-gateway': { x: 40, y: 40 },
  'pharmacy-prior-auth': { x: 40, y: 175 },
  'edi-837-ingest': { x: 40, y: 315 },
  'claims-processor': { x: 290, y: 270 },
  'eligibility-api': { x: 310, y: 120 },
  'provider-directory': { x: 310, y: 0 },
  'postgres-claims-db': { x: 615, y: 215 },
  'redis-session-cache': { x: 615, y: 50 },
};

function shortImageTag(image?: string): string {
  if (!image) return '';
  const parts = image.split(':');
  return parts.length > 1 ? `:${parts[parts.length - 1]}` : image;
}

function TopologyInner({ topology, selectedSlug, onSelectAsset }: Props) {
  const { fitView } = useReactFlow();
  const [viewMode, setViewMode] = useState<'graph' | 'table'>('graph');

  const handleNodeClick = useCallback<NodeMouseHandler>(
    (_, node) => {
      onSelectAsset(node.id);
      fitView({ nodes: [{ id: node.id }], duration: 180, padding: 0.6 });
    },
    [fitView, onSelectAsset],
  );

  const nodes: Node[] = useMemo(() => {
    if (!topology) return [];
    return topology.nodes.map((item, idx) => {
      const hasIncident = item.active_incidents.length > 0;
      const impacted = item.downstream_impacted;
      const isSelected = selectedSlug === item.slug;

      let border = '1px solid var(--status-success)';
      let background = 'var(--bg-elevated)';
      if (hasIncident) {
        border = '2px solid var(--status-danger)';
        background = 'var(--status-danger-surface)';
      } else if (impacted) {
        border = '2px solid var(--status-warning)';
        background = 'var(--status-warning-surface)';
      }
      if (isSelected) {
        border = '2px solid var(--accent-highlight)';
      }

      const pos = NODE_POSITIONS[item.slug] ?? { x: (idx % 3) * 260, y: Math.floor(idx / 3) * 120 };
      const statusBadge = hasIncident
        ? `${item.active_incidents[0].severity} ${item.active_incidents[0].state}`
        : impacted
          ? 'DOWNSTREAM IMPACT'
          : 'HEALTHY';

      const statusClass = hasIncident
        ? 'topo-status-danger'
        : impacted
          ? 'topo-status-warn'
          : 'topo-status-ok';

      const k8s = item.k8s_live;
      const diff = item.selected_run_diff;

      return {
        id: item.slug,
        position: pos,
        data: {
          label: (
            <div className="topo-node-content">
              <div className="topo-node-slug">{item.slug}</div>
              <div className="topo-node-meta">
                {item.asset_type} · {item.criticality.replace('TIER_', 'T')}
              </div>
              {k8s && k8s.available && (
                <div className="topo-node-live">
                  <span>{k8s.replica_label}</span>
                  {k8s.memory_limit && k8s.memory_limit !== 'unset' && ` · ${k8s.memory_limit}`}
                  {k8s.image && <span> · {shortImageTag(k8s.image)}</span>}
                  {k8s.stale && <span className="topo-node-stale"> (stale)</span>}
                </div>
              )}
              {k8s && k8s.virtual_cmdb_node && (
                <div className="topo-node-virtual">Logical CMDB node</div>
              )}
              {diff && (
                <div className="topo-node-diff">
                  Δ {diff.playbook_id}: {diff.before.replicas ?? '?'}→{diff.after.replicas ?? '?'} pods ·{' '}
                  {diff.after.memory_limit || shortImageTag(diff.after.image)}
                </div>
              )}
              <div className={`topo-node-status ${statusClass}`}>
                {statusBadge}
              </div>
            </div>
          ),
        },
        style: {
          background,
          border,
          borderRadius: 8,
          padding: 8,
          width: 230,
        },
      };
    });
  }, [topology, selectedSlug]);

  const edges: Edge[] = useMemo(() => {
    if (!topology) return [];
    return topology.edges.map((e) => ({
      id: e.id,
      source: e.source_slug,
      target: e.target_slug,
      label: e.dependency_type,
      animated: true,
      style: { stroke: 'var(--text-dim)' },
      labelStyle: { fill: 'var(--text-muted)', fontSize: 9 },
      markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--text-dim)' },
    }));
  }, [topology]);

  if (!topology) {
    return (
      <div className="detail-stack" aria-label="Loading CMDB topology graph">
        <Skeleton height={34} width={280} />
        <Skeleton height={390} />
      </div>
    );
  }

  const selectedNode = topology.nodes.find((n) => n.slug === selectedSlug) || null;

  return (
    <div>
      <div className="header-controls" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
        <div className="tab-group" role="tablist" aria-label="Topology display mode">
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'graph'}
            className={`tab-btn ${viewMode === 'graph' ? 'active' : ''}`}
            onClick={() => setViewMode('graph')}
          >
            Graph View
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'table'}
            className={`tab-btn ${viewMode === 'table' ? 'active' : ''}`}
            onClick={() => setViewMode('table')}
          >
            Accessible Table View
          </button>
        </div>
        {topology.observed_at && (
          <span className="mono-small">K8s snapshot: {new Date(topology.observed_at).toLocaleTimeString()}</span>
        )}
      </div>

      {viewMode === 'graph' ? (
        <div className="topo-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodeClick={handleNodeClick}
            fitView
            attributionPosition="bottom-left"
          >
            <Background color="var(--bg-control)" gap={18} />
            <Controls />
          </ReactFlow>
        </div>
      ) : (
        <div style={{ maxHeight: 390, overflowY: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Asset</th>
                <th>Tier / Type</th>
                <th>Live K8s Replicas &amp; Image</th>
                <th>Memory Limit</th>
                <th>Health / Blast Impact</th>
              </tr>
            </thead>
            <tbody>
              {topology.nodes.map((n) => (
                <tr
                  key={n.slug}
                  onClick={() => onSelectAsset(n.slug)}
                  className={`topo-row-clickable ${selectedSlug === n.slug ? 'topo-row-selected' : ''}`}
                >
                  <td>
                    <button
                      type="button"
                      className="btn btn-ghost ui-btn--sm"
                      onClick={(event) => {
                        event.stopPropagation();
                        onSelectAsset(n.slug);
                      }}
                    >
                      <strong>{n.slug}</strong>
                    </button>
                  </td>
                  <td>{n.criticality.replace('TIER_', 'T')} · {n.asset_type}</td>
                  <td>
                    {n.k8s_live?.replica_label || 'N/A'}
                    {n.k8s_live?.image && <div className="mono-small">{n.k8s_live.image}</div>}
                  </td>
                  <td><code>{n.k8s_live?.memory_limit || '—'}</code></td>
                  <td>
                    {n.active_incidents.length > 0
                      ? `${n.active_incidents[0].severity} ${n.active_incidents[0].state}`
                      : n.downstream_impacted
                        ? 'DOWNSTREAM IMPACT'
                        : 'HEALTHY'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedNode && selectedNode.k8s_live && (
        <div className="k8s-fact-strip">
          <strong>Selected Node K8s Facts ({selectedNode.slug}):</strong>{' '}
          <span>{selectedNode.k8s_live.replica_label}</span>
          {selectedNode.k8s_live.rollout_status && ` · Rollout: ${selectedNode.k8s_live.rollout_status}`}
          {selectedNode.k8s_live.container_name && ` · Container: ${selectedNode.k8s_live.container_name}`}
          {selectedNode.k8s_live.memory_limit && ` · Mem Limit: ${selectedNode.k8s_live.memory_limit}`}
          {selectedNode.k8s_live.image && ` · Image: ${selectedNode.k8s_live.image}`}
        </div>
      )}
    </div>
  );
}

export function TopologyGraph(props: Props) {
  return (
    <ReactFlowProvider>
      <TopologyInner {...props} />
    </ReactFlowProvider>
  );
}
