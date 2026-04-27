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
    <div className="studio-route summarize-page dialogue-page">
      <h1 className="page-title">Dialogue</h1>
      <p className="page-sub">
        Ask questions grounded in your <strong>Library</strong> index. Chunk size and overlap are configured there
        (rebuild index when you change them). Retrieval can use image captions and text chunks when present.
      </p>

      <div className="dialogue-shell">
        <main className="dialogue-main">
          <section className="dialogue-card dialogue-card--scope" aria-labelledby="dialogue-scope-heading">
            <div className="dialogue-card__head">
              <h2 id="dialogue-scope-heading" className="dialogue-card__title">
                Scope
              </h2>
              <p className="dialogue-card__lede">
                Limit retrieval to specific shelf documents, or leave empty and use optional IDs for a narrower slice.
              </p>
            </div>
            <DocPicker value={pickIds} onChange={setPickIds} accept=".pdf,.docx,.pptx,.txt,.md" compact />
            {pickIds.length > 0 ? (
              <p className="dialogue-scope-note">
                Active:{' '}
                <code className="dialogue-code">{pickIds.join(', ')}</code>
                <span className="dialogue-scope-note__hint">
                  {' '}
                  — Uncheck documents or use <strong>Clear</strong> to search more broadly; optional IDs below.
                </span>
              </p>
            ) : (
              <div className="field dialogue-field-tight">
                <label htmlFor="dialogue-ids">Document IDs (optional)</label>
                <input
                  id="dialogue-ids"
                  value={ids}
                  onChange={(e) => setIds(e.target.value)}
                  placeholder="From Library, comma-separated"
                  className="dialogue-input-mono"
                />
                <p className="dialogue-field-hint">Partial ids match when they resolve to exactly one document.</p>
              </div>
            )}
          </section>

          <aside className="dialogue-sidebar" aria-labelledby="dialogue-sidebar-heading">
            <h3 id="dialogue-sidebar-heading" className="dialogue-sidebar__title">
              Retrieval & tone
            </h3>
            <p className="dialogue-sidebar__lede">These apply to the next answer only.</p>

            <div className="dialogue-sidebar__block">
              <span className="summarize-field-label">Answer length</span>
              <div className="dialogue-length summarize-length" role="group" aria-label="Answer length">
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

            <div className="dialogue-sidebar__grid">
              <div className="field dialogue-field-tight">
                <label htmlFor="dialogue-tk">Chunks (top_k)</label>
                <input
                  id="dialogue-tk"
                  type="number"
                  min={1}
                  max={10}
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                />
              </div>
              <div className="field dialogue-field-tight">
                <label htmlFor="dialogue-temp">Temperature</label>
                <input
                  id="dialogue-temp"
                  type="number"
                  min={0}
                  max={1.5}
                  step={0.1}
                  value={temperature}
                  onChange={(e) => setTemperature(Number(e.target.value))}
                />
              </div>
            </div>
          </aside>

          {(result || error) && (
            <section className="dialogue-card dialogue-card--thread" aria-label="Assistant reply">
              <div className="dialogue-thread__toolbar">
                <span className="dialogue-thread__badge">Reply</span>
              </div>
              <div className="dialogue-thread__body">
                {error && <div className="error dialogue-thread__error">{error}</div>}
                {result && (
                  <>
                    <div className="dialogue-answer summarize-prose">{result.answer}</div>
                    {result.sources && result.sources.length > 0 && (
                      <div className="dialogue-sources">
                        <h3 className="dialogue-sources__title">Sources</h3>
                        <ul className="dialogue-sources__list">
                          {result.sources.map((s, i) => (
                            <li key={i}>
                              {s.document_title}
                              {s.section_heading ? ` — ${s.section_heading}` : ''}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {result.processing_notes && result.processing_notes.length > 0 && (
                      <p className="dialogue-footnote summarize-footnote">{result.processing_notes.join(' ')}</p>
                    )}
                  </>
                )}
              </div>
            </section>
          )}

          <section className="dialogue-card dialogue-card--composer" aria-labelledby="dialogue-composer-heading">
            <label id="dialogue-composer-heading" className="dialogue-composer__label" htmlFor="dialogue-q">
              Your message
            </label>
            <textarea
              id="dialogue-q"
              className="dialogue-composer__textarea"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. What should students take away from the unit on…"
              rows={4}
            />
            <div className="dialogue-composer__actions">
              <button
                type="button"
                className="btn btn--primary dialogue-send"
                disabled={loading || !question.trim()}
                onClick={() => void send()}
              >
                {loading ? 'Sending…' : 'Send'}
              </button>
            </div>
          </section>
        </main>
      </div>
    </div>
  )
}
