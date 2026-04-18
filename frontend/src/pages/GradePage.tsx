import { useState } from 'react'
import { apiJson } from '../api/client'

export function GradePage() {
  const [tab, setTab] = useState<'assignment' | 'teacher' | 'grade'>('assignment')
  const [assignmentText, setAssignmentText] = useState('')
  const [teacherKeyText, setTeacherKeyText] = useState('')
  const [totalPoints, setTotalPoints] = useState(100)
  const [submission, setSubmission] = useState('')
  const [itemsJson, setItemsJson] = useState('[]')
  const [teacherKeyForGrade, setTeacherKeyForGrade] = useState('')
  const [referenceText, setReferenceText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rubricPreview, setRubricPreview] = useState<unknown>(null)
  const [gradeResult, setGradeResult] = useState<unknown>(null)

  async function genAssignment() {
    setLoading(true)
    setError(null)
    setRubricPreview(null)
    try {
      const res = await apiJson('/evaluation/rubric/from-assignment', {
        method: 'POST',
        body: JSON.stringify({ text: assignmentText, total_points: totalPoints }),
      })
      setRubricPreview(res)
      if (res && typeof res === 'object' && 'items' in res) {
        setItemsJson(JSON.stringify((res as { items: unknown }).items, null, 2))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  async function genTeacher() {
    setLoading(true)
    setError(null)
    setRubricPreview(null)
    try {
      const res = await apiJson('/evaluation/rubric/from-teacher-key', {
        method: 'POST',
        body: JSON.stringify({ text: teacherKeyText, total_points: totalPoints }),
      })
      setRubricPreview(res)
      if (res && typeof res === 'object' && 'items' in res) {
        setItemsJson(JSON.stringify((res as { items: unknown }).items, null, 2))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  async function grade() {
    setLoading(true)
    setError(null)
    setGradeResult(null)
    let items: unknown
    try {
      items = JSON.parse(itemsJson)
    } catch {
      setError('Rubric items must be valid JSON array.')
      setLoading(false)
      return
    }
    if (!Array.isArray(items)) {
      setError('Rubric items must be a JSON array.')
      setLoading(false)
      return
    }
    try {
      const res = await apiJson('/evaluation/grade', {
        method: 'POST',
        body: JSON.stringify({
          submission_text: submission,
          items,
          teacher_key_text: teacherKeyForGrade,
          reference_text: referenceText,
          result_title: 'Web submission',
        }),
      })
      setGradeResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <h1 className="page-title">Grading salon</h1>
      <p className="page-sub">
        Build a rubric from an assignment or answer key, then score a submission. Requires <code>GROQ_API_KEY</code> on
        the API.
      </p>
      {error && <div className="error">{error}</div>}

      <div className="tabs" style={{ marginBottom: '1rem' }}>
        <button type="button" className={tab === 'assignment' ? 'active' : ''} onClick={() => setTab('assignment')}>
          From assignment
        </button>
        <button type="button" className={tab === 'teacher' ? 'active' : ''} onClick={() => setTab('teacher')}>
          From teacher key
        </button>
        <button type="button" className={tab === 'grade' ? 'active' : ''} onClick={() => setTab('grade')}>
          Grade submission
        </button>
      </div>

      {tab === 'assignment' && (
        <div className="panel">
          <div className="field">
            <label htmlFor="assign">Assignment text</label>
            <textarea id="assign" value={assignmentText} onChange={(e) => setAssignmentText(e.target.value)} rows={8} />
          </div>
          <div className="field">
            <label htmlFor="tp">Total points</label>
            <input
              id="tp"
              type="number"
              min={1}
              max={2000}
              value={totalPoints}
              onChange={(e) => setTotalPoints(Number(e.target.value))}
            />
          </div>
          <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void genAssignment()}>
            {loading ? 'Generating…' : 'Generate rubric'}
          </button>
        </div>
      )}

      {tab === 'teacher' && (
        <div className="panel">
          <div className="field">
            <label htmlFor="tk">Teacher key text</label>
            <textarea id="tk" value={teacherKeyText} onChange={(e) => setTeacherKeyText(e.target.value)} rows={8} />
          </div>
          <div className="field">
            <label htmlFor="tp2">Total points</label>
            <input
              id="tp2"
              type="number"
              min={1}
              max={2000}
              value={totalPoints}
              onChange={(e) => setTotalPoints(Number(e.target.value))}
            />
          </div>
          <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void genTeacher()}>
            {loading ? 'Generating…' : 'Generate rubric'}
          </button>
        </div>
      )}

      {tab === 'grade' && (
        <div className="panel">
          <div className="field">
            <label htmlFor="sub">Student submission</label>
            <textarea id="sub" value={submission} onChange={(e) => setSubmission(e.target.value)} rows={8} />
          </div>
          <div className="field">
            <label htmlFor="items">Rubric items (JSON array)</label>
            <textarea id="items" value={itemsJson} onChange={(e) => setItemsJson(e.target.value)} rows={12} />
          </div>
          <div className="field">
            <label htmlFor="tkg">Teacher key (optional, for context)</label>
            <textarea id="tkg" value={teacherKeyForGrade} onChange={(e) => setTeacherKeyForGrade(e.target.value)} rows={4} />
          </div>
          <div className="field">
            <label htmlFor="ref">Reference material (optional)</label>
            <textarea id="ref" value={referenceText} onChange={(e) => setReferenceText(e.target.value)} rows={4} />
          </div>
          <button type="button" className="btn btn--accent" disabled={loading} onClick={() => void grade()}>
            {loading ? 'Grading…' : 'Grade'}
          </button>
        </div>
      )}

      {rubricPreview && tab !== 'grade' && (
        <div className="panel" style={{ marginTop: '1.25rem' }}>
          <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.1rem' }}>Rubric (raw)</h2>
          <pre className="pre-json">{JSON.stringify(rubricPreview, null, 2)}</pre>
          <p style={{ fontSize: '0.88rem', color: 'var(--ink-soft)', marginTop: '0.75rem' }}>
            Items were copied into the Grade tab JSON field. Open &quot;Grade submission&quot; to score.
          </p>
        </div>
      )}

      {gradeResult && (
        <div className="panel" style={{ marginTop: '1.25rem' }}>
          <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.1rem' }}>Grade result</h2>
          <pre className="pre-json">{JSON.stringify(gradeResult, null, 2)}</pre>
        </div>
      )}
    </>
  )
}
