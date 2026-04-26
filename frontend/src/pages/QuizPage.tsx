import { useState } from 'react'
import { DocPicker } from '../components/DocPicker'
import { apiJson, apiPostBlob, triggerDownload } from '../api/client'

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

const DIFFICULTY_LEVELS = [
  { id: 'easy', label: 'Easy', hint: 'Recall & definitions' },
  { id: 'medium', label: 'Medium', hint: 'Typical classroom mix' },
  { id: 'hard', label: 'Hard', hint: 'Synthesis & edge cases' },
] as const

function clampInt(n: number, lo: number, hi: number) {
  if (!Number.isFinite(n)) return lo
  return Math.min(hi, Math.max(lo, Math.floor(n)))
}

export function QuizPage() {
  const [docId, setDocId] = useState('')
  const [nMcq, setNMcq] = useState(3)
  const [nShort, setNShort] = useState(2)
  const [difficulty, setDifficulty] = useState('medium')
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<QuizResult | null>(null)

  const quizTotal = nMcq + nShort

  function setNMcqSafe(raw: number) {
    const v = clampInt(raw, 0, 20)
    setNMcq(v)
    if (v + nShort > 25) setNShort(Math.max(0, 25 - v))
  }

  function setNShortSafe(raw: number) {
    const v = clampInt(raw, 0, 20)
    setNShort(v)
    if (nMcq + v > 25) setNMcq(Math.max(0, 25 - v))
  }

  function quizBody() {
    return {
      document_id: docId.trim(),
      n_mcq: nMcq,
      n_short_answer: nShort,
      difficulty,
    }
  }

  async function exportMoodle() {
    const id = docId.trim()
    if (!id) {
      setError('Choose a document above.')
      return
    }
    if (quizTotal < 1 || quizTotal > 25) {
      setError('Set MCQ and short-answer counts (1–25 total) before export.')
      return
    }
    setExporting(true)
    setError(null)
    try {
      const { blob, filename } = await apiPostBlob('/agents/quiz/export/moodle-xml', quizBody())
      triggerDownload(blob, filename.endsWith('.xml') ? filename : `${filename}_quiz_moodle.xml`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  async function run() {
    const id = docId.trim()
    if (!id) {
      setError('Choose a document above.')
      return
    }
    if (quizTotal < 1) {
      setError('Choose at least one MCQ or short-answer question.')
      return
    }
    if (quizTotal > 25) {
      setError('At most 25 questions total (MCQ + short answer).')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await apiJson<QuizResult>('/agents/quiz', {
        method: 'POST',
        body: JSON.stringify({
          document_id: id,
          n_mcq: nMcq,
          n_short_answer: nShort,
          difficulty,
        }),
      })
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="studio-route summarize-page">
      <h1 className="page-title">Quiz</h1>
      <p className="page-sub">
        Generate quiz questions from one document. Export the same quiz to <strong>Moodle XML</strong> for import into
        Moodle (multichoice + short answer).
      </p>

      <div className="studio-sheet">
        <div className="studio-sheet__grid">
          <div className="studio-main">
          <div className="studio-panel">
            <h2>Document</h2>
            <p className="summarize-lede">
              Upload in the <strong>Library</strong> if needed, then pick the file to build the quiz from.
            </p>
            <DocPicker value={docId} onChange={setDocId} accept=".pdf,.docx,.pptx,.txt,.md" />
          </div>

          <div className="studio-panel">
            <h2>Question counts</h2>
            <p className="summarize-lede">
              Set how many multiple-choice vs short-answer items you want (max <strong>25</strong> combined).
            </p>

            <div
              style={{
                display: 'grid',
                gap: '0.85rem',
                gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 220px), 1fr))',
                marginBottom: '0.85rem',
              }}
            >
              <div
                className="field"
                style={{
                  marginBottom: 0,
                  padding: '0.75rem 0.8rem',
                  borderRadius: '14px',
                  background: '#fff',
                  border: '1px solid var(--line)',
                }}
              >
                <label htmlFor="n-mcq">Multiple choice (MCQ)</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.65rem' }}>
                  <div
                    style={{
                      minWidth: '2.75rem',
                      height: '2.75rem',
                      borderRadius: '12px',
                      background: '#f4f3f0',
                      border: '1px solid var(--line)',
                      display: 'grid',
                      placeItems: 'center',
                      fontFamily: 'var(--font-display)',
                      fontSize: '1.1rem',
                      fontWeight: 700,
                      color: 'var(--ink)',
                    }}
                    aria-hidden
                  >
                    {nMcq}
                  </div>
                  <div style={{ flex: '1 1 140px', minWidth: 0 }}>
                    <input
                      id="n-mcq-range"
                      type="range"
                      min={0}
                      max={20}
                      value={nMcq}
                      onChange={(e) => setNMcqSafe(Number(e.target.value))}
                      aria-label="MCQ count"
                      style={{ width: '100%', accentColor: '#5c6670' }}
                    />
                  </div>
                  <input
                    id="n-mcq"
                    type="number"
                    min={0}
                    max={20}
                    value={nMcq}
                    onChange={(e) => setNMcqSafe(Number(e.target.value))}
                    aria-label="MCQ count exact"
                    style={{ width: '3.75rem' }}
                  />
                </div>
              </div>

              <div
                className="field"
                style={{
                  marginBottom: 0,
                  padding: '0.75rem 0.8rem',
                  borderRadius: '14px',
                  background: '#fff',
                  border: '1px solid var(--line)',
                }}
              >
                <label htmlFor="n-short">Short answer (sentence)</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.65rem' }}>
                  <div
                    style={{
                      minWidth: '2.75rem',
                      height: '2.75rem',
                      borderRadius: '12px',
                      background: '#f4f3f0',
                      border: '1px solid var(--line)',
                      display: 'grid',
                      placeItems: 'center',
                      fontFamily: 'var(--font-display)',
                      fontSize: '1.1rem',
                      fontWeight: 700,
                      color: 'var(--ink)',
                    }}
                    aria-hidden
                  >
                    {nShort}
                  </div>
                  <div style={{ flex: '1 1 140px', minWidth: 0 }}>
                    <input
                      id="n-short-range"
                      type="range"
                      min={0}
                      max={20}
                      value={nShort}
                      onChange={(e) => setNShortSafe(Number(e.target.value))}
                      aria-label="Short answer count"
                      style={{ width: '100%', accentColor: '#5c6670' }}
                    />
                  </div>
                  <input
                    id="n-short"
                    type="number"
                    min={0}
                    max={20}
                    value={nShort}
                    onChange={(e) => setNShortSafe(Number(e.target.value))}
                    aria-label="Short answer count exact"
                    style={{ width: '3.75rem' }}
                  />
                </div>
              </div>
            </div>

            <p
              style={{
                margin: 0,
                fontSize: '0.8rem',
                color: quizTotal > 25 ? '#b45309' : 'var(--ink-soft)',
              }}
            >
              Total: <strong>{quizTotal}</strong> / 25
              {quizTotal < 1 ? ' — pick at least one.' : null}
              {quizTotal > 25 ? ' — reduce counts (sliders cap automatically).' : null}
            </p>
          </div>
          </div>

        <aside className="studio-aside">
          <div>
            <span className="summarize-field-label">Question mix</span>
            <div
              style={{
                height: '10px',
                borderRadius: '99px',
                overflow: 'hidden',
                display: 'flex',
                opacity: quizTotal > 0 ? 1 : 0.45,
                background: '#ecebe8',
              }}
            >
              <div
                style={{
                  width: quizTotal > 0 ? `${(nMcq / quizTotal) * 100}%` : '50%',
                  background: '#5c6670',
                  transition: 'width 0.2s ease',
                }}
              />
              <div style={{ flex: 1, background: '#d9d7d2' }} />
            </div>
            <p style={{ margin: '0.45rem 0 0', fontSize: '0.8rem', color: 'var(--ink-soft)' }}>
              <strong style={{ color: 'var(--ink)' }}>{nMcq}</strong> MCQ ·{' '}
              <strong style={{ color: 'var(--ink)' }}>{nShort}</strong> short
            </p>
          </div>

          <div className="summarize-stat">
            <span>Questions in this run</span>
            <strong>
              {quizTotal} / 25
            </strong>
          </div>

          <div>
            <span className="summarize-field-label">Difficulty</span>
            <div className="summarize-length" role="group" aria-label="Difficulty">
              {DIFFICULTY_LEVELS.map((lvl) => (
                <button
                  key={lvl.id}
                  type="button"
                  className={difficulty === lvl.id ? 'is-on' : ''}
                  onClick={() => setDifficulty(lvl.id)}
                >
                  {lvl.label}
                  <span className="summarize-length-hint">{lvl.hint}</span>
                </button>
              ))}
            </div>
          </div>

          <button
            type="button"
            className="btn btn--accent summarize-run"
            disabled={loading || !docId.trim() || quizTotal < 1 || quizTotal > 25}
            onClick={() => void run()}
          >
            {loading ? 'Generating…' : 'Generate quiz'}
          </button>
          <button
            type="button"
            className="btn btn--ghost summarize-run"
            disabled={exporting || !docId.trim() || quizTotal < 1 || quizTotal > 25}
            onClick={() => void exportMoodle()}
          >
            {exporting ? 'Exporting…' : 'Download Moodle XML'}
          </button>
        </aside>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      {result?.quiz && result.quiz.length > 0 && (
        <div className="studio-sheet studio-sheet--spaced studio-sheet--flat studio-results">
          <div className="studio-results__head">
            <h2>Questions</h2>
          </div>
          <div className="studio-results__body summarize-results__body">
            <div
              style={{
                display: 'grid',
                gap: '0.85rem',
                gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 280px), 1fr))',
              }}
            >
              {result.quiz.map((q, idx) => {
                const isMcq = q.type === 'mcq'
                return (
                  <div
                    key={idx}
                    style={{
                      position: 'relative',
                      padding: '0.85rem 1rem 0.95rem 1rem',
                      borderRadius: '14px',
                      border: '1px solid var(--line)',
                      borderLeft: `4px solid ${isMcq ? '#8a9199' : '#b5bcc4'}`,
                      background: '#fff',
                      boxShadow: '0 2px 12px rgba(21, 36, 51, 0.04)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.45rem', flexWrap: 'wrap' }}>
                      <span
                        style={{
                          fontSize: '0.7rem',
                          fontWeight: 700,
                          letterSpacing: '0.06em',
                          textTransform: 'uppercase',
                          color: 'var(--ink-soft)',
                          background: '#f0efec',
                          padding: '0.2rem 0.45rem',
                          borderRadius: '6px',
                        }}
                      >
                        Q{idx + 1}
                      </span>
                      {q.type ? (
                        <span
                          style={{
                            fontSize: '0.7rem',
                            color: 'var(--ink-soft)',
                            fontWeight: 600,
                          }}
                        >
                          {q.type}
                        </span>
                      ) : null}
                    </div>
                    <p style={{ fontWeight: 600, margin: '0 0 0.45rem', lineHeight: 1.35 }}>{q.question}</p>
                    {q.options && q.options.length > 0 && (
                      <ol style={{ margin: '0.15rem 0 0.35rem', paddingLeft: '1.1rem', fontSize: '0.92rem' }}>
                        {q.options.map((o, i) => (
                          <li key={i} style={{ marginBottom: '0.2rem' }}>
                            {o}
                          </li>
                        ))}
                      </ol>
                    )}
                    {q.explanation && (
                      <p style={{ fontSize: '0.85rem', color: 'var(--ink-soft)', margin: '0.35rem 0 0', lineHeight: 1.45 }}>
                        {q.explanation}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
