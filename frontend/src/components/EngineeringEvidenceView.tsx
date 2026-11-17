import type { EvidenceResponse } from '../types';

interface Props {
  evidence: EvidenceResponse | null;
}

export function EngineeringEvidenceView({ evidence }: Props) {
  if (!evidence) {
    return <div className="card">Loading build, benchmark, and test gate evidence...</div>;
  }

  return (
    <div className="detail-stack" aria-label="Engineering Evidence Overview">
      <section className="card">
        <div className="section-head">
          <h3>Running Build &amp; Environment Metadata</h3>
          <span className="muted-pill">Commit: {evidence.build.commit} ({evidence.build.branch})</span>
        </div>
        <div className="meta-grid">
          <div><strong>App Version:</strong> {evidence.build.app_version}</div>
          <div><strong>Python / Alembic Rev:</strong> {evidence.build.python_version} / <code>{evidence.build.alembic_revision}</code></div>
          <div><strong>Local Chat Model:</strong> <code>{evidence.build.chat_model}</code></div>
          <div>
            <strong>Embedding Model / Cos Threshold:</strong>{' '}
            <code>{evidence.build.embedding_model}</code> ({evidence.build.embedding_dimensions}d, &gt;= {evidence.build.cosine_threshold})
          </div>
          <div><strong>Sustained Watchdog Window:</strong> {evidence.build.sustained_recovery_seconds}s</div>
          <div><strong>Working Tree Dirty:</strong> {String(evidence.build.dirty_working_tree ?? 'unknown')}</div>
        </div>
      </section>

      <section className="card">
        <h3>Trust Boundaries &amp; Explicit Scope Limits</h3>
        <ul className="timeline">
          {evidence.architecture_boundaries.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      </section>

      <div className="console-grid" style={{ marginTop: 0 }}>
        <section className="card">
          <h3>Ragas Offline LLM Evaluation (Synthetic Corpus)</h3>
          {evidence.benchmarks.ragas ? (
            <div className="detail-stack">
              <div className="meta-grid">
                <div><strong>Models:</strong> {evidence.benchmarks.ragas.model} + {evidence.benchmarks.ragas.embedding_model}</div>
                <div><strong>Samples:</strong> {evidence.benchmarks.ragas.sample_count} scenarios</div>
                <div><strong>Faithfulness:</strong> {evidence.benchmarks.ragas.metrics?.faithfulness ?? 'N/A'}</div>
                <div><strong>Context Recall:</strong> {evidence.benchmarks.ragas.metrics?.context_recall ?? 'N/A'}</div>
              </div>
              <p className="muted" style={{ fontSize: '0.8rem' }}>{evidence.benchmarks.ragas.limitations}</p>
            </div>
          ) : (
            <div className="empty-state">Ragas artifact not found in docs/evidence/ragas-evaluation.json.</div>
          )}
        </section>

        <section className="card">
          <h3>k6 Webhook Burst &amp; Idempotency Benchmark</h3>
          {evidence.benchmarks.k6 ? (
            <div className="meta-grid">
              <div><strong>HTTP Requests:</strong> {evidence.benchmarks.k6.total_requests}</div>
              <div><strong>p95 Duration:</strong> {evidence.benchmarks.k6.http_req_duration_p95_ms?.toFixed(1)} ms</div>
              <div><strong>Checks Passed:</strong> {evidence.benchmarks.k6.checks_passed}</div>
              <div><strong>Checks Failed:</strong> {evidence.benchmarks.k6.checks_failed}</div>
            </div>
          ) : (
            <div className="empty-state">k6 summary artifact not found in docs/evidence/k6-summary.json.</div>
          )}
        </section>
      </div>

      <section className="card">
        <h3>Verification Test Gate Logs &amp; Artifacts</h3>
        {evidence.test_reports.length === 0 ? (
          <div className="empty-state">No verification gate log artifacts found yet.</div>
        ) : (
          evidence.test_reports.map((rep) => (
            <details key={rep.filename} style={{ marginBottom: '0.65rem' }}>
              <summary className="details-toggle">
                {rep.filename} — modified {new Date(rep.modified_at_utc).toLocaleString()} ({rep.size_bytes} bytes)
              </summary>
              <pre className="json-box" style={{ whiteSpace: 'pre-wrap' }}>{rep.excerpt}</pre>
            </details>
          ))
        )}
        <h4 style={{ marginTop: '0.85rem', marginBottom: '0.35rem' }}>Documentation Reference Paths</h4>
        <ul className="timeline">
          {evidence.documentation_links.map((d) => (
            <li key={d.path}><strong>{d.label}:</strong> <code>{d.path}</code></li>
          ))}
        </ul>
      </section>
    </div>
  );
}
