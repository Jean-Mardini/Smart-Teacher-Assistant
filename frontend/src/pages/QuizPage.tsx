import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { DocPicker } from '../components/DocPicker'
import { apiJson, apiPostBlob, triggerDownload } from '../api/client'
import { buildTeacherKeyFromQuiz, quizQuestionsToRubricItems, rubricPointsSum } from '../lib/quizToRubric'

type QuizQuestion = {
  type?: string
  question?: string
  options?: string[]
  answer_index?: number | null
  answer_text?: string | null
  explanation?: string
  /** Marks for this item; server splits ``total_points`` across questions. */
  points?: number
}

type QuizResult = {
  quiz?: QuizQuestion[]
  /** Echo from API: resolved quiz heading (document or optional title override). */
  quiz_title?: string | null
}

const DIFFICULTY_LEVELS = [
  { id: 'easy', label: 'Easy', hint: 'Recall & definitions' },
  { id: 'medium', label: 'Medium', hint: 'Typical classroom mix' },
  { id: 'hard', label: 'Hard', hint: 'Synthesis & edge cases' },
] as const

type CreationMode = 'generate' | 'paste' | 'template' | 'import'

const CREATION_CARDS: {
  id: CreationMode
  icon: string
  title: string
  description: string
  badge?: string
}[] = [
  {
    id: 'generate',
    icon: '✦',
    title: 'Quick prompt',
    description: 'One-line topic; the model expands it into quiz questions from that idea',
    badge: 'Quick',
  },
  {
    id: 'paste',
    icon: 'Aa',
    title: 'Paste in text',
    description: 'Paste notes, an outline, or lesson content to question against',
  },
  {
    id: 'template',
    icon: '▥',
    title: 'Library document',
    description: 'Pick an indexed file from your library (PDF, Word, etc.)',
  },
  {
    id: 'import',
    icon: '↑',
    title: 'Import file or URL',
    description: 'Choose a library file and/or pull text from a web page',
  },
]

const QUIZ_LIBRARY_HINT =
  'Upload into the Library if needed, then pick one document. For import mode you can add a URL below; when set, it takes priority over the file for this run.'

function clampInt(n: number, lo: number, hi: number) {
  if (!Number.isFinite(n)) return lo
  return Math.min(hi, Math.max(lo, Math.floor(n)))
}

/** Server allows up to this many questions (MCQ + short combined). */
const QUIZ_MAX_TOTAL = 100

