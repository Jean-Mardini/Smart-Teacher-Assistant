import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiStream } from '../api/client'
import { DocPicker } from '../components/DocPicker'

type RubricItem = {
  name?: string
  description?: string
  points?: number
  grounding?: string
  mode?: string
  expected_answer?: string
  item_origin?: string
}

type GeneratedTask = { number: number; description: string; points: number }
type GeneratedQuestion = {
  number: number
  type: string
  question: string
  options?: string[]
  answer?: string
  points: number
}

type AssignmentResult = {
  title?: string
  objective?: string
  instructions?: string
  tasks?: GeneratedTask[]
  submission_requirements?: string
  rubric_items?: RubricItem[]
}

type ExamResult = {
  title?: string
  instructions?: string
  duration?: string
  questions?: GeneratedQuestion[]
  rubric_items?: RubricItem[]
}

type StreamEvent = {
  status?: string
  message?: string
  done?: boolean
  error?: string
  [key: string]: unknown
}

const DIFFICULTY_OPTIONS = ['easy', 'medium', 'hard']
const QUESTION_TYPES = ['mcq', 'short_answer', 'essay', 'true_false']
const QUESTION_TYPE_LABELS: Record<string, string> = {
  mcq: 'Multiple Choice',
  short_answer: 'Short Answer',
  essay: 'Essay',
  true_false: 'True / False',
}

function rubricTotal(items: RubricItem[]) {
  return items.reduce((s, i) => s + Number(i.points || 0), 0)
}

