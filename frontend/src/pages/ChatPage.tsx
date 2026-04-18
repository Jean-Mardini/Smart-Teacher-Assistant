import { useState } from 'react'
import { apiJson } from '../api/client'

type ChatResponse = {
  answer: string
  sources: { document_title: string; section_heading?: string | null; page?: string | null }[]
  processing_notes: string[]
}

export function ChatPage() {
  const [question, setQuestion] = useState('')
  const [ids, setIds] = useState('')
  const [length, setLength] = useState('medium')
  const [result, setResult] = useState<ChatResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function send() {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const document_ids = ids
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      const res = await apiJson<ChatResponse>('/chat', {
        method: 'POST',
        body: JSON.stringify({
          question,
          length,
          top_k: 4,
          temperature: 0.2,
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
    <>
      <h1 className="page-title">Dialogue</h1>
      <p className="page-sub">
        Questions grounded in your indexed library. Leave document IDs empty to search across everything, or restrict to
        comma-separated IDs from the Library.
      </p>
      {error && <div className="error">{error}</div>}
      <div className="panel">
        <div className="field">
          <label htmlFor="q">Your question</label>
          <textarea id="q" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What should students take away from…" rows={4} />
        </div>
        <div className="field">
          <label htmlFor="ids">Document IDs (optional)</label>
          <input id="ids" value={ids} onChange={(e) => setIds(e.target.value)} placeholder="e.g. my_doc, chapter_2" />
        </div>
        <div className="field">
          <label htmlFor="len">Answer length</label>
          <select id="len" value={length} onChange={(e) => setLength(e.target.value)}>
            <option value="short">Short</option>
            <option value="medium">Medium</option>
            <option value="long">Long</option>
          </select>
        </div>
        <button type="button" className="btn btn--primary" disabled={loading || !question.trim()} onClick={() => void send()}>
          {loading ? 'Thinking…' : 'Ask'}
        </button>
      </div>
      {result && (
        <div className="panel" style={{ marginTop: '1.25rem' }}>
          <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.2rem' }}>Reply</h2>
          <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{result.answer}</p>
          {result.sources?.length > 0 && (
            <>
              <h3 style={{ fontSize: '1rem', marginTop: '1.25rem' }}>Sources</h3>
              <ul style={{ paddingLeft: '1.2rem', color: 'var(--ink-soft)' }}>
                {result.sources.map((s, i) => (
                  <li key={i}>
                    {s.document_title}
                    {s.section_heading ? ` — ${s.section_heading}` : ''}
                  </li>
                ))}
              </ul>
            </>
          )}
          {result.processing_notes?.length > 0 && (
            <p style={{ fontSize: '0.85rem', color: 'var(--ink-soft)', marginTop: '1rem' }}>
              {result.processing_notes.join(' ')}
            </p>
          )}
        </div>
      )}
    </>
  )
}
