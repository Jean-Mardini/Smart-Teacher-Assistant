import { useState } from 'react'
import { apiJson } from '../api/client'

type Tab = 'summarize' | 'slides' | 'quiz'

export function StudioPage() {
  const [tab, setTab] = useState<Tab>('summarize')
  const [documentId, setDocumentId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [out, setOut] = useState<unknown>(null)

  const [nSlides, setNSlides] = useState(5)
  const [nQuiz, setNQuiz] = useState(5)
  const [difficulty, setDifficulty] = useState('medium')
  const [length, setLength] = useState('medium')

  async function run() {
    setLoading(true)
    setError(null)
    setOut(null)
    const id = documentId.trim()
    if (!id) {
      setError('Enter a document_id from the Library.')
      setLoading(false)
      return
    }
    try {
      if (tab === 'summarize') {
        const res = await apiJson('/agents/summarize', {
          method: 'POST',
          body: JSON.stringify({ document_ids: [id], length }),
        })
        setOut(res)
      } else if (tab === 'slides') {
        const res = await apiJson('/agents/slides', {
          method: 'POST',
          body: JSON.stringify({
            document_id: id,
            n_slides: nSlides,
            generate_images: false,
            max_generated_images: 0,
          }),
        })
        setOut(res)
      } else {
        const res = await apiJson('/agents/quiz', {
          method: 'POST',
          body: JSON.stringify({
            document_id: id,
            n_questions: nQuiz,
            difficulty,
          }),
        })
        setOut(res)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <h1 className="page-title">Studio</h1>
      <p className="page-sub">
        Summaries, slide outlines, and quizzes are generated from one indexed document. Paste its <code>document_id</code>{' '}
        from Library.
      </p>
      {error && <div className="error">{error}</div>}
      <div className="panel">
        <div className="field">
          <label htmlFor="doc">Document ID</label>
          <input id="doc" value={documentId} onChange={(e) => setDocumentId(e.target.value)} placeholder="e.g. my_lesson" />
        </div>
        <div className="tabs">
          {(
            [
              ['summarize', 'Summarize'],
              ['slides', 'Slides'],
              ['quiz', 'Quiz'],
            ] as const
          ).map(([k, label]) => (
            <button key={k} type="button" className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>
              {label}
            </button>
          ))}
        </div>
        {tab === 'summarize' && (
          <div className="field">
            <label htmlFor="slen">Length</label>
            <select id="slen" value={length} onChange={(e) => setLength(e.target.value)}>
              <option value="short">Short</option>
              <option value="medium">Medium</option>
              <option value="long">Long</option>
            </select>
          </div>
        )}
        {tab === 'slides' && (
          <div className="field">
            <label htmlFor="ns">Number of slides</label>
            <input
              id="ns"
              type="number"
              min={1}
              max={20}
              value={nSlides}
              onChange={(e) => setNSlides(Number(e.target.value))}
            />
          </div>
        )}
        {tab === 'quiz' && (
          <>
            <div className="field">
              <label htmlFor="nq">Questions</label>
              <input
                id="nq"
                type="number"
                min={1}
                max={20}
                value={nQuiz}
                onChange={(e) => setNQuiz(Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="diff">Difficulty</label>
              <select id="diff" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </div>
          </>
        )}
        <button type="button" className="btn btn--accent" disabled={loading} onClick={() => void run()}>
          {loading ? 'Creating…' : 'Generate'}
        </button>
      </div>
      {out !== null && (
        <div className="panel" style={{ marginTop: '1.25rem' }}>
          <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.1rem' }}>Result</h2>
          <pre className="pre-json">{JSON.stringify(out, null, 2)}</pre>
        </div>
      )}
    </>
  )
}
