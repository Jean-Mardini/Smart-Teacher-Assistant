import { useState } from 'react'
import { DocPicker } from '../components/DocPicker'
import { apiJson } from '../api/client'

type ChatResponse = {
  answer: string
  sources: { document_title: string; section_heading?: string | null; page?: string | null }[]
  processing_notes: string[]
}

const LENGTH_OPTS = [
  { id: 'short', label: 'Short', hint: 'Brief reply' },
  { id: 'medium', label: 'Medium', hint: 'Balanced' },
  { id: 'long', label: 'Long', hint: 'More detail' },
] as const

export function ChatPage() {
  const [question, setQuestion] = useState('')
  const [ids, setIds] = useState('')
  const [pickIds, setPickIds] = useState<string[]>([])
  const [length, setLength] = useState('medium')
  const [topK, setTopK] = useState(4)
  const [temperature, setTemperature] = useState(0.2)
  const [result, setResult] = useState<ChatResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function send() {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const fromInput = ids
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      const document_ids = pickIds.length > 0 ? pickIds : fromInput
      const res = await apiJson<ChatResponse>('/chat', {
        method: 'POST',
        body: JSON.stringify({
          question,
          length,
          top_k: Math.min(10, Math.max(1, Math.round(topK))),
          temperature: Math.min(1.5, Math.max(0, temperature)),
          document_ids,
        }),
      })
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="studio-route summarize-page">
      <h1 className="page-title">Dialogue</h1>
      <p className="page-sub">
        Uploads index automatically for search. <strong>Chunk size / overlap</strong> for indexed passages are set on{' '}
        <strong>Library</strong> via <strong>Rebuild search index</strong> (optional JSON body in API{' '}
        <code>/rag/reindex</code>). Retrieval uses image captions and text chunks when present.
      </p>

      <div className="studio-sheet">
        <div className="studio-sheet__grid">
          <div className="studio-main">
          <div className="studio-panel">
            <h2>Document</h2>
            <p className="summarize-lede">
              Choose an active document to scope retrieval, or leave unset and use document IDs in the question panel.
            </p>
            <DocPicker value={pickIds} onChange={setPickIds} accept=".pdf,.docx,.pptx,.txt,.md" />
          </div>

          <div className="studio-panel">
            <h2>Your question</h2>
            <p className="summarize-lede">
              Ask about material in the index. Tune retrieval and answer length in the column on the right.
            </p>
            <div className="field" style={{ marginBottom: '1rem' }}>
              <label htmlFor="q">Message</label>
              <textarea
                id="q"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="What should students take away from…"
                rows={5}
              />
            </div>
            {pickIds.length > 0 ? (
              <p style={{ margin: '0 0 0.75rem', fontSize: '0.9rem', color: 'var(--ink-soft)' }}>
                Scoped to <code style={{ fontSize: '0.88em' }}>{pickIds.join(', ')}</code>. To search the whole library or
                combine IDs, clear the library selection (Ctrl/Cmd-click to deselect).
              </p>
            ) : (
              <div className="field" style={{ marginBottom: 0 }}>
                <label htmlFor="ids">Document IDs (optional)</label>
                <input
                  id="ids"
                  value={ids}
                  onChange={(e) => setIds(e.target.value)}
                  placeholder="Full ids from Library, comma-separated"
                  style={{ fontFamily: 'ui-monospace, monospace' }}
                />
                <p style={{ margin: '0.35rem 0 0', fontSize: '0.85rem', color: 'var(--ink-soft)' }}>
                  Partial ids are expanded when they match exactly one shelf document.
                </p>
              </div>
            )}
          </div>
          </div>

        <aside className="studio-aside">
          <div>
            <span className="summarize-field-label">Answer length</span>
            <div className="summarize-length" role="group" aria-label="Answer length">
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

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '0.75rem',
            }}
          >
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor="tk">top_k</label>
              <input
                id="tk"
                type="number"
                min={1}
                max={10}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
              />
            </div>
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor="temp">Temperature</label>
              <input
                id="temp"
                type="number"
                min={0}
                max={1.5}
                step={0.1}
                value={temperature}
                onChange={(e) => setTemperature(Number(e.target.value))}
              />
            </div>
          </div>

          <button
            type="button"
            className="btn btn--accent summarize-run"
            disabled={loading || !question.trim()}
            onClick={() => void send()}
          >
            {loading ? 'Thinking…' : 'Ask'}
          </button>
        </aside>
        </div>
      </div>

      {error && <div className="error" style={{ whiteSpace: 'pre-wrap' }}>{error}</div>}

      {result && (
        <div className="studio-sheet studio-sheet--spaced studio-sheet--flat studio-results">
          <div className="studio-results__head">
            <h2>Reply</h2>
          </div>
          <div className="studio-results__body summarize-results__body">
            <p className="summarize-prose" style={{ marginTop: 0 }}>
              {result.answer}
            </p>
            {result.sources && result.sources.length > 0 && (
              <>
                <h3>Sources</h3>
                <ul>
                  {result.sources.map((s, i) => (
                    <li key={i} style={{ color: 'var(--ink-soft)' }}>
                      {s.document_title}
                      {s.section_heading ? ` — ${s.section_heading}` : ''}
                    </li>
                  ))}
                </ul>
              </>
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
