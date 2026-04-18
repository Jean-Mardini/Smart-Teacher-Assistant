import { useState } from 'react'
import { DocPicker } from '../components/DocPicker'
import { apiJson } from '../api/client'

type SummaryResult = {
  summary?: string
  key_points?: string[]
  action_items?: string[]
  processing_notes?: string[]
}

export function SummarizePage() {
  const [docId, setDocId] = useState('')
  const [length, setLength] = useState('medium')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<SummaryResult | null>(null)

  async function run() {
    const id = docId.trim()
    if (!id) {
      setError('Choose a document above.')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await apiJson<SummaryResult>('/agents/summarize', {
        method: 'POST',
        body: JSON.stringify({ document_ids: [id], length }),
      })
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Summarize failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <h1 className="page-title">Summarize</h1>
      <p className="page-sub">
        Turn a PDF, Word file, or other supported text into a structured summary. Requires <code>GROQ_API_KEY</code> on
        the API.
      </p>

      <DocPicker value={docId} onChange={setDocId} accept=".pdf,.docx,.pptx,.txt,.md" />

      <div className="panel">
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.05rem' }}>2. Options</h2>
        <div className="field">
          <label htmlFor="len">Length</label>
          <select id="len" value={length} onChange={(e) => setLength(e.target.value)}>
            <option value="short">Short</option>
            <option value="medium">Medium</option>
            <option value="long">Long</option>
          </select>
        </div>
        <button type="button" className="btn btn--accent" disabled={loading || !docId} onClick={() => void run()}>
          {loading ? 'Summarizing…' : 'Generate summary'}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {result && (
        <div className="panel" style={{ marginTop: '1.25rem' }}>
          <h2 style={{ margin: '0 0 1rem', fontSize: '1.15rem' }}>Summary</h2>
          {result.summary && (
            <p style={{ lineHeight: 1.65, whiteSpace: 'pre-wrap' }}>{result.summary}</p>
          )}
          {result.key_points && result.key_points.length > 0 && (
            <>
              <h3 style={{ fontSize: '1rem', marginTop: '1.25rem' }}>Key points</h3>
              <ul style={{ lineHeight: 1.5 }}>
                {result.key_points.map((k, i) => (
                  <li key={i}>{k}</li>
                ))}
              </ul>
            </>
          )}
          {result.action_items && result.action_items.length > 0 && (
            <>
              <h3 style={{ fontSize: '1rem', marginTop: '1rem' }}>Action items</h3>
              <ul>
                {result.action_items.map((k, i) => (
                  <li key={i}>{k}</li>
                ))}
              </ul>
            </>
          )}
          {result.processing_notes && result.processing_notes.length > 0 && (
            <p style={{ fontSize: '0.85rem', color: 'var(--ink-soft)', marginTop: '1rem' }}>
              {result.processing_notes.join(' ')}
            </p>
          )}
        </div>
      )}
    </>
  )
}
