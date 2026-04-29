import { useState } from 'react'
import { DocPicker } from '../components/DocPicker'
import { apiJson, apiPostBlob, triggerDownload } from '../api/client'

type GlossaryItem = { term?: string; definition?: string }

type SummaryResult = {
  summary?: string
  key_points?: string[]
  action_items?: string[]
  formulas?: string[]
  glossary?: GlossaryItem[]
  source_documents?: string[]
  total_pages?: number
  chunk_count?: number
  image_notes?: string[]
  processing_notes?: string[]
}

const MAX_DOCS = 10

const LENGTH_OPTS = [
  { id: 'short', label: 'Short', hint: 'Brief overview' },
  { id: 'medium', label: 'Medium', hint: 'Balanced depth' },
  { id: 'long', label: 'Long', hint: 'More detail' },
] as const

const RAG_OPTS = [
  { id: 'auto' as const, label: 'Auto', hint: 'Recommended' },
  { id: 'on' as const, label: 'RAG', hint: 'Retrieved passages' },
  { id: 'off' as const, label: 'Full text', hint: 'Extracted text only' },
] as const

const SUMMARIZE_SCOPE_HINT =
  'Upload supported files into the Library, then tick documents for this run. The first selected file anchors the summary; add up to nine more to merge.'

export function SummarizePage() {
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [length, setLength] = useState('medium')
  /** Auto: server uses RAG for multi-doc / very long text; on/off forces behaviour. */
  const [ragMode, setRagMode] = useState<'auto' | 'on' | 'off'>('auto')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<SummaryResult | null>(null)
  const [exportBusy, setExportBusy] = useState<'docx' | 'pdf' | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  function documentIdsForRun(): string[] {
    return Array.from(new Set(selectedIds.map((s) => s.trim()).filter(Boolean))).slice(0, MAX_DOCS)
  }

  async function run() {
    const ids = documentIdsForRun()
    if (ids.length === 0) {
      setError('Select at least one document from the Library (or upload first).')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    setExportError(null)
    try {
      const payload: Record<string, unknown> = { document_ids: ids, length }
      if (ragMode === 'on') payload.use_rag = true
      if (ragMode === 'off') payload.use_rag = false
      const res = await apiJson<SummaryResult>('/agents/summarize', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Summarize failed')
    } finally {
      setLoading(false)
    }
  }

  async function exportSummary(format: 'docx' | 'pdf') {
    if (!result) return
    setExportError(null)
    setExportBusy(format)
    try {
      const { blob, filename } = await apiPostBlob('/agents/summarize/export', {
        format,
        summary: result.summary ?? '',
        key_points: result.key_points ?? [],
        action_items: result.action_items ?? [],
        formulas: result.formulas ?? [],
        glossary: result.glossary ?? [],
        source_documents: result.source_documents ?? [],
        total_pages: result.total_pages ?? 0,
        chunk_count: result.chunk_count ?? 0,
        image_notes: result.image_notes ?? [],
        processing_notes: result.processing_notes ?? [],
      })
      triggerDownload(blob, filename)
    } catch (e) {
      setExportError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setExportBusy(null)
    }
  }

  const ids = documentIdsForRun()
  const nSelected = ids.length

  return (
    <div className="studio-route summarize-page dialogue-page">
      <h1 className="page-title">Summarize</h1>
      <p className="page-sub">
        Turn one or more supported files into a structured summary. Large or merged documents can take a minute or
        more while the model works — stay on this page until it finishes. The API needs <code>GROQ_API_KEY</code> in{' '}
        <code>.env</code>.
      </p>

      <div className="dialogue-shell">
        <main className="dialogue-main">
          <section className="dialogue-card dialogue-card--scope" aria-labelledby="summarize-scope-heading">
            <div className="dialogue-card__head">
              <h2 id="summarize-scope-heading" className="dialogue-card__title">
                Scope
              </h2>
              <p className="dialogue-card__lede">
                Limit the run to specific Library documents. The first ticked file is the primary anchor; additional
                ticks merge into one summary (up to {MAX_DOCS} files).
              </p>
            </div>
            <DocPicker
              value={selectedIds}
              onChange={(next) => setSelectedIds(next.slice(0, MAX_DOCS))}
              accept=".pdf,.docx,.pptx,.txt,.md"
              compact
              maxSelection={MAX_DOCS}
              compactHint={SUMMARIZE_SCOPE_HINT}
            />
            {selectedIds.length > 0 && (
              <p className="dialogue-scope-note">
                Primary: <code className="dialogue-code">{selectedIds[0]}</code>
                {selectedIds.length > 1 ? (
                  <span className="dialogue-scope-note__hint">
                    {' '}
                    — Additional files follow in the order you selected them.
                  </span>
                ) : null}
              </p>
            )}
          </section>

          <aside className="dialogue-sidebar" aria-labelledby="summarize-options-heading">
            <h3 id="summarize-options-heading" className="dialogue-sidebar__title">
              Length &amp; input
            </h3>
            <p className="dialogue-sidebar__lede">These apply to the next summary only.</p>

            <div className="dialogue-sidebar__block">
              <span className="summarize-field-label">Summary length</span>
              <div className="dialogue-length summarize-length" role="group" aria-label="Summary length">
                {LENGTH_OPTS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    className={length === opt.id ? 'is-on' : ''}
                    onClick={() => setLength(opt.id)}
                  >
                    {opt.label}
                    <span className="summarize-length-hint">{opt.hint}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="dialogue-sidebar__block">
              <span className="summarize-field-label">Summarization input</span>
              <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--ink-soft)', lineHeight: 1.45 }}>
                <strong>Auto</strong> uses indexed retrieval for several large sources or very long combined text.{' '}
                <strong>Full text</strong> always sends extracted text (may hit size limits).
              </p>
              <div className="dialogue-length summarize-length" role="group" aria-label="Summarization input">
                {RAG_OPTS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    className={ragMode === opt.id ? 'is-on' : ''}
                    onClick={() => setRagMode(opt.id)}
                  >
                    {opt.label}
                    <span className="summarize-length-hint">{opt.hint}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="summarize-stat">
              <span>Documents in this run</span>
              <strong>
                {nSelected} / {MAX_DOCS}
              </strong>
            </div>
          </aside>

          {(result || error) && (
            <section className="dialogue-card dialogue-card--thread" aria-label="Summary output">
              <div className="dialogue-thread__toolbar">
                <span className="dialogue-thread__badge">Summary</span>
                {result ? (
                  <div className="dialogue-thread__export-actions">
                    <button
                      type="button"
                      className="btn btn--primary"
                      disabled={exportBusy !== null}
                      onClick={() => void exportSummary('docx')}
                    >
                      {exportBusy === 'docx' ? 'Preparing…' : 'Word'}
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost"
                      disabled={exportBusy !== null}
                      onClick={() => void exportSummary('pdf')}
                    >
                      {exportBusy === 'pdf' ? 'Preparing…' : 'PDF'}
                    </button>
                  </div>
                ) : null}
              </div>
              <div className="dialogue-thread__body summarize-results__body">
                {error && <div className="error dialogue-thread__error">{error}</div>}
                {result && (
                  <>
                    {exportError && <div className="error" style={{ marginBottom: '1rem' }}>{exportError}</div>}
                    {result.source_documents && result.source_documents.length > 0 && (
                      <p className="summarize-results__sources">
                        <strong style={{ color: 'var(--sea)' }}>Sources</strong> · {result.source_documents.join(' · ')}
                        {typeof result.total_pages === 'number' ? ` · ~${result.total_pages} pages (declared)` : null}
                      </p>
                    )}
                    {result.summary && <p className="summarize-prose">{result.summary}</p>}
                    {result.key_points && result.key_points.length > 0 && (
                      <>
                        <h3>Key points</h3>
                        <ul>
                          {result.key_points.map((k, i) => (
                            <li key={i}>{k}</li>
                          ))}
                        </ul>
                      </>
                    )}
                    {result.action_items && result.action_items.length > 0 && (
                      <>
                        <h3>Action items</h3>
                        <ul>
                          {result.action_items.map((k, i) => (
                            <li key={i}>{k}</li>
                          ))}
                        </ul>
                      </>
                    )}
                    {result.formulas && result.formulas.length > 0 && (
                      <>
                        <h3>Formulas</h3>
                        <ul className="summarize-formulas">
                          {result.formulas.map((f, i) => (
                            <li key={i}>
                              <code>{f}</code>
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                    {result.glossary && result.glossary.length > 0 && (
                      <>
                        <h3>Glossary</h3>
                        <dl>
                          {result.glossary.map((g, i) => (
                            <div key={i}>
                              <dt>{g.term}</dt>
                              <dd>{g.definition}</dd>
                            </div>
                          ))}
                        </dl>
                      </>
                    )}
                    {result.image_notes && result.image_notes.length > 0 && (
                      <div className="summarize-footnote">
                        <strong style={{ color: 'var(--sea)' }}>Image notes</strong>
                        <ul style={{ marginTop: '0.35rem' }}>
                          {result.image_notes.map((n, i) => (
                            <li key={i}>{n}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {result.processing_notes && result.processing_notes.length > 0 && (
                      <p className="summarize-footnote">{result.processing_notes.join(' ')}</p>
                    )}
                  </>
                )}
              </div>
            </section>
          )}

          <section className="dialogue-card dialogue-card--composer" aria-labelledby="summarize-run-heading">
            <h2 id="summarize-run-heading" className="dialogue-composer__label">
              Generate
            </h2>
            <p className="dialogue-card__lede" style={{ margin: '0 0 0.85rem' }}>
              Large merged jobs can take a while — keep this tab open until the summary appears above.
            </p>
            <div className="dialogue-composer__actions dialogue-composer__actions--full-run">
              <button
                type="button"
                className="btn btn--accent summarize-run"
                disabled={loading || nSelected === 0}
                onClick={() => void run()}
              >
                {loading ? 'Summarizing…' : 'Generate summary'}
              </button>
            </div>
          </section>
        </main>
      </div>
    </div>
  )
}
