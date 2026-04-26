import { useState } from 'react'
import { DocPicker } from '../components/DocPicker'
import { apiJson } from '../api/client'

type QuizQuestion = {
  type?: string
  question?: string
  options?: string[]
  answer_index?: number | null
  answer_text?: string | null
  explanation?: string
}

type QuizResult = {
  quiz?: QuizQuestion[]
}

export function QuizPage() {
  const [docIds, setDocIds] = useState<string[]>([])
  const [nQuestions, setNQuestions] = useState(5)
  const [difficulty, setDifficulty] = useState('medium')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<QuizResult | null>(null)

  async function run() {
    if (!docIds.length) {
      setError('Choose at least one document above.')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await apiJson<QuizResult>('/agents/quiz', {
        method: 'POST',
        body: JSON.stringify({
          document_id: docIds[0],
          n_questions: nQuestions,
          difficulty,
        }),
      }, 120_000)
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <h1 className="page-title">Quiz</h1>
      <p className="page-sub">Generate quiz questions from one document.</p>

      <DocPicker value={docIds} onChange={setDocIds} accept=".pdf,.docx,.pptx,.txt,.md" />

      <div className="panel">
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.05rem' }}>2. Options</h2>
        <div className="field">
          <label htmlFor="nq">Number of questions</label>
          <input
            id="nq"
            type="number"
            min={1}
            max={20}
            value={nQuestions}
            onChange={(e) => setNQuestions(Number(e.target.value))}
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
        <button type="button" className="btn btn--accent" disabled={loading || !docIds.length} onClick={() => void run()}>
          {loading ? 'Generating…' : 'Generate quiz'}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {result?.quiz && result.quiz.length > 0 && (
        <div className="panel" style={{ marginTop: '1.25rem' }}>
          <h2 style={{ margin: '0 0 1rem', fontSize: '1.15rem' }}>Questions</h2>
          {result.quiz.map((q, idx) => (
            <div
              key={idx}
              style={{
                marginBottom: '1.25rem',
                paddingBottom: '1rem',
                borderBottom: idx < result.quiz!.length - 1 ? '1px solid var(--line)' : undefined,
              }}
            >
              <p style={{ fontWeight: 600, margin: '0 0 0.5rem' }}>
                {idx + 1}. {q.question}
              </p>
              {q.options && q.options.length > 0 && (
                <ol style={{ margin: '0.25rem 0' }}>
                  {q.options.map((o, i) => (
                    <li key={i}>{o}</li>
                  ))}
                </ol>
              )}
              {q.explanation && (
                <p style={{ fontSize: '0.9rem', color: 'var(--ink-soft)' }}>{q.explanation}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  )
}