export function GeneratePage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'assignment' | 'exam'>('assignment')

  // shared source
  const [docIds, setDocIds] = useState<string[]>([])
  const [sourceText, setSourceText] = useState('')
  const [difficulty, setDifficulty] = useState('medium')
  const [totalPoints, setTotalPoints] = useState(100)

  // assignment-specific
  const [taskCount, setTaskCount] = useState(5)

  // exam-specific
  const [questionCount, setQuestionCount] = useState(10)
  const [questionTypes, setQuestionTypes] = useState<string[]>(['short_answer'])

  // output
  const [assignmentResult, setAssignmentResult] = useState<AssignmentResult | null>(null)
  const [examResult, setExamResult] = useState<ExamResult | null>(null)

  const [loading, setLoading] = useState(false)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  function toggleQuestionType(type: string) {
    setQuestionTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    )
  }

  async function generate() {
    setLoading(true)
    setError(null)
    setStatusMsg(null)
    setAssignmentResult(null)
    setExamResult(null)

    const body = {
      text: sourceText,
      document_ids: docIds,
      difficulty,
      total_points: totalPoints,
      ...(mode === 'assignment'
        ? { task_count: taskCount }
        : { question_count: questionCount, question_types: questionTypes }),
    }

    try {
      for await (const event of apiStream<StreamEvent>(`/generator/${mode}/stream`, {
        method: 'POST',
        body: JSON.stringify(body),
      })) {
        if (event.error) throw new Error(event.error as string)
        if (event.message) setStatusMsg(event.message as string)
        if (event.done) {
          if (mode === 'assignment') setAssignmentResult(event as AssignmentResult)
          else setExamResult(event as ExamResult)
          setStatusMsg(null)
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed.')
    } finally {
      setLoading(false)
    }
  }

  function sendToGrading(rubricItems: RubricItem[], origin: 'assignment' | 'teacher_key') {
    const tagged = rubricItems.map((item) => ({ ...item, item_origin: origin }))
    navigate('/grade', { state: { rubric: tagged, origin } })
  }

  function downloadTxt(content: string, filename: string) {
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  function assignmentToText(r: AssignmentResult): string {
    const lines: string[] = []
    lines.push(`ASSIGNMENT: ${r.title || ''}`)
    lines.push('='.repeat(70))
    if (r.objective) lines.push(`\nObjective: ${r.objective}`)
    if (r.instructions) lines.push(`\nInstructions:\n${r.instructions}`)
    lines.push('\nTASKS')
    lines.push('-'.repeat(70))
    for (const task of r.tasks || []) {
      lines.push(`${task.number}. (${task.points} pts) ${task.description}`)
    }
    if (r.submission_requirements) lines.push(`\nSubmission: ${r.submission_requirements}`)
    return lines.join('\n')
  }

  function examToText(r: ExamResult): string {
    const lines: string[] = []
    lines.push(`EXAM: ${r.title || ''}`)
    lines.push('='.repeat(70))
    if (r.instructions) lines.push(`\nInstructions: ${r.instructions}`)
    if (r.duration) lines.push(`Duration: ${r.duration}`)
    lines.push('\nQUESTIONS')
    lines.push('-'.repeat(70))
    for (const q of r.questions || []) {
      lines.push(`\n${q.number}. [${q.type.toUpperCase()}] (${q.points} pts)`)
      lines.push(q.question)
      if (q.options?.length) q.options.forEach((o) => lines.push(`   ${o}`))
    }
    return lines.join('\n')
  }

  const result = mode === 'assignment' ? assignmentResult : examResult
  const rubricItems: RubricItem[] = (result as any)?.rubric_items || []

  return (
    <>
      <h1 className="page-title">Generate</h1>
      <p className="page-sub">
        Create assignments and exams from your library documents or pasted material — rubric included and ready for grading.
      </p>

      {/* Mode tabs */}
      <div className="tabs" style={{ marginBottom: '1.25rem' }}>
        <button type="button" className={mode === 'assignment' ? 'active' : ''} onClick={() => setMode('assignment')}>
          Assignment
        </button>
        <button type="button" className={mode === 'exam' ? 'active' : ''} onClick={() => setMode('exam')}>
          Exam
        </button>
      </div>

      {/* Source */}
      <div className="panel" style={{ marginBottom: '1rem' }}>
        <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.05rem' }}>1. Source material</h2>
        <DocPicker value={docIds} onChange={setDocIds} accept=".pdf,.docx,.pptx,.txt,.md" />
        <div className="field" style={{ marginTop: '0.75rem' }}>
          <label htmlFor="gen-text">Or paste text directly</label>
          <textarea
            id="gen-text"
            rows={6}
            value={sourceText}
            placeholder="Paste chapter, lecture notes, or any source material…"
            onChange={(e) => setSourceText(e.target.value)}
          />
        </div>
      </div>

      {/* Options */}
      <div className="panel" style={{ marginBottom: '1rem' }}>
        <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.05rem' }}>2. Options</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '0.75rem' }}>
          <div className="field" style={{ margin: 0 }}>
            <label>Difficulty</label>
            <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              {DIFFICULTY_OPTIONS.map((d) => (
                <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
              ))}
            </select>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label>Total points</label>
            <input type="number" min={1} max={2000} value={totalPoints} onChange={(e) => setTotalPoints(Number(e.target.value))} />
          </div>
          {mode === 'assignment' ? (
            <div className="field" style={{ margin: 0 }}>
              <label>Number of tasks</label>
              <input type="number" min={1} max={20} value={taskCount} onChange={(e) => setTaskCount(Number(e.target.value))} />
            </div>
          ) : (
            <div className="field" style={{ margin: 0 }}>
              <label>Number of questions</label>
              <input type="number" min={1} max={50} value={questionCount} onChange={(e) => setQuestionCount(Number(e.target.value))} />
            </div>
          )}
        </div>

        {mode === 'exam' && (
          <div style={{ marginTop: '0.85rem' }}>
            <label style={{ display: 'block', marginBottom: '0.45rem', fontSize: '0.88rem', fontWeight: 600 }}>
              Question types
            </label>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {QUESTION_TYPES.map((type) => (
                <label
                  key={type}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    padding: '0.35rem 0.65rem',
                    borderRadius: '999px',
                    border: `1px solid ${questionTypes.includes(type) ? 'rgba(193,127,89,0.6)' : 'var(--line)'}`,
                    background: questionTypes.includes(type) ? 'rgba(193,127,89,0.12)' : 'transparent',
                    cursor: 'pointer',
                    fontSize: '0.84rem',
                    fontWeight: 600,
                    userSelect: 'none',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={questionTypes.includes(type)}
                    onChange={() => toggleQuestionType(type)}
                    style={{ display: 'none' }}
                  />
                  {QUESTION_TYPE_LABELS[type]}
                </label>
              ))}
            </div>
          </div>
        )}

        <button
          type="button"
          className="btn btn--primary"
          disabled={loading || (!docIds.length && !sourceText.trim())}
          style={{ marginTop: '1rem' }}
          onClick={() => void generate()}
        >
          {loading ? (statusMsg || 'Generating…') : `Generate ${mode === 'assignment' ? 'Assignment' : 'Exam'}`}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {/* Assignment result */}
      {mode === 'assignment' && assignmentResult && (
        <>
          <div className="panel" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem' }}>
              <h2 style={{ margin: 0, fontSize: '1.1rem' }}>{assignmentResult.title || 'Generated Assignment'}</h2>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <button type="button" className="btn btn--ghost" onClick={() => downloadTxt(assignmentToText(assignmentResult), 'assignment.txt')}>
                  Download TXT
                </button>
              </div>
            </div>

            {assignmentResult.objective && (
              <p style={{ margin: '0 0 0.75rem', color: 'var(--ink-soft)', fontSize: '0.93rem' }}>
                <strong>Objective:</strong> {assignmentResult.objective}
              </p>
            )}
            {assignmentResult.instructions && (
              <p style={{ margin: '0 0 1rem', fontSize: '0.93rem' }}>{assignmentResult.instructions}</p>
            )}

            <div style={{ borderTop: '1px solid var(--line)', paddingTop: '0.85rem' }}>
              {(assignmentResult.tasks || []).map((task) => (
                <div key={task.number} style={{ marginBottom: '0.85rem', paddingLeft: '0.5rem', borderLeft: '3px solid rgba(193,127,89,0.4)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem' }}>
                    <strong style={{ fontSize: '0.95rem' }}>Task {task.number}</strong>
                    <span className="pill">{task.points} pts</span>
                  </div>
                  <p style={{ margin: '0.3rem 0 0', fontSize: '0.93rem' }}>{task.description}</p>
                </div>
              ))}
            </div>

            {assignmentResult.submission_requirements && (
              <p style={{ margin: '0.75rem 0 0', fontSize: '0.88rem', color: 'var(--ink-soft)' }}>
                <strong>Submission:</strong> {assignmentResult.submission_requirements}
              </p>
            )}
          </div>

          {rubricItems.length > 0 && (
            <RubricPreview
              items={rubricItems}
              totalPoints={totalPoints}
              onSendToGrading={() => sendToGrading(rubricItems, 'assignment')}
            />
          )}
        </>
      )}

      {/* Exam result */}
      {mode === 'exam' && examResult && (
        <>
          <div className="panel" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem' }}>
              <h2 style={{ margin: 0, fontSize: '1.1rem' }}>{examResult.title || 'Generated Exam'}</h2>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {examResult.duration && <span className="pill">{examResult.duration}</span>}
                <button type="button" className="btn btn--ghost" onClick={() => downloadTxt(examToText(examResult), 'exam.txt')}>
                  Download TXT
                </button>
              </div>
            </div>

            {examResult.instructions && (
              <p style={{ margin: '0 0 1rem', fontSize: '0.93rem' }}>{examResult.instructions}</p>
            )}

            <div style={{ borderTop: '1px solid var(--line)', paddingTop: '0.85rem' }}>
              {(examResult.questions || []).map((q) => (
                <div key={q.number} style={{ marginBottom: '1.1rem', paddingLeft: '0.5rem', borderLeft: `3px solid ${q.type === 'mcq' ? 'rgba(80,140,200,0.4)' : q.type === 'essay' ? 'rgba(150,100,200,0.4)' : q.type === 'true_false' ? 'rgba(80,180,120,0.4)' : 'rgba(193,127,89,0.4)'}` }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.65rem', flexWrap: 'wrap' }}>
                    <strong style={{ fontSize: '0.95rem' }}>Q{q.number}.</strong>
                    <span className="pill" style={{ fontSize: '0.72rem' }}>{QUESTION_TYPE_LABELS[q.type] || q.type}</span>
                    <span className="pill" style={{ fontSize: '0.72rem' }}>{q.points} pts</span>
                  </div>
                  <p style={{ margin: '0.35rem 0 0.45rem', fontSize: '0.93rem' }}>{q.question}</p>
                  {q.options?.length ? (
                    <ul style={{ margin: '0 0 0.35rem', paddingLeft: '1.25rem', fontSize: '0.9rem' }}>
                      {q.options.map((opt, i) => <li key={i}>{opt}</li>)}
                    </ul>
                  ) : null}
                </div>
              ))}
            </div>
          </div>

          {rubricItems.length > 0 && (
            <RubricPreview
              items={rubricItems}
              totalPoints={totalPoints}
              onSendToGrading={() => sendToGrading(rubricItems, 'teacher_key')}
            />
          )}
        </>
      )}
    </>
  )
}

function RubricPreview({
  items,
  totalPoints,
  onSendToGrading,
}: {
  items: RubricItem[]
  totalPoints: number
  onSendToGrading: () => void
}) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  function toggle(i: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(i) ? next.delete(i) : next.add(i)
      return next
    })
  }

  return (
    <div className="panel">
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.85rem' }}>
        <h2 style={{ margin: 0, fontSize: '1.05rem' }}>Generated rubric</h2>
        <span style={{ color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
          Total: <strong>{rubricTotal(items)}</strong> / {totalPoints} pts
        </span>
      </div>

      {items.map((item, i) => {
        const isOpen = expanded.has(i)
        return (
          <div key={i} style={{ border: '1px solid var(--line)', borderRadius: '12px', marginBottom: '0.45rem', overflow: 'hidden', background: 'rgba(255,255,255,0.6)' }}>
            <button
              type="button"
              onClick={() => toggle(i)}
              style={{ width: '100%', display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.65rem 1rem', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}
            >
              <span style={{ fontWeight: 600, flex: 1, fontSize: '0.92rem', color: 'var(--ink)' }}>{item.name || `Criterion ${i + 1}`}</span>
              {item.grounding && <span className="pill" style={{ fontSize: '0.7rem' }}>{item.grounding}</span>}
              {item.mode && <span className="pill" style={{ fontSize: '0.7rem' }}>{item.mode}</span>}
              <span style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--ink-soft)', whiteSpace: 'nowrap' }}>{item.points ?? 0} pts</span>
              <span style={{ fontSize: '0.7rem', color: 'var(--ink-soft)' }}>{isOpen ? '▲' : '▼'}</span>
            </button>
            {isOpen && (
              <div style={{ padding: '0 1rem 0.85rem', borderTop: '1px solid var(--line)', fontSize: '0.9rem' }}>
                {item.description && <p style={{ margin: '0.65rem 0 0', color: 'var(--ink-soft)' }}>{item.description}</p>}
                {item.expected_answer && (
                  <p style={{ margin: '0.45rem 0 0' }}><strong>Expected:</strong> {item.expected_answer}</p>
                )}
              </div>
            )}
          </div>
        )
      })}

      <button type="button" className="btn btn--accent" style={{ marginTop: '0.85rem' }} onClick={onSendToGrading}>
        Send rubric to Grading →
      </button>
    </div>
  )
}
