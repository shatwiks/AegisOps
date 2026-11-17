import { useEffect, useState } from 'react';
import { apiFetch } from '../lib/pkce';

interface Preset {
  id: string;
  label: string;
  text: string;
}

interface PreviewResult {
  sanitized_text: string;
  total_redactions: number;
  redactions_by_category: Record<string, number>;
  persisted: boolean;
}

interface PromptInspectorData {
  incident_id: string;
  captured: boolean;
  message: string | null;
  prompt_record: {
    model?: string;
    temperature?: number;
    delimiters?: string[];
    system_prompt?: string;
    user_prompt?: string;
    cited_context_slugs?: string[];
    invoked_at?: string;
    latency_ms?: number;
    cached?: boolean;
    validated_output?: Record<string, unknown>;
  } | null;
}

interface Props {
  selectedIncidentId: string | null;
  canInspectPrompts: boolean;
}

export function PrivacyPromptDrawer({ selectedIncidentId, canInspectPrompts }: Props) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [coverageNotes, setCoverageNotes] = useState<{ warning?: string; covered_patterns?: string[]; coverage_limits?: string[] } | null>(null);
  const [inputText, setInputText] = useState('');
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [promptData, setPromptData] = useState<PromptInspectorData | null>(null);
  const [promptErr, setPromptErr] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<{ fictional_presets: Preset[]; coverage_notes: { warning?: string; covered_patterns?: string[]; coverage_limits?: string[] } }>(
      '/api/v1/showcase/privacy/presets',
    )
      .then((res) => {
        setPresets(res.fictional_presets);
        setCoverageNotes(res.coverage_notes);
        if (res.fictional_presets.length > 0 && !inputText) {
          setInputText(res.fictional_presets[0].text);
        }
      })
      .catch(() => {
        // ignore background load error
      });
  }, []);

  async function runPreview() {
    setBusy(true);
    setErr(null);
    try {
      const res = await apiFetch<PreviewResult>('/api/v1/showcase/privacy/preview', {
        method: 'POST',
        body: JSON.stringify({ text: inputText }),
      });
      setPreview(res);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Privacy preview failed');
    } finally {
      setBusy(false);
    }
  }

  async function loadIncidentPrompt() {
    if (!selectedIncidentId) return;
    setPromptErr(null);
    try {
      const res = await apiFetch<PromptInspectorData>(`/api/v1/incidents/${selectedIncidentId}/prompt`);
      setPromptData(res);
    } catch (e) {
      setPromptErr(e instanceof Error ? e.message : 'Unable to load prompt record');
    }
  }

  return (
    <div className="detail-stack">
      <section className="card" aria-label="Privacy Scrubber Playground">
        <div className="section-head">
          <div>
            <h3>Edge Privacy Scrubber Playground (Fictional Test Only)</h3>
            <span className="muted" style={{ fontSize: '0.8rem' }}>
              {coverageNotes?.warning || 'Runs exact ingestion-boundary scrubber in memory (max 8 KiB, 30 req/min). Zero persistence or log emission.'}
            </span>
          </div>
          <button type="button" className="btn btn-ghost" onClick={() => { setInputText(''); setPreview(null); }}>
            Clear Input
          </button>
        </div>

        <div className="header-controls" style={{ marginBottom: '0.65rem' }}>
          {presets.map((p) => (
            <button
              key={p.id}
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                setInputText(p.text);
                setPreview(null);
              }}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="diff-grid">
          <div>
            <label htmlFor="privacy-input" className="muted" style={{ display: 'block', marginBottom: 4 }}>
              Fictional Telemetry / Log Snippet (Input)
            </label>
            <textarea
              id="privacy-input"
              rows={6}
              style={{ width: '100%' }}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
            />
            <div style={{ marginTop: 8 }}>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={runPreview}>
                {busy ? 'Scrubbing...' : 'Test Privacy Scrubber'}
              </button>
            </div>
            {err && <p className="error-text">{err}</p>}
          </div>

          <div>
            <div className="muted" style={{ marginBottom: 4 }}>
              Sanitized Output Sent Down Pipeline ({preview ? `${preview.total_redactions} tokens redacted` : 'Click Test Privacy Scrubber'})
            </div>
            <pre className="json-box" style={{ minHeight: 120, whiteSpace: 'pre-wrap' }}>
              {preview ? preview.sanitized_text : 'Output appears here without touching disk, logs, or Ollama.'}
            </pre>
            {preview && (
              <div className="header-controls" style={{ marginTop: 6 }}>
                {Object.entries(preview.redactions_by_category).map(([cat, cnt]) => (
                  <span key={cat} className="muted-pill">
                    {cat}: {cnt}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {coverageNotes && (
          <details style={{ marginTop: '0.75rem' }}>
            <summary className="details-toggle">Regex &amp; Key-Allowlist Coverage Limits</summary>
            <ul className="timeline" style={{ marginTop: 6 }}>
              {(coverageNotes.covered_patterns || []).map((c) => (
                <li key={c}>Covered: {c}</li>
              ))}
              {(coverageNotes.coverage_limits || []).map((l) => (
                <li key={l} className="muted">Limit: {l}</li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <section className="card" aria-label="Sanitized Prompt Inspector">
        <div className="section-head">
          <div>
            <h3>Captured LLM Prompt Inspector (Authorized Incidents)</h3>
            <span className="muted" style={{ fontSize: '0.8rem' }}>
              Displays the exact sanitized XML-delimited prompt captured at Ollama invocation time — never fabricated post-hoc.
            </span>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={!canInspectPrompts || !selectedIncidentId}
            onClick={loadIncidentPrompt}
          >
            Inspect Selected Incident Prompt
          </button>
        </div>

        {!canInspectPrompts && (
          <p className="muted">Sign in as Viewer, Operator, or Approver to inspect operational incident prompts.</p>
        )}
        {canInspectPrompts && !selectedIncidentId && (
          <p className="muted">Select an incident from the Operations Console queue first, then click Inspect Selected Incident Prompt.</p>
        )}
        {promptErr && <p className="error-text">{promptErr}</p>}
        {promptData && (
          <div>
            {!promptData.captured ? (
              <div className="alert-banner alert-warn">{promptData.message}</div>
            ) : (
              <div className="detail-stack">
                <div className="header-controls">
                  <span className="muted-pill">Model: {promptData.prompt_record?.model}</span>
                  <span className="muted-pill">Latency: {promptData.prompt_record?.latency_ms} ms</span>
                  <span className="muted-pill">Cached: {String(promptData.prompt_record?.cached)}</span>
                  <span className="muted-pill">
                    Delimiters: {(promptData.prompt_record?.delimiters || []).join(', ')}
                  </span>
                </div>
                <pre className="json-box" style={{ whiteSpace: 'pre-wrap' }}>
                  {promptData.prompt_record?.system_prompt}
                </pre>
                <pre className="json-box" style={{ whiteSpace: 'pre-wrap' }}>
                  {promptData.prompt_record?.user_prompt}
                </pre>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
