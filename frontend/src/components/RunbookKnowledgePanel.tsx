import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { apiFetch } from '../lib/pkce';
import type { RunbookSummary } from '../types';

interface Props {
  canUpload: boolean;
}

interface SearchHit {
  rrf_rank: number;
  slug: string;
  title: string;
  doc_type: string;
  service_slug: string;
  version: string;
  source: string;
  vector_similarity: number;
  vector_rank: number | null;
  lexical_score: number;
  lexical_rank: number | null;
  rrf_score: number;
  passes_cosine_threshold: boolean;
  passes_lexical_corroboration: boolean;
  is_primary_evidence: boolean;
  matched_passage: string;
}

interface SearchResponse {
  status: string;
  hits: SearchHit[];
  ambiguous: boolean;
  indexing_in_progress_count: number;
  explanation?: {
    rrf_k: number;
    cosine_similarity_threshold: number;
    lexical_corroboration_rule: string;
    embedding_model: string;
    embedding_dimensions: number;
    plain_english: string;
  };
  detail?: string;
}

export function RunbookKnowledgePanel({ canUpload }: Props) {
  const [docs, setDocs] = useState<RunbookSummary[]>([]);
  const [counts, setCounts] = useState({ total: 0, ready: 0, indexing: 0, failed: 0 });
  const [filterQ, setFilterQ] = useState('');
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [selectedDocBody, setSelectedDocBody] = useState<string | null>(null);
  const [loadingDocs, setLoadingDocs] = useState(false);

  // Hybrid Search Tester state
  const [searchQ, setSearchQ] = useState('ERR_PG_POOL_TIMEOUT_57P03 eligibility-api');
  const [searchSvc, setSearchSvc] = useState('');
  const [searchRes, setSearchRes] = useState<SearchResponse | null>(null);
  const [searchBusy, setSearchBusy] = useState(false);

  // Upload Drawer state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);

  const loadRunbooks = useCallback(async () => {
    setLoadingDocs(true);
    try {
      const qs = filterQ.trim() ? `?q=${encodeURIComponent(filterQ.trim())}` : '';
      const res = await apiFetch<{
        items: RunbookSummary[];
        counts: { total: number; ready: number; indexing: number; failed: number };
      }>(`/api/v1/runbooks${qs}`);
      setDocs(res.items);
      setCounts(res.counts);
    } catch {
      // keep prior state on error
    } finally {
      setLoadingDocs(false);
    }
  }, [filterQ]);

  useEffect(() => {
    loadRunbooks();
  }, [loadRunbooks]);

  async function inspectRunbook(slug: string) {
    setSelectedSlug(slug);
    try {
      const res = await apiFetch<{ runbook: RunbookSummary & { body_markdown: string } }>(`/api/v1/runbooks/${slug}`);
      setSelectedDocBody(res.runbook.body_markdown);
    } catch {
      setSelectedDocBody('Unable to load runbook Markdown content.');
    }
  }

  async function runHybridSearch(e: FormEvent) {
    e.preventDefault();
    setSearchBusy(true);
    setSearchRes(null);
    try {
      const res = await apiFetch<SearchResponse>('/api/v1/runbooks/search', {
        method: 'POST',
        body: JSON.stringify({
          query: searchQ,
          service_slug: searchSvc.trim() || null,
          top_k: 5,
        }),
      });
      setSearchRes(res);
    } catch (err) {
      setSearchRes({
        status: 'unavailable',
        hits: [],
        ambiguous: false,
        indexing_in_progress_count: 0,
        detail: err instanceof Error ? err.message : 'Search failed',
      });
    } finally {
      setSearchBusy(false);
    }
  }

  async function handleUploadSubmit(e: FormEvent) {
    e.preventDefault();
    if (!uploadFile) return;
    setUploadBusy(true);
    setUploadErr(null);
    setUploadStatus(null);
    try {
      const form = new FormData();
      form.append('file', uploadFile);
      const res = await apiFetch<{
        runbook: RunbookSummary;
        lifecycle_trace: string[];
        indexing_error: string | null;
      }>('/api/v1/runbooks/upload', {
        method: 'POST',
        body: form,
      });
      setUploadStatus(
        `Lifecycle: ${res.lifecycle_trace.join(' -> ')} | Status: ${res.runbook.indexing_status}${
          res.indexing_error ? ` (${res.indexing_error})` : ''
        }`,
      );
      setUploadFile(null);
      loadRunbooks();
    } catch (err) {
      setUploadErr(err instanceof Error ? err.message : 'Upload rejected by validation guard');
    } finally {
      setUploadBusy(false);
    }
  }

  async function retryIndex(slug: string) {
    try {
      await apiFetch(`/api/v1/runbooks/${slug}/retry-index`, { method: 'POST' });
      loadRunbooks();
    } catch {
      // handled visually on reload
    }
  }

  return (
    <div className="detail-stack">
      <section className="card" aria-label="Test Hybrid Search">
        <div className="section-head">
          <div>
            <h3>Test Hybrid Search (PostgreSQL FTS + 768-dim pgvector + RRF)</h3>
            <span className="muted" style={{ fontSize: '0.8rem' }}>
              Uses the exact production retrieval pipeline &amp; cosine threshold policy gate.
            </span>
          </div>
          <span className="muted-pill">
            Indexed READY: {counts.ready} / Total: {counts.total}
            {counts.indexing > 0 ? ` (${counts.indexing} indexing)` : ''}
          </span>
        </div>

        <form onSubmit={runHybridSearch} className="inline-form" style={{ marginTop: 0 }}>
          <input
            type="text"
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            placeholder="Query alertname, error code, or symptom..."
            style={{ flex: 2, minWidth: 240 }}
            required
          />
          <input
            type="text"
            value={searchSvc}
            onChange={(e) => setSearchSvc(e.target.value)}
            placeholder="Optional service filter (e.g. eligibility-api)"
            style={{ flex: 1, minWidth: 180 }}
          />
          <button type="submit" className="btn btn-primary" disabled={searchBusy}>
            {searchBusy ? 'Searching...' : 'Test Hybrid Search'}
          </button>
        </form>

        {searchRes && (
          <div style={{ marginTop: '0.85rem' }}>
            {searchRes.detail && <div className="alert-banner alert-warn">{searchRes.detail}</div>}
            {searchRes.explanation && (
              <p className="muted" style={{ fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                {searchRes.explanation.plain_english}
              </p>
            )}
            {searchRes.ambiguous && (
              <div className="alert-banner alert-warn">
                Ambiguous or sub-threshold top hit detected; inspect vector cosine vs. 0.78 gate carefully.
              </div>
            )}
            {searchRes.hits.length === 0 ? (
              <div className="empty-state">No READY indexed runbooks matched that query.</div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>RRF #</th>
                    <th>Document</th>
                    <th>Cosine Sim</th>
                    <th>Lexical Score</th>
                    <th>RRF Score</th>
                    <th>Policy Gate</th>
                  </tr>
                </thead>
                <tbody>
                  {searchRes.hits.map((h) => (
                    <tr key={h.slug}>
                      <td>#{h.rrf_rank}</td>
                      <td>
                        <strong>{h.slug}</strong> <span className="muted-pill">{h.source}</span>
                        <div className="muted" style={{ fontSize: '0.75rem' }}>{h.matched_passage}</div>
                      </td>
                      <td>
                        {h.vector_similarity.toFixed(4)} {h.vector_rank ? `(rank #${h.vector_rank})` : ''}
                      </td>
                      <td>
                        {h.lexical_score.toFixed(4)} {h.lexical_rank ? `(rank #${h.lexical_rank})` : '(unmatched)'}
                      </td>
                      <td>{h.rrf_score.toFixed(6)}</td>
                      <td>
                        <span className={`probe-pill probe-${h.is_primary_evidence ? 'PASS' : 'FAIL'}`}>
                          {h.passes_cosine_threshold
                            ? 'Cosine >= 0.78 PASS'
                            : h.passes_lexical_corroboration
                              ? 'Lexical Corroboration PASS'
                              : 'Below Threshold'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </section>

      <div className="console-grid" style={{ marginTop: 0 }}>
        <section className="card" aria-label="Knowledge Base Browser">
          <div className="section-head">
            <h3>Runbook &amp; Postmortem Browser ({docs.length} shown)</h3>
            <div className="header-controls">
              <input
                type="search"
                value={filterQ}
                onChange={(e) => setFilterQ(e.target.value)}
                placeholder="Filter title, slug, symptom..."
              />
              <button type="button" className="btn btn-ghost" onClick={loadRunbooks}>
                {loadingDocs ? 'Loading...' : 'Refresh'}
              </button>
            </div>
          </div>

          <div style={{ maxHeight: 360, overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Slug / Title</th>
                  <th>Service</th>
                  <th>Risk / Mode</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr
                    key={d.slug}
                    onClick={() => inspectRunbook(d.slug)}
                    style={{ cursor: 'pointer', background: selectedSlug === d.slug ? 'rgba(56,189,248,0.1)' : undefined }}
                  >
                    <td>
                      <strong>{d.slug}</strong> v{d.version}
                      <div className="muted" style={{ fontSize: '0.75rem' }}>{d.title}</div>
                    </td>
                    <td><code>{d.service_slug}</code></td>
                    <td>
                      <span className={`sev-pill ${d.risk_tier === 'HIGH' ? 'sev-P1' : 'sev-P3'}`}>
                        {d.risk_tier} · {d.approval_mode}
                      </span>
                    </td>
                    <td>
                      <span className={`probe-pill probe-${d.indexing_status === 'READY' ? 'PASS' : d.indexing_status === 'FAILED' ? 'FAIL' : 'DEGRADED'}`}>
                        {d.indexing_status}
                      </span>
                      {d.indexing_status === 'FAILED' && canUpload && (
                        <button
                          type="button"
                          className="btn btn-ghost"
                          style={{ marginLeft: 6, padding: '2px 6px', fontSize: '0.72rem' }}
                          onClick={(ev) => {
                            ev.stopPropagation();
                            retryIndex(d.slug);
                          }}
                        >
                          Retry
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {selectedDocBody !== null && (
            <div style={{ marginTop: '0.75rem' }}>
              <div className="muted" style={{ marginBottom: 4 }}>
                Sanitized Markdown Source: <strong>{selectedSlug}</strong> (HTML scripts disallowed)
              </div>
              <pre className="json-box" style={{ maxHeight: 240, whiteSpace: 'pre-wrap' }}>
                {selectedDocBody}
              </pre>
            </div>
          )}
        </section>

        <section className="card" aria-label="Upload Custom Markdown Runbook">
          <h3>Upload Reference Runbook (.md)</h3>
          <p className="muted" style={{ fontSize: '0.8rem' }}>
            Uploaded Markdown is indexed through <code>UPLOADED -&gt; VALIDATING -&gt; INDEXING -&gt; READY</code> for Hybrid RAG retrieval.
            Unknown playbooks and risk downgrades are rejected; uploads never create new executable commands.
          </p>
          <form onSubmit={handleUploadSubmit} className="detail-stack">
            <input
              type="file"
              accept=".md,text/markdown"
              disabled={!canUpload || uploadBusy}
              onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
            />
            <button type="submit" className="btn btn-primary" disabled={!canUpload || !uploadFile || uploadBusy}>
              {uploadBusy ? 'Validating & Indexing...' : 'Validate, Upload & Embed .md'}
            </button>
            {!canUpload && (
              <p className="muted" style={{ fontSize: '0.8rem' }}>
                Sign in with Operator or Approver role to upload custom runbooks.
              </p>
            )}
            {uploadErr && <div className="alert-banner alert-err">{uploadErr}</div>}
            {uploadStatus && <div className="alert-banner alert-ok">{uploadStatus}</div>}
          </form>
        </section>
      </div>
    </div>
  );
}