export function QuizPage() {
  const navigate = useNavigate()
  const [creationMode, setCreationMode] = useState<CreationMode>('template')
  const [docId, setDocId] = useState('')
  const [promptLine, setPromptLine] = useState('')
  const [pastedText, setPastedText] = useState('')
  const [importUrl, setImportUrl] = useState('')
  const [sourceTitle, setSourceTitle] = useState('')
  const [nMcq, setNMcq] = useState(3)
  const [nShort, setNShort] = useState(2)
  const [nTf, setNTf] = useState(0)
  const [totalPoints, setTotalPoints] = useState(25)
  const [difficulty, setDifficulty] = useState('medium')
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<QuizResult | null>(null)

  const quizTotal = nMcq + nShort + nTf

  function setNMcqSafe(raw: number) {
    let v = clampInt(raw, 0, QUIZ_MAX_TOTAL)
    let short = nShort
    let tf = nTf
    while (v + short + tf > QUIZ_MAX_TOTAL) {
      if (tf > 0) tf--
      else if (short > 0) short--
      else v--
    }
    setNMcq(v)
    setNShort(short)
    setNTf(tf)
  }

  function setNShortSafe(raw: number) {
    let short = clampInt(raw, 0, QUIZ_MAX_TOTAL)
    let mcq = nMcq
    let tf = nTf
    while (mcq + short + tf > QUIZ_MAX_TOTAL) {
      if (tf > 0) tf--
      else if (mcq > 0) mcq--
      else short--
    }
    setNMcq(mcq)
    setNShort(short)
    setNTf(tf)
  }

  function setNTfSafe(raw: number) {
    let tf = clampInt(raw, 0, QUIZ_MAX_TOTAL)
    let mcq = nMcq
    let short = nShort
    while (mcq + short + tf > QUIZ_MAX_TOTAL) {
      if (short > 0) short--
      else if (mcq > 0) mcq--
      else tf--
    }
    setNMcq(mcq)
    setNShort(short)
    setNTf(tf)
  }

  function quizBody(): Record<string, unknown> {
    const base: Record<string, unknown> = {
      n_mcq: nMcq,
      n_short_answer: nShort,
      n_true_false: nTf,
      difficulty,
      total_points: clampInt(totalPoints, 1, 2000),
    }
    if (creationMode === 'generate') {
      base.source_text = promptLine.trim()
      if (sourceTitle.trim()) base.source_title = sourceTitle.trim()
      return base
    }
    if (creationMode === 'paste') {
      base.source_text = pastedText.trim()
      if (sourceTitle.trim()) base.source_title = sourceTitle.trim()
      return base
    }
    if (creationMode === 'import' && importUrl.trim()) {
      base.source_url = importUrl.trim()
      if (sourceTitle.trim()) base.source_title = sourceTitle.trim()
      return base
    }
    base.document_id = docId.trim()
    if (sourceTitle.trim()) base.source_title = sourceTitle.trim()
    return base
  }

  function validateSource(): string | null {
    if (creationMode === 'generate') {
      if (!promptLine.trim()) return 'Enter a one-line topic or prompt.'
      return null
    }
    if (creationMode === 'paste') {
      if (!pastedText.trim()) return 'Paste your notes or outline.'
      return null
    }
    if (creationMode === 'template') {
      if (!docId.trim()) return 'Choose a document from the library.'
      return null
    }
    if (creationMode === 'import') {
      if (!docId.trim() && !importUrl.trim()) return 'Pick a library document or enter a page URL (https…).'
      return null
    }
    return null
  }

  const canRun = validateSource() === null && quizTotal >= 1 && quizTotal <= QUIZ_MAX_TOTAL

  const hasQuizResult = Boolean(result?.quiz && result.quiz.length > 0)

  async function exportMoodle() {
    const v = validateSource()
    if (v) {
      setError(v)
      return
    }
    if (quizTotal < 1 || quizTotal > QUIZ_MAX_TOTAL) {
      setError(`Set question counts (1–${QUIZ_MAX_TOTAL} total) before export.`)
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
    const v = validateSource()
    if (v) {
      setError(v)
      return
    }
    if (quizTotal < 1) {
      setError('Choose at least one MCQ, true/false, or short-answer question.')
      return
    }
    if (quizTotal > QUIZ_MAX_TOTAL) {
      setError(`At most ${QUIZ_MAX_TOTAL} questions total (all types combined).`)
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await apiJson<QuizResult>('/agents/quiz', {
        method: 'POST',
        body: JSON.stringify(quizBody()),
      })
      setResult(res)
      const n = res.quiz?.length ?? 0
      if (n === 0) {
        setError(
          'The server returned no questions. Often the file has no extracted text in the index yet, the model returned invalid JSON, or Groq hit a rate limit—check the API terminal logs.',
        )
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  /** Sends quiz questions as a QA-style rubric into Flexible Grader (Grade tab). */
  function exportQuizRubricToGrading() {
    const list = result?.quiz
    if (!list?.length) return
    const rubric = quizQuestionsToRubricItems(list)
    const teacherKeyText = buildTeacherKeyFromQuiz(list, result.quiz_title)
    const sumPts = rubricPointsSum(rubric)
    const titleHint =
      (result.quiz_title && result.quiz_title.trim()) ||
      (singleTitleFromContext() || 'Exam / quiz submission')
    navigate('/grade', {
      state: {
        rubric,
        origin: 'qa',
        teacher_key_text: teacherKeyText,
        suggested_total_points: sumPts >= 1 ? sumPts : totalPoints,
        result_title_hint: titleHint,
        importMessage: `Exported ${rubric.length} rubric row(s) into Grading (QA). Open the QA rubric tab to review items if needed, then use the Grade tab for student text submissions.`,
      },
    })
  }

  /** Prefer quiz-related title for handoff when available. */
  function singleTitleFromContext(): string {
    if (sourceTitle.trim()) return sourceTitle.trim()
    if (creationMode === 'generate' && promptLine.trim()) return promptLine.trim().slice(0, 120)
    return ''
  }

  const showThread = Boolean(error || hasQuizResult)

  return (
    <div className="studio-route summarize-page dialogue-page">
      <h1 className="page-title">Quiz</h1>
      <p className="page-sub">
        Build MCQ, true/false, and short-answer items from a <strong>prompt</strong>, <strong>pasted text</strong>, a{' '}
        <strong>library document</strong>, or a <strong>URL</strong>. Export to <strong>Moodle XML</strong> for LMS
        import, or use <strong>Export rubric to Grading</strong> after a run to open Flexible Grader with one row per
        question (exact for MCQ / true-false, conceptual for short answer).
      </p>

      <div className="dialogue-shell">
        <main className="dialogue-main">
          <section className="dialogue-card dialogue-card--scope" aria-labelledby="quiz-scope-heading">
            <div className="dialogue-card__head">
              <h2 id="quiz-scope-heading" className="dialogue-card__title">
                Scope
              </h2>
              <p className="dialogue-card__lede">
                Pick how the generator reads your material, then fill the fields below. Library and import modes use
                the same document resolution as slide generation.
              </p>
            </div>

            <div className="dialogue-sidebar__block">
              <span className="summarize-field-label">Source type</span>
              <div className="dialogue-length summarize-length" role="group" aria-label="Quiz source type">
                {CREATION_CARDS.map((c) => {
                  const active = creationMode === c.id
                  return (
                    <button
                      key={c.id}
                      type="button"
                      className={active ? 'is-on' : ''}
                      onClick={() => {
                        setCreationMode(c.id)
                        setError(null)
                      }}
                    >
                      <span style={{ marginRight: '0.35rem', opacity: 0.9 }} aria-hidden>
                        {c.icon}
                      </span>
                      {c.title}
                      {c.badge ? (
                        <span
                          style={{
                            marginLeft: '0.35rem',
                            fontSize: '0.65rem',
                            textTransform: 'uppercase',
                            letterSpacing: '0.04em',
                            color: 'var(--ink-soft)',
                            fontWeight: 600,
                          }}
                        >
                          {c.badge}
                        </span>
                      ) : null}
                      <span className="summarize-length-hint">{c.description}</span>
                    </button>
                  )
                })}
              </div>
            </div>

            {creationMode === 'generate' && (
              <div className="field dialogue-field-tight">
                <label htmlFor="quiz-oneprompt">One-line prompt</label>
                <input
                  id="quiz-oneprompt"
                  type="text"
                  value={promptLine}
                  onChange={(e) => setPromptLine(e.target.value)}
                  placeholder="e.g. Photosynthesis — grade 9, definitions and Calvin cycle"
                  className="dialogue-input-mono"
                />
              </div>
            )}

            {creationMode === 'paste' && (
              <div className="field dialogue-field-tight">
                <label htmlFor="quiz-paste">Notes or outline</label>
                <textarea
                  id="quiz-paste"
                  rows={8}
                  value={pastedText}
                  onChange={(e) => setPastedText(e.target.value)}
                  placeholder="Paste bullets, a lesson plan, or raw notes…"
                  className="dialogue-composer__textarea"
                  style={{ minHeight: '8rem' }}
                />
              </div>
            )}

            {(creationMode === 'generate' || creationMode === 'paste') && (
              <div className="field dialogue-field-tight">
                <label htmlFor="quiz-dtitle">Quiz title (optional)</label>
                <input
                  id="quiz-dtitle"
                  type="text"
                  value={sourceTitle}
                  onChange={(e) => setSourceTitle(e.target.value)}
                  placeholder="Used in Moodle export category / filename when set"
                />
              </div>
            )}

            {(creationMode === 'template' || creationMode === 'import') && (
              <>
                <DocPicker
                  value={docId ? [docId] : []}
                  onChange={(ids) => setDocId(ids[0] ?? '')}
                  accept=".pdf,.docx,.pptx,.txt,.md"
                  compact
                  maxSelection={1}
                  compactHint={QUIZ_LIBRARY_HINT}
                />
                {creationMode === 'template' && (
                  <div className="field dialogue-field-tight">
                    <label htmlFor="quiz-lib-title">Quiz title (optional)</label>
                    <input
                      id="quiz-lib-title"
                      type="text"
                      value={sourceTitle}
                      onChange={(e) => setSourceTitle(e.target.value)}
                      placeholder="Shown above your questions and in Moodle export when set"
                    />
                  </div>
                )}
                {creationMode === 'import' && (
                  <>
                    <div className="field dialogue-field-tight">
                      <label htmlFor="quiz-url">Or import from URL</label>
                      <input
                        id="quiz-url"
                        type="url"
                        value={importUrl}
                        onChange={(e) => setImportUrl(e.target.value)}
                        placeholder="https://… (text extracted on the server)"
                        className="dialogue-input-mono"
                      />
                      {importUrl.trim() ? (
                        <p className="dialogue-field-hint">
                          When a URL is set, it takes priority over the library document for this run.
                        </p>
                      ) : null}
                    </div>
                    <div className="field dialogue-field-tight">
                      <label htmlFor="quiz-import-title">Quiz title (optional)</label>
                      <input
                        id="quiz-import-title"
                        type="text"
                        value={sourceTitle}
                        onChange={(e) => setSourceTitle(e.target.value)}
                        placeholder="Override title for URL import"
                      />
                    </div>
                  </>
                )}
              </>
            )}
          </section>

          <aside className="dialogue-sidebar" aria-labelledby="quiz-options-heading">
            <h3 id="quiz-options-heading" className="dialogue-sidebar__title">
              Mix &amp; difficulty
            </h3>
            <p className="dialogue-sidebar__lede">These apply to the next quiz generation only.</p>

            <div className="dialogue-sidebar__block">
              <span className="summarize-field-label">Multiple choice (MCQ)</span>
              <div className="field dialogue-field-tight" style={{ marginBottom: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
                  <input
                    id="n-mcq-range"
                    type="range"
                    min={0}
                    max={QUIZ_MAX_TOTAL}
                    value={nMcq}
                    onChange={(e) => setNMcqSafe(Number(e.target.value))}
                    aria-label="MCQ count"
                    style={{ flex: '1 1 140px', minWidth: 0, width: '100%', accentColor: '#5c6670' }}
                  />
                  <input
                    id="n-mcq"
                    type="number"
                    min={0}
                    max={QUIZ_MAX_TOTAL}
                    value={nMcq}
                    onChange={(e) => setNMcqSafe(Number(e.target.value))}
                    aria-label="MCQ count exact"
                    style={{ width: '3.75rem' }}
                  />
                </div>
              </div>
            </div>

            <div className="dialogue-sidebar__block">
              <span className="summarize-field-label">Short answer</span>
              <div className="field dialogue-field-tight" style={{ marginBottom: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
                  <input
                    id="n-short-range"
                    type="range"
                    min={0}
                    max={QUIZ_MAX_TOTAL}
                    value={nShort}
                    onChange={(e) => setNShortSafe(Number(e.target.value))}
                    aria-label="Short answer count"
                    style={{ flex: '1 1 140px', minWidth: 0, width: '100%', accentColor: '#5c6670' }}
                  />
                  <input
                    id="n-short"
                    type="number"
                    min={0}
                    max={QUIZ_MAX_TOTAL}
                    value={nShort}
                    onChange={(e) => setNShortSafe(Number(e.target.value))}
                    aria-label="Short answer count exact"
                    style={{ width: '3.75rem' }}
                  />
                </div>
              </div>
            </div>

            <div className="dialogue-sidebar__block">
              <span className="summarize-field-label">True / false</span>
              <div className="field dialogue-field-tight" style={{ marginBottom: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
                  <input
                    id="n-tf-range"
                    type="range"
                    min={0}
                    max={QUIZ_MAX_TOTAL}
                    value={nTf}
                    onChange={(e) => setNTfSafe(Number(e.target.value))}
                    aria-label="True/false count"
                    style={{ flex: '1 1 140px', minWidth: 0, width: '100%', accentColor: '#a67c52' }}
                  />
                  <input
                    id="n-tf"
                    type="number"
                    min={0}
                    max={QUIZ_MAX_TOTAL}
                    value={nTf}
                    onChange={(e) => setNTfSafe(Number(e.target.value))}
                    aria-label="True/false count exact"
                    style={{ width: '3.75rem' }}
                  />
                </div>
              </div>
            </div>

            <p
              style={{
                margin: 0,
                fontSize: '0.8rem',
                color: quizTotal > QUIZ_MAX_TOTAL ? '#b45309' : 'var(--ink-soft)',
              }}
            >
              Total: <strong>{quizTotal}</strong> / {QUIZ_MAX_TOTAL}
              {quizTotal < 1 ? ' — pick at least one.' : null}
              {quizTotal > QUIZ_MAX_TOTAL ? ' — over server limit.' : null}
            </p>

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
                    width: quizTotal > 0 ? `${(nMcq / quizTotal) * 100}%` : '33.33%',
                    background: '#5c6670',
                    transition: 'width 0.2s ease',
                  }}
                />
                <div
                  style={{
                    width: quizTotal > 0 ? `${(nTf / quizTotal) * 100}%` : '33.33%',
                    background: '#a67c52',
                    transition: 'width 0.2s ease',
                  }}
                />
                <div
                  style={{
                    width: quizTotal > 0 ? `${(nShort / quizTotal) * 100}%` : '33.33%',
                    background: '#d9d7d2',
                    transition: 'width 0.2s ease',
                  }}
                />
              </div>
              <p style={{ margin: '0.45rem 0 0', fontSize: '0.8rem', color: 'var(--ink-soft)' }}>
                <strong style={{ color: 'var(--ink)' }}>{nMcq}</strong> MCQ ·{' '}
                <strong style={{ color: 'var(--ink)' }}>{nTf}</strong> T/F ·{' '}
                <strong style={{ color: 'var(--ink)' }}>{nShort}</strong> short
              </p>
            </div>

            <div className="summarize-stat">
              <span>Questions in this run</span>
              <strong>
                {quizTotal} / {QUIZ_MAX_TOTAL}
              </strong>
            </div>

            <div className="dialogue-sidebar__block">
              <span className="summarize-field-label">Difficulty</span>
              <div className="dialogue-length summarize-length" role="group" aria-label="Difficulty">
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

            <div className="field dialogue-field-tight">
              <label htmlFor="quiz-total-points">Total points (whole quiz)</label>
              <input
                id="quiz-total-points"
                type="number"
                min={1}
                max={2000}
                value={totalPoints}
                onChange={(e) => setTotalPoints(clampInt(Number(e.target.value), 1, 2000))}
                aria-describedby="quiz-total-points-hint"
              />
              <p id="quiz-total-points-hint" className="dialogue-field-hint">
                Split evenly across questions (at least 1 point each). Moodle export uses these as default grades.
              </p>
            </div>
          </aside>

          {showThread && (
            <section className="dialogue-card dialogue-card--thread" aria-label="Quiz output">
              <div className="dialogue-thread__toolbar">
                <span className="dialogue-thread__badge">Quiz</span>
                {hasQuizResult ? (
                  <div className="dialogue-thread__export-actions">
                    <button
                      type="button"
                      className="btn btn--primary"
                      disabled={exporting || !canRun}
                      onClick={() => void exportMoodle()}
                    >
                      {exporting ? 'Exporting…' : 'Moodle XML'}
                    </button>
                    <button type="button" className="btn btn--ghost" onClick={() => exportQuizRubricToGrading()}>
                      Rubric → Grading
                    </button>
                  </div>
                ) : null}
              </div>
              <div className="dialogue-thread__body summarize-results__body">
                {error && <div className="error dialogue-thread__error">{error}</div>}
                {hasQuizResult && (
                  <div>
                    <div style={{ marginBottom: '1rem' }}>
                      <h3 style={{ margin: 0, fontSize: '1.05rem' }}>
                        {(result!.quiz_title && result!.quiz_title!.trim()) || 'Quiz'}
                      </h3>
                      <p style={{ margin: '0.35rem 0 0', fontSize: '0.92rem', color: 'var(--ink-soft)' }}>
                        {result!.quiz!.length} question{result!.quiz!.length === 1 ? '' : 's'}
                        {(() => {
                          const pts = result!.quiz!.reduce(
                            (s, q) => s + (typeof q.points === 'number' ? q.points : 0),
                            0,
                          )
                          return pts > 0 ? ` · ${pts} points total` : null
                        })()}
                      </p>
                      <p style={{ margin: '0.5rem 0 0', fontSize: '0.82rem', color: 'var(--ink-soft)', maxWidth: '42rem' }}>
                        Use <strong>Rubric → Grading</strong> in the toolbar to open the Grade tab with one rubric row
                        per question.
                      </p>
                    </div>
                    <div
                      style={{
                        display: 'grid',
                        gap: '0.85rem',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 280px), 1fr))',
                      }}
                    >
                      {result!.quiz!.map((q, idx) => {
                        const isMcq = q.type === 'mcq'
                        const isTf = q.type === 'true_false'
                        const accent = isMcq ? '#8a9199' : isTf ? '#a67c52' : '#b5bcc4'
                        return (
                          <div
                            key={idx}
                            style={{
                              position: 'relative',
                              padding: '0.85rem 1rem 0.95rem 1rem',
                              borderRadius: '14px',
                              border: '1px solid var(--line)',
                              borderLeft: `4px solid ${accent}`,
                              background: '#fff',
                              boxShadow: '0 2px 12px rgba(21, 36, 51, 0.04)',
                            }}
                          >
                            <div
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.5rem',
                                marginBottom: '0.45rem',
                                flexWrap: 'wrap',
                              }}
                            >
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
                                  {q.type === 'true_false' ? 'true/false' : q.type}
                                </span>
                              ) : null}
                              {typeof q.points === 'number' && q.points > 0 ? (
                                <span
                                  style={{
                                    fontSize: '0.7rem',
                                    fontWeight: 700,
                                    color: 'var(--ink)',
                                    marginLeft: '0.15rem',
                                  }}
                                >
                                  {q.points} pt{q.points === 1 ? '' : 's'}
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
                              <p
                                style={{
                                  fontSize: '0.85rem',
                                  color: 'var(--ink-soft)',
                                  margin: '0.35rem 0 0',
                                  lineHeight: 1.45,
                                }}
                              >
                                {q.explanation}
                              </p>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}

          <section className="dialogue-card dialogue-card--composer" aria-labelledby="quiz-run-heading">
            <h2 id="quiz-run-heading" className="dialogue-composer__label">
              Generate
            </h2>
            <p className="dialogue-card__lede" style={{ margin: '0 0 0.85rem' }}>
              Large question counts can take longer — keep this tab open until results appear above.
            </p>
            <div className="dialogue-composer__actions dialogue-composer__actions--full-run">
              <button
                type="button"
                className="btn btn--accent summarize-run"
                disabled={loading || !canRun}
                onClick={() => void run()}
              >
                {loading ? 'Generating…' : 'Generate quiz'}
              </button>
            </div>
            <div
              className="dialogue-composer__actions"
              style={{ marginTop: '0.65rem', flexWrap: 'wrap', gap: '0.5rem', justifyContent: 'stretch' }}
            >
              <button
                type="button"
                className="btn btn--ghost"
                style={{ flex: '1 1 12rem' }}
                disabled={exporting || !canRun}
                onClick={() => void exportMoodle()}
              >
                {exporting ? 'Exporting…' : 'Download Moodle XML'}
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                style={{ flex: '1 1 12rem' }}
                disabled={!hasQuizResult}
                title={hasQuizResult ? 'Open Grading with a rubric built from this quiz' : 'Generate a quiz first'}
                onClick={() => exportQuizRubricToGrading()}
              >
                Export rubric to Grading
              </button>
            </div>
          </section>
        </main>
      </div>
    </div>
  )
}
