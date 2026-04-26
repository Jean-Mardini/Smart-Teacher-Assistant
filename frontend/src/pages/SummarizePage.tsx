import { useCallback, useEffect, useState } from 'react'
import { DocPicker } from '../components/DocPicker'
import type { DocRow } from '../components/DocPicker'
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

/** Summarization runs multiple LLM calls; default apiJson 12s is too short. */
const SUMMARIZE_TIMEOUT_MS = 300_000
const SUMMARIZE_EXPORT_TIMEOUT_MS = 120_000

const LENGTH_OPTS = [
  { id: 'short', label: 'Short', hint: 'Brief overview' },
  { id: 'medium', label: 'Medium', hint: 'Balanced depth' },
  { id: 'long', label: 'Long', hint: 'More detail' },
] as const

export function SummarizePage() {
  const [docId, setDocId] = useState('')
  const [extraIds, setExtraIds] = useState<Set<string>>(() => new Set())
  const [shelf, setShelf] = useState<DocRow[]>([])
  const [length, setLength] = useState('medium')
  /** Auto: server uses RAG for multi-doc / very long text; on/off forces behaviour. */
  const [ragMode, setRagMode] = useState<'auto' | 'on' | 'off'>('auto')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<SummaryResult | null>(null)
  const [exportBusy, setExportBusy] = useState<'docx' | 'pdf' | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  const refreshShelf = useCallback(async () => {
    try {
      const list = await apiJson<DocRow[]>('/documents/local')
      setShelf(list)
    } catch {
      setShelf([])
    }
  }, [])

  useEffect(() => {
    void refreshShelf()
  }, [refreshShelf])

  function toggleExtra(id: string) {
    if (!docId || id === docId) return
    setExtraIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else if (next.size < MAX_DOCS - 1) next.add(id)
      return next
    })
  }

  function resolvedIds(): string[] {
    const primary = docId.trim()
    if (!primary) return []
    const rest = shelf.map((d) => d.document_id).filter((id) => id !== primary && extraIds.has(id))
    const merged = [primary, ...rest]
    return Array.from(new Set(merged)).slice(0, MAX_DOCS)
  }

  async function run() {
    const ids = resolvedIds()
    if (ids.length === 0) {
      setError('Choose a primary document first. You can add more shelf files after that.')
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
      const res = await apiJson<SummaryResult>(
        '/agents/summarize',
        {
          method: 'POST',
          body: JSON.stringify(payload),
        },
        SUMMARIZE_TIMEOUT_MS,
      )
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
      const { blob, filename } = await apiPostBlob(
        '/agents/summarize/export',
        {
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
        },
        SUMMARIZE_EXPORT_TIMEOUT_MS,
      )
      triggerDownload(blob, filename)
    } catch (e) {
      setExportError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setExportBusy(null)
    }
  }

  const nSelected = resolvedIds().length

  return (
    <div className="studio-route summarize-page">
      <h1 className="page-title">Summarize</h1>
      <p className="page-sub">
        Turn one or more supported files into a structured summary. Large or merged documents can take a minute or
        more while the model works — stay on this page until it finishes. The API needs <code>GROQ_API_KEY</code> in{' '}
        <code>.env</code>.
      </p>

      <div className="studio-sheet">
        <div className="studio-sheet__grid">
          <div className="studio-main">
          <div className="studio-panel">
            <h2>Primary document</h2>
            <p className="summarize-lede">
              Upload in the <strong>Library</strong> if needed, then choose the file that anchors this summary.
            </p>
            <DocPicker
              value={docId ? [docId] : []}
              onChange={(ids) => {
                const id = ids[0] ?? ''
                setDocId(id)
                setExtraIds((prev) => {
                  if (!id) return new Set()
                  const next = new Set(prev)
                  next.delete(id)
                  return next
                })
              }}
              accept=".pdf,.docx,.pptx,.txt,.md"
            />
          </div>

          <div className="studio-panel">
            <h2>Merge more from the shelf</h2>
            <p className="summarize-lede" style={{ marginBottom: '0.65rem' }}>
              Optional: include up to {MAX_DOCS - 1} additional files in one run.
            </p>
            <button type="button" className="btn btn--ghost" onClick={() => void refreshShelf()}>
              Refresh shelf
            </button>
            {shelf.length === 0 ? (
              <p style={{ color: 'var(--ink-soft)', margin: 0 }}>No documents on the shelf yet.</p>
            ) : (
              <div className="summarize-shelf">
                <ul>
                  {shelf.map((d) => {
                    const isPrimary = d.document_id === docId
                    const checked = isPrimary || extraIds.has(d.document_id)
                    const disabled = isPrimary ? true : !docId
                    return (
                      <li key={d.document_id}>
                        <label>
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={disabled}
                            onChange={() => {
                              if (isPrimary) return
                              toggleExtra(d.document_id)
                            }}
                          />
                          <span className="summarize-shelf__meta">
                            <strong>{d.title}</strong>{' '}
                            <code>{d.document_id}</code>
                            {isPrimary ? (
                              <span style={{ color: 'var(--ink-soft)', fontSize: '0.86rem' }}> — primary</span>
                            ) : null}
                          </span>
                        </label>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}
          </div>
          </div>

        <aside className="studio-aside">
          <div>
            <span className="summarize-field-label">Summary length</span>
            <div className="summarize-length" role="group" aria-label="Summary length">
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

          <div style={{ marginTop: '1rem' }}>
            <span className="summarize-field-label">Summarization input</span>
            <p style={{ margin: '0.35rem 0 0.5rem', fontSize: '0.86rem', color: 'var(--ink-soft)' }}>
              <strong>Auto</strong> uses indexed retrieval for several large sources or very long combined text.{' '}
              <strong>Full text</strong> always sends extracted text (may hit size limits).
            </p>
            <select
              id="summarize-rag"
              className="field"
              style={{ width: '100%', maxWidth: '16rem' }}
              value={ragMode}
              onChange={(e) => setRagMode(e.target.value as 'auto' | 'on' | 'off')}
            >
              <option value="auto">Auto (recommended)</option>
              <option value="on">RAG (retrieved passages)</option>
              <option value="off">Full extracted text only</option>
            </select>
          </div>

          <div className="summarize-stat">
            <span>Documents in this run</span>
            <strong>
              {nSelected} / {MAX_DOCS}
            </strong>
          </div>

          <button
            type="button"
            className="btn btn--accent summarize-run"
            disabled={loading || !docId.trim()}
            onClick={() => void run()}
          >
            {loading ? 'Summarizing…' : 'Generate summary'}
          </button>
        </aside>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      {result && (
        <div className="studio-sheet studio-sheet--spaced studio-sheet--flat studio-results">
          <div className="studio-results__head studio-results__head--row">
            <h2>Summary output</h2>
            <div className="studio-results__actions">
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
          </div>
          <div className="studio-results__body summarize-results__body">
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
          </div>
        </div>
      )}
    </div>
  )
}
