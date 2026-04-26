import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { apiDownload, apiFormJson, apiJson, apiStream, apiUpload } from '../api/client'

type DocRow = {
  document_id: string
  title: string
  path: string
  filetype: string
}

type RubricItem = {
  item_origin?: string
  name?: string
  description?: string
  points?: number
  grounding?: string
  expected_answer?: string
  mode?: string
}

type RubricStreamEvent = {
  status?: string
  message?: string
  done?: boolean
  error?: string
  rubric_title?: string | null
  summary?: string[]
  items?: RubricItem[]
}

type EvaluationPreset = {
  items: RubricItem[]
  saved_at?: string
  total_points?: number
  origin?: string
}

type EvaluationResult = {
  id?: string
  timestamp?: string
  updated_at?: string
  title?: string
  overall_score?: number
  overall_out_of?: number
  manual_reviewed?: boolean
  history_type?: string
  batch_id?: string
  batch_name?: string
  batch_size?: number
  batch_rank?: number
  batch_created_at?: string
  score_percent?: number
  items_results?: Array<{
    item_origin?: string
    name?: string
    description?: string
    expected_answer?: string
    points?: number
    mode?: string
    grounding?: string
    earned_points?: number
    rationale?: string
    suggestions?: string[]
    evidence?: Array<{ quote?: string; source?: string }>
    matched_key_ideas?: string[]
    missing_key_ideas?: string[]
    misconceptions?: string[]
  }>
}

type GradeResponse = { record?: EvaluationResult }
type ParsedUploadListResponse = { items: Array<{ name: string; text: string }> }
type BatchGradeResponse = { records?: EvaluationResult[]; batch_id?: string; batch_name?: string; stats?: HistoryStats }
type HistoryStats = {
  total_records?: number
  single_records?: number
  batch_records?: number
  batch_count?: number
  average_percent?: number
  highest_percent?: number
  lowest_percent?: number
}
type HistoryBatch = {
  batch_id: string
  batch_name?: string
  created_at?: string
  submission_count?: number
  average_percent?: number
  highest_percent?: number
  lowest_percent?: number
  average_score?: number
  average_out_of?: number
  records?: EvaluationResult[]
}
type HistoryResponse = { records?: EvaluationResult[]; batches?: HistoryBatch[]; stats?: HistoryStats }

const LIBRARY_ACCEPT = '.pdf,.docx,.pptx,.txt,.md,.json'
const PARSE_ACCEPT = '.pdf,.docx,.pptx,.txt,.md,.json,.csv,.html,.rtf,.zip'

function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2)
}

function parseRubricItems(text: string): RubricItem[] {
  const parsed = JSON.parse(text)
  if (!Array.isArray(parsed)) throw new Error('Rubric JSON must be an array.')
  return parsed as RubricItem[]
}

function rubricTotal(items: RubricItem[]) {
  return items.reduce((sum, item) => sum + Number(item.points || 0), 0)
}

function scorePercent(record: Pick<EvaluationResult, 'overall_score' | 'overall_out_of' | 'score_percent'>) {
  if (typeof record.score_percent === 'number') return record.score_percent
  const score = Number(record.overall_score || 0)
  const outOf = Number(record.overall_out_of || 0)
  return outOf > 0 ? Number(((score / outOf) * 100).toFixed(2)) : 0
}

function fmtPercent(value: number | undefined) {
  return `${Number(value || 0).toFixed(1)}%`
}

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

function safeDateInputValue(value: string) {
  const text = String(value || '').trim()
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : ''
}

function formatTimestamp(value?: string) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString()
}

function formatShortDate(value?: string) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString()
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function listToMultiline(list?: string[]) {
  return (list || []).join('\n')
}

function multilineToList(text: string) {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

function cloneRecord(record: EvaluationResult | null) {
  if (!record) return null
  return JSON.parse(JSON.stringify(record)) as EvaluationResult
}

function normalizeEditedRecord(record: EvaluationResult) {
  const next = cloneRecord(record) || { items_results: [] }
  const items = (next.items_results || []).map((item) => {
    const maxPoints = Math.max(0, Number(item.points || 0))
    const earned = clamp(Number(item.earned_points || 0), 0, maxPoints)
    return {
      ...item,
      points: maxPoints,
      earned_points: Number(earned.toFixed(2)),
      rationale: String(item.rationale || '').trim(),
      suggestions: multilineToList(Array.isArray(item.suggestions) ? item.suggestions.join('\n') : String(item.suggestions || '')),
    }
  })
  const overallScore = Number(items.reduce((sum, item) => sum + Number(item.earned_points || 0), 0).toFixed(2))
  const overallOutOf = Number(items.reduce((sum, item) => sum + Number(item.points || 0), 0).toFixed(2))
  return {
    ...next,
    items_results: items,
    overall_score: overallScore,
    overall_out_of: overallOutOf,
    score_percent: overallOutOf > 0 ? Number(((overallScore / overallOutOf) * 100).toFixed(2)) : 0,
    manual_reviewed: true,
    updated_at: new Date().toISOString(),
  }
}

function rubricNeedsReference(items: RubricItem[]) {
  return items.some((item) => {
    const grounding = String(item.grounding || '').trim().toLowerCase()
    return grounding === 'reference' || grounding === 'hybrid'
  })
}

// ── File chips ──────────────────────────────────────────────────────────────

function FileChips({ files, onRemove }: { files: File[]; onRemove: (i: number) => void }) {
  if (files.length === 0) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.5rem' }}>
      {files.map((file, i) => (
        <span
          key={`${file.name}-${file.size}-${i}`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.35rem',
            background: 'var(--mist)',
            border: '1px solid var(--line)',
            borderRadius: 8,
            padding: '0.22rem 0.55rem',
            fontSize: '0.82rem',
            color: 'var(--ink)',
          }}
        >
          {file.name}
          <button
            type="button"
            onClick={() => onRemove(i)}
            title={`Remove ${file.name}`}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--ink-soft)',
              padding: 0,
              lineHeight: 1,
              fontSize: '0.9rem',
            }}
          >
            ✕
          </button>
        </span>
      ))}
    </div>
  )
}

// ── Visual rubric item editor ───────────────────────────────────────────────

function RubricTable({
  items,
  source,
  onChange,
}: {
  items: RubricItem[]
  source: 'assignment' | 'teacher_key'
  onChange: (items: RubricItem[]) => void
}) {
  function update(index: number, patch: Partial<RubricItem>) {
    onChange(items.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }

  function remove(index: number) {
    onChange(items.filter((_, i) => i !== index))
  }

  function addItem() {
    const base: RubricItem =
      source === 'teacher_key'
        ? { item_origin: 'teacher_key', name: '', description: '', expected_answer: '', points: 5, mode: 'exact', grounding: '' }
        : { item_origin: 'assignment', name: '', description: '', points: 5, grounding: 'ai' }
    onChange([...items, base])
  }

  if (items.length === 0) {
    return (
      <div style={{ color: 'var(--ink-soft)', padding: '0.75rem 0' }}>
        No items yet. Generate a rubric above or{' '}
        <button type="button" className="btn btn--ghost" style={{ padding: '0.2rem 0.65rem', fontSize: '0.85rem' }} onClick={addItem}>
          add one manually
        </button>
        .
      </div>
    )
  }

  return (
    <div>
      {items.map((item, index) => {
        const isExact = item.mode === 'exact'
        const showGrounding = source === 'assignment' || !isExact
        return (
          <div
            key={index}
            style={{
              border: '1px solid var(--line)',
              borderRadius: 14,
              padding: '0.9rem 1rem',
              background: 'rgba(255,255,255,0.6)',
              marginBottom: '0.65rem',
            }}
          >
            {/* Header row */}
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: '0.55rem' }}>
              {/* Name */}
              <div style={{ flex: '2 1 160px' }}>
                <label style={{ fontSize: '0.76rem', color: 'var(--ink-soft)', display: 'block', marginBottom: 2 }}>
                  Question / Name
                </label>
                <input
                  value={item.name || ''}
                  onChange={(e) => update(index, { name: e.target.value })}
                  placeholder="e.g. Question 1"
                  style={{ width: '100%' }}
                />
              </div>
              {/* Points */}
              <div style={{ flex: '0 0 72px' }}>
                <label style={{ fontSize: '0.76rem', color: 'var(--ink-soft)', display: 'block', marginBottom: 2 }}>
                  Points
                </label>
                <input
                  type="number"
                  min={0}
                  value={item.points ?? 0}
                  onChange={(e) => update(index, { points: Number(e.target.value) })}
                  style={{ width: '100%' }}
                />
              </div>
              {/* Type (teacher_key only) */}
              {source === 'teacher_key' && (
                <div style={{ flex: '0 0 140px' }}>
                  <label style={{ fontSize: '0.76rem', color: 'var(--ink-soft)', display: 'block', marginBottom: 2 }}>
                    Type
                  </label>
                  <select
                    value={item.mode || 'exact'}
                    onChange={(e) => {
                      const mode = e.target.value as 'exact' | 'conceptual'
                      update(index, { mode, grounding: mode === 'exact' ? '' : (item.grounding || 'ai') })
                    }}
                    style={{ width: '100%' }}
                  >
                    <option value="exact">MCQ / Exact</option>
                    <option value="conceptual">QA / Conceptual</option>
                  </select>
                </div>
              )}
              {/* Grounding */}
              {showGrounding && (
                <div style={{ flex: '0 0 130px' }}>
                  <label style={{ fontSize: '0.76rem', color: 'var(--ink-soft)', display: 'block', marginBottom: 2 }}>
                    Grounding
                  </label>
                  <select
                    value={item.grounding || 'ai'}
                    onChange={(e) => update(index, { grounding: e.target.value })}
                    style={{ width: '100%' }}
                  >
                    <option value="ai">AI reasoning</option>
                    <option value="reference">Reference only</option>
                    <option value="hybrid">Hybrid</option>
                  </select>
                </div>
              )}
              {/* Delete */}
              <button
                type="button"
                onClick={() => remove(index)}
                title="Remove this item"
                style={{
                  alignSelf: 'flex-end',
                  background: 'none',
                  border: '1px solid var(--line)',
                  borderRadius: 8,
                  cursor: 'pointer',
                  color: 'var(--ink-soft)',
                  padding: '0.28rem 0.55rem',
                  fontSize: '0.85rem',
                  lineHeight: 1,
                }}
              >
                ✕
              </button>
            </div>

            {/* Description */}
            <div style={{ marginBottom: '0.45rem' }}>
              <label style={{ fontSize: '0.76rem', color: 'var(--ink-soft)', display: 'block', marginBottom: 2 }}>
                Description / Criteria
              </label>
              <textarea
                rows={2}
                value={item.description || ''}
                onChange={(e) => update(index, { description: e.target.value })}
                placeholder="What this item tests…"
                style={{ width: '100%', resize: 'vertical' }}
              />
            </div>

            {/* Expected answer (teacher_key only) */}
            {source === 'teacher_key' && (
              <div>
                <label style={{ fontSize: '0.76rem', color: 'var(--ink-soft)', display: 'block', marginBottom: 2 }}>
                  {isExact ? 'Correct answer (e.g. "A", "B", "True")' : 'Model answer / key ideas to cover'}
                </label>
                <input
                  value={item.expected_answer || ''}
                  onChange={(e) => update(index, { expected_answer: e.target.value })}
                  placeholder={isExact ? 'A' : 'Key concepts the student should address…'}
                  style={{ width: '100%' }}
                />
              </div>
            )}
          </div>
        )
      })}
      <button type="button" className="btn btn--ghost" onClick={addItem} style={{ marginTop: '0.25rem' }}>
        + Add item
      </button>
    </div>
  )
}

// ── Result card ─────────────────────────────────────────────────────────────

function ResultCard({
  record,
  onApply,
  onSave,
  saving = false,
}: {
  record: EvaluationResult | null
  onApply?: (record: EvaluationResult) => void
  onSave?: (record: EvaluationResult) => void | Promise<void>
  saving?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<EvaluationResult | null>(cloneRecord(record))

  useEffect(() => {
    setEditing(false)
    setDraft(cloneRecord(record))
  }, [record])

  if (!record || !draft) return null

  const current = editing ? draft : record
  const pct = Math.round(scorePercent(current))

  function updateItem(index: number, patch: Partial<NonNullable<EvaluationResult['items_results']>[number]>) {
    setDraft((prev) => {
      if (!prev) return prev
      const items = [...(prev.items_results || [])]
      items[index] = { ...items[index], ...patch }
      return normalizeEditedRecord({ ...prev, items_results: items })
    })
  }

  async function handleSave() {
    if (!draft) return
    const normalized = normalizeEditedRecord(draft)
    onApply?.(normalized)
    if (onSave) await onSave(normalized)
    setDraft(normalized)
    setEditing(false)
  }

  function handleCancel() {
    setDraft(cloneRecord(record))
    setEditing(false)
  }

  return (
    <div className="panel" style={{ marginTop: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
        <h2 style={{ margin: 0, fontSize: '1.1rem' }}>{current.title || 'Grading result'}</h2>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {!editing && <button type="button" className="btn btn--ghost" onClick={() => setEditing(true)}>Fine-tune grading</button>}
          {editing && <button type="button" className="btn btn--ghost" onClick={handleCancel}>Cancel</button>}
          {editing && <button type="button" className="btn btn--primary" disabled={saving} onClick={() => void handleSave()}>{saving ? 'Saving...' : onSave ? 'Save review changes' : 'Apply review changes'}</button>}
        </div>
      </div>
      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
        <span className="pill pill--ok">
          {current.overall_score ?? 0} / {current.overall_out_of ?? 0}
          {Number.isFinite(pct) ? ` (${pct}%)` : ''}
        </span>
        {current.manual_reviewed && <span className="pill">teacher-reviewed</span>}
        {current.history_type && <span className="pill">{current.history_type === 'batch' || current.history_type === 'batch_submission' ? 'batch submission' : 'single submission'}</span>}
        {current.batch_name && <span className="pill">{current.batch_name}</span>}
        {current.batch_rank && current.batch_size ? <span className="pill">rank #{current.batch_rank} of {current.batch_size}</span> : null}
        {current.timestamp && <span className="pill">{formatTimestamp(current.timestamp)}</span>}
        {current.updated_at && <span className="pill">updated {formatTimestamp(current.updated_at)}</span>}
      </div>

      {(current.items_results || []).map((item, index) => {
        const earned = item.earned_points ?? 0
        const max = item.points ?? 0
        const ok = max > 0 && earned >= max
        const partial = max > 0 && earned > 0 && earned < max
        return (
          <div
            key={`${item.name || 'item'}-${index}`}
            style={{
              border: `1px solid ${ok ? 'rgba(34,139,34,0.25)' : partial ? 'rgba(200,140,0,0.25)' : 'var(--line)'}`,
              borderRadius: 14,
              padding: '1rem',
              background: ok
                ? 'rgba(240,255,240,0.7)'
                : partial
                  ? 'rgba(255,250,230,0.7)'
                  : 'rgba(255,255,255,0.6)',
              marginBottom: '0.85rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.35rem' }}>
              <strong>{item.name || `Item ${index + 1}`}</strong>
              {!editing ? (
                <span style={{ fontWeight: 600, color: ok ? '#228b22' : partial ? '#b08000' : 'var(--ink-soft)' }}>
                  {earned} / {max}
                </span>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                  <input
                    type="number"
                    min={0}
                    max={Number(max || 0)}
                    step="0.25"
                    value={Number(earned || 0)}
                    onChange={(e) => updateItem(index, { earned_points: Number(e.target.value) })}
                    style={{ width: 90 }}
                  />
                  <span style={{ color: 'var(--ink-soft)', fontSize: '0.88rem' }}>/ {max}</span>
                </div>
              )}
            </div>

            {item.description && <p style={{ margin: '0 0 0.45rem', color: 'var(--ink-soft)', fontSize: '0.9rem' }}>{item.description}</p>}

            <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginBottom: '0.45rem' }}>
              {item.item_origin && <span className="pill">{item.item_origin}</span>}
              {item.mode && <span className="pill">{item.mode}</span>}
              {item.grounding && <span className="pill">{item.grounding}</span>}
            </div>

            {item.expected_answer && (
              <p style={{ margin: '0.35rem 0', fontSize: '0.9rem' }}>
                <strong>Expected:</strong> {item.expected_answer}
              </p>
            )}

            {!editing ? (
              <>
                {item.rationale && (
                  <p style={{ margin: '0.35rem 0', fontSize: '0.9rem' }}>
                    <strong>Rationale:</strong> {item.rationale}
                  </p>
                )}
                {(item.suggestions || []).length > 0 && (
                  <div style={{ marginTop: '0.5rem' }}>
                    <strong style={{ fontSize: '0.88rem' }}>Suggestions</strong>
                    <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.2rem', fontSize: '0.88rem' }}>
                      {(item.suggestions || []).map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              <div style={{ display: 'grid', gap: '0.65rem', marginTop: '0.5rem' }}>
                <div>
                  <label style={{ fontSize: '0.82rem', color: 'var(--ink-soft)', display: 'block', marginBottom: 4 }}>Teacher feedback / rationale</label>
                  <textarea
                    rows={3}
                    value={String(item.rationale || '')}
                    onChange={(e) => updateItem(index, { rationale: e.target.value })}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '0.82rem', color: 'var(--ink-soft)', display: 'block', marginBottom: 4 }}>Suggestions (one per line)</label>
                  <textarea
                    rows={3}
                    value={listToMultiline(item.suggestions || [])}
                    onChange={(e) => updateItem(index, { suggestions: multilineToList(e.target.value) })}
                  />
                </div>
              </div>
            )}

            {(item.matched_key_ideas || []).length > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                <strong style={{ color: '#228b22', fontSize: '0.88rem' }}>Covered</strong>
                <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.2rem', fontSize: '0.88rem' }}>
                  {(item.matched_key_ideas || []).map((idea, i) => <li key={i}>{idea}</li>)}
                </ul>
              </div>
            )}
            {(item.missing_key_ideas || []).length > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                <strong style={{ color: '#b08000', fontSize: '0.88rem' }}>Missing</strong>
                <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.2rem', fontSize: '0.88rem' }}>
                  {(item.missing_key_ideas || []).map((idea, i) => <li key={i}>{idea}</li>)}
                </ul>
              </div>
            )}
            {(item.misconceptions || []).length > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                <strong style={{ color: '#c0392b', fontSize: '0.88rem' }}>Misconceptions</strong>
                <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.2rem', fontSize: '0.88rem' }}>
                  {(item.misconceptions || []).map((idea, i) => <li key={i}>{idea}</li>)}
                </ul>
              </div>
            )}
            {(item.evidence || []).length > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                <strong style={{ fontSize: '0.88rem' }}>Evidence</strong>
                <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.2rem', fontSize: '0.88rem' }}>
                  {(item.evidence || []).map((ev, i) => (
                    <li key={i}>
                      {ev.quote}
                      {ev.source ? ` [${ev.source}]` : ''}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Library doc list with checkboxes + delete ────────────────────────────────

function DocList({
  docs,
  selectedIds,
  onChange,
  onDelete,
  loading,
}: {
  docs: DocRow[]
  selectedIds: string[]
  onChange: (ids: string[]) => void
  onDelete: (doc: DocRow) => void
  loading: boolean
}) {
  function toggle(id: string) {
    onChange(selectedIds.includes(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id])
  }

  if (loading) return <p style={{ color: 'var(--ink-soft)', fontSize: '0.9rem' }}>Loading library…</p>
  if (docs.length === 0)
    return <p style={{ color: 'var(--ink-soft)', fontSize: '0.9rem' }}>No documents yet — upload above.</p>

  return (
    <div
      style={{
        border: '1px solid var(--line)',
        borderRadius: 10,
        overflow: 'hidden',
        maxHeight: 240,
        overflowY: 'auto',
      }}
    >
      {docs.map((doc, i) => {
        const selected = selectedIds.includes(doc.document_id)
        return (
          <div
            key={doc.document_id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.6rem',
              padding: '0.45rem 0.75rem',
              background: selected ? 'rgba(30,58,95,0.06)' : i % 2 === 0 ? 'rgba(255,255,255,0.7)' : 'rgba(248,246,242,0.7)',
              borderBottom: i < docs.length - 1 ? '1px solid var(--line)' : 'none',
              cursor: 'pointer',
            }}
            onClick={() => toggle(doc.document_id)}
          >
            <input
              type="checkbox"
              checked={selected}
              onChange={() => toggle(doc.document_id)}
              onClick={(e) => e.stopPropagation()}
              style={{ flexShrink: 0, cursor: 'pointer' }}
            />
            <span style={{ flex: 1, fontSize: '0.88rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {doc.title}
            </span>
            <span
              style={{
                fontSize: '0.72rem',
                background: 'var(--mist)',
                border: '1px solid var(--line)',
                borderRadius: 5,
                padding: '0.1rem 0.35rem',
                color: 'var(--ink-soft)',
                flexShrink: 0,
              }}
            >
              {doc.filetype}
            </span>
            <button
              type="button"
              title={`Delete ${doc.title}`}
              onClick={(e) => { e.stopPropagation(); onDelete(doc) }}
              style={{
                flexShrink: 0,
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: '#c0392b',
                fontSize: '0.85rem',
                padding: '0.1rem 0.3rem',
                borderRadius: 4,
                lineHeight: 1,
              }}
            >
              🗑
            </button>
          </div>
        )
      })}
    </div>
  )
}

// ── Source panel (for assignment, teacher key, reference) ───────────────────

function SourcePanel({
  title,
  subtitle,
  selectedIds,
  setSelectedIds,
  manualText,
  setManualText,
  docs,
  docsLoading,
  onUpload,
  onDirectParse,
  onRefresh,
  onDelete,
}: {
  title: string
  subtitle: string
  selectedIds: string[]
  setSelectedIds: (ids: string[]) => void
  manualText: string
  setManualText: (v: string) => void
  docs: DocRow[]
  docsLoading: boolean
  onUpload: (files: FileList | null) => void
  onDirectParse: (files: FileList | null) => void
  onRefresh: () => void
  onDelete: (doc: DocRow) => void
}) {
  const panelId = title.replace(/\s+/g, '-').toLowerCase()
  const selectedCount = selectedIds.filter((id) => docs.some((d) => d.document_id === id)).length
  return (
    <div className="panel" style={{ marginBottom: '1rem' }}>
      <h2 style={{ margin: '0 0 0.5rem', fontSize: '1.08rem' }}>{title}</h2>
      <p style={{ margin: '0 0 1rem', color: 'var(--ink-soft)', fontSize: '0.92rem' }}>{subtitle}</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
        <div className="field">
          <label htmlFor={`${panelId}-upload`}>Upload to library</label>
          <input
            id={`${panelId}-upload`}
            type="file"
            multiple
            accept={LIBRARY_ACCEPT}
            onChange={(e) => onUpload(e.target.files)}
          />
        </div>
        <div className="field">
          <label htmlFor={`${panelId}-direct`}>Use directly (no library save)</label>
          <input
            id={`${panelId}-direct`}
            type="file"
            multiple
            accept={PARSE_ACCEPT}
            onChange={(e) => onDirectParse(e.target.files)}
          />
        </div>
      </div>

      <div className="field">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.4rem' }}>
          <label style={{ margin: 0 }}>Library documents</label>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            {selectedCount > 0 && (
              <span className="pill pill--ok" style={{ fontSize: '0.78rem' }}>{selectedCount} selected</span>
            )}
            <button type="button" className="btn btn--ghost" style={{ fontSize: '0.78rem', padding: '0.15rem 0.5rem' }} onClick={onRefresh} disabled={docsLoading}>
              {docsLoading ? '…' : 'Refresh'}
            </button>
          </div>
        </div>
        <DocList docs={docs} selectedIds={selectedIds} onChange={setSelectedIds} onDelete={onDelete} loading={docsLoading} />
      </div>

      <div className="field">
        <label htmlFor={`${panelId}-text`}>Or paste text directly</label>
        <textarea
          id={`${panelId}-text`}
          rows={7}
          value={manualText}
          onChange={(e) => setManualText(e.target.value)}
          placeholder="Paste content here if you prefer not to upload a file…"
        />
      </div>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export function GradePage() {
  const location = useLocation()
  const [tab, setTab] = useState<'assignment' | 'teacher' | 'presets' | 'grade' | 'history'>('assignment')

  const [docs, setDocs] = useState<DocRow[]>([])
  const [docsLoading, setDocsLoading] = useState(false)

  // Assignment rubric
  const [assignmentText, setAssignmentText] = useState('')
  const [assignmentDocIds, setAssignmentDocIds] = useState<string[]>([])
  const [assignmentItems, setAssignmentItems] = useState<RubricItem[]>([])
  const [assignmentItemsJson, setAssignmentItemsJson] = useState('[]')
  const [assignmentShowJson, setAssignmentShowJson] = useState(false)

  // Teacher key rubric
  const [teacherKeyText, setTeacherKeyText] = useState('')
  const [teacherKeyDocIds, setTeacherKeyDocIds] = useState<string[]>([])
  const [teacherItems, setTeacherItems] = useState<RubricItem[]>([])
  const [teacherItemsJson, setTeacherItemsJson] = useState('[]')
  const [teacherShowJson, setTeacherShowJson] = useState(false)

  const [totalPoints, setTotalPoints] = useState(100)
  const [gradeSource, setGradeSource] = useState<'assignment' | 'teacher_key'>('assignment')
  const [presetSource, setPresetSource] = useState<'assignment' | 'teacher_key'>('assignment')
  const [presetName, setPresetName] = useState('')
  const [selectedPreset, setSelectedPreset] = useState('')
  const [presets, setPresets] = useState<Record<string, EvaluationPreset>>({})

  // Reference
  const [referenceDocIds, setReferenceDocIds] = useState<string[]>([])
  const [referenceText, setReferenceText] = useState('')

  // Single submission
  const [singleSubmissionText, setSingleSubmissionText] = useState('')
  const [singleSubmissionDocIds, setSingleSubmissionDocIds] = useState<string[]>([])
  const [singleTitle, setSingleTitle] = useState('Web submission')
  const [gradeResult, setGradeResult] = useState<EvaluationResult | null>(null)

  // Batch
  const [batchFiles, setBatchFiles] = useState<File[]>([])
  const batchInputRef = useRef<HTMLInputElement>(null)
  const [batchName, setBatchName] = useState('')
  const [batchResults, setBatchResults] = useState<EvaluationResult[]>([])
  const [selectedBatchIndex, setSelectedBatchIndex] = useState(0)

  const [saveHistory, setSaveHistory] = useState(true)
  const [history, setHistory] = useState<EvaluationResult[]>([])
  const [historyBatches, setHistoryBatches] = useState<HistoryBatch[]>([])
  const [historyStats, setHistoryStats] = useState<HistoryStats>({})
  const [selectedHistoryIndex, setSelectedHistoryIndex] = useState(0)
  const [selectedHistoryBatchIndex, setSelectedHistoryBatchIndex] = useState(0)
  const [historyDateFrom, setHistoryDateFrom] = useState('')
  const [historyDateTo, setHistoryDateTo] = useState('')
  const [historySearch, setHistorySearch] = useState('')
  const [historyTypeFilter, setHistoryTypeFilter] = useState<'all' | 'single' | 'batch'>('all')

  const [loading, setLoading] = useState(false)
  const [savingReview, setSavingReview] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const activeItems = gradeSource === 'teacher_key' ? teacherItems : assignmentItems
  const activeItemsNeedReference = rubricNeedsReference(activeItems)
  const hasReferenceMaterial = referenceDocIds.length > 0 || referenceText.trim().length > 0
  const selectedBatchRecord = batchResults[selectedBatchIndex] || null
  const batchAveragePercent = batchResults.length
    ? batchResults.reduce((sum, record) => sum + scorePercent(record), 0) / batchResults.length
    : 0
  const batchHighestPercent = batchResults.length
    ? Math.max(...batchResults.map((record) => scorePercent(record)))
    : 0
  const batchLowestPercent = batchResults.length
    ? Math.min(...batchResults.map((record) => scorePercent(record)))
    : 0
  const selectedHistoryRecord = history[selectedHistoryIndex] || null
  const selectedHistoryBatch = historyBatches[selectedHistoryBatchIndex] || null
  const selectedHistoryBatchRecords = selectedHistoryBatch?.records || []

  // Keep JSON in sync when items change via visual editor
  function setAssignmentItemsWithSync(items: RubricItem[]) {
    setAssignmentItems(items)
    setAssignmentItemsJson(prettyJson(items))
  }
  function setTeacherItemsWithSync(items: RubricItem[]) {
    setTeacherItems(items)
    setTeacherItemsJson(prettyJson(items))
  }

  useEffect(() => { void bootstrap() }, [])

  useEffect(() => {
    const state = location.state as { rubric?: RubricItem[]; origin?: string } | null
    if (!state?.rubric?.length) return
    if (state.origin === 'teacher_key') {
      setTeacherItemsWithSync(state.rubric)
      setGradeSource('teacher_key')
    } else {
      setAssignmentItemsWithSync(state.rubric)
      setGradeSource('assignment')
    }
    setTab('grade')
    setMessage('Rubric loaded from Generate.')
    window.history.replaceState({}, '')
  }, [location.state])

  async function refreshDocs() {
    setDocsLoading(true)
    try {
      setDocs(await apiJson<DocRow[]>('/documents/local'))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to refresh documents.')
    } finally {
      setDocsLoading(false)
    }
  }

  async function deleteDoc(doc: DocRow) {
    if (!window.confirm(`Delete "${doc.title}" from the library? This cannot be undone.`)) return
    setError(null); setMessage(null)
    try {
      await apiJson(`/documents/${encodeURIComponent(doc.document_id)}`, { method: 'DELETE' })
      // Deselect from all pickers if it was selected
      const id = doc.document_id
      setAssignmentDocIds((prev) => prev.filter((x) => x !== id))
      setTeacherKeyDocIds((prev) => prev.filter((x) => x !== id))
      setReferenceDocIds((prev) => prev.filter((x) => x !== id))
      setSingleSubmissionDocIds((prev) => prev.filter((x) => x !== id))
      await refreshDocs()
      setMessage(`"${doc.title}" deleted from library.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete document.')
    }
  }

  async function refreshHistory(overrides?: Partial<{ dateFrom: string; dateTo: string; search: string; historyType: 'all' | 'single' | 'batch'; selectedRecordId: string; selectedBatchId: string }>) {
    try {
      const dateFrom = overrides?.dateFrom ?? historyDateFrom
      const dateTo = overrides?.dateTo ?? historyDateTo
      const search = overrides?.search ?? historySearch
      const historyType = overrides?.historyType ?? historyTypeFilter
      const selectedRecordId = overrides?.selectedRecordId ?? String(history[selectedHistoryIndex]?.id || '')
      const selectedBatchId = overrides?.selectedBatchId ?? String(historyBatches[selectedHistoryBatchIndex]?.batch_id || '')
      const params = new URLSearchParams({ limit: '1000' })
      if (dateFrom) params.set('date_from', dateFrom)
      if (dateTo) params.set('date_to', dateTo)
      if (search.trim()) params.set('search', search.trim())
      if (historyType !== 'all') params.set('history_type', historyType)

      const res = await apiJson<HistoryResponse>(`/evaluation/history?${params.toString()}`)
      const nextRecords = res.records || []
      const nextBatches = res.batches || []
      setHistory(nextRecords)
      setHistoryBatches(nextBatches)
      setHistoryStats(res.stats || {})
      const nextRecordIndex = selectedRecordId ? nextRecords.findIndex((record) => record.id === selectedRecordId) : -1
      const nextBatchIndex = selectedBatchId ? nextBatches.findIndex((batch) => batch.batch_id === selectedBatchId) : -1
      setSelectedHistoryIndex(nextRecordIndex >= 0 ? nextRecordIndex : 0)
      setSelectedHistoryBatchIndex(nextBatchIndex >= 0 ? nextBatchIndex : 0)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load history.')
    }
  }

  async function bootstrap() {
    setDocsLoading(true)
    try {
      const [docsRes, presetsRes, historyRes] = await Promise.all([
        apiJson<DocRow[]>('/documents/local'),
        apiJson<{ presets: Record<string, EvaluationPreset> }>('/evaluation/presets'),
        apiJson<HistoryResponse>('/evaluation/history?limit=1000'),
      ])
      setDocs(docsRes)
      setPresets(presetsRes.presets || {})
      setHistory(historyRes.records || [])
      setHistoryBatches(historyRes.batches || [])
      setHistoryStats(historyRes.stats || {})
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load grading workspace.')
    } finally {
      setDocsLoading(false)
    }
  }

  async function uploadToLibrary(files: FileList | null, setSelectedIds?: (ids: string[]) => void) {
    if (!files?.length) return
    setError(null); setMessage(null)
    const previousIds = new Set(docs.map((d) => d.document_id))
    try {
      await apiUpload('/documents/upload', files)
      const docsRes = await apiJson<DocRow[]>('/documents/local')
      setDocs(docsRes)
      const added = docsRes.filter((d) => !previousIds.has(d.document_id)).map((d) => d.document_id)
      if (added.length > 0 && setSelectedIds) {
        setSelectedIds(added)
        setMessage('File(s) uploaded and selected.')
      } else {
        setMessage('Files uploaded to library.')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to upload files.')
    }
  }

  async function parseSourceUpload(
    files: FileList | null,
    currentText: string,
    setText: (v: string) => void,
    label: string
  ) {
    if (!files?.length) return
    setLoading(true); setError(null); setMessage(null)
    try {
      const formData = new FormData()
      Array.from(files).forEach((f) => formData.append('files', f))
      const res = await apiFormJson<ParsedUploadListResponse>('/evaluation/uploads/parse', formData)
      if (!res.items.length) throw new Error('No supported files could be parsed.')
      const appended = res.items.map((item) => `=== FILE: ${item.name} ===\n${item.text}`).join('\n\n')
      setText([currentText.trim(), appended].filter(Boolean).join('\n\n'))
      setMessage(`Loaded ${res.items.length} ${label} file(s).`)
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to parse ${label} file.`)
    } finally {
      setLoading(false)
    }
  }

  async function parseSingleSubmissionFile(files: FileList | null) {
    if (!files?.length) return
    setLoading(true); setError(null); setMessage(null)
    try {
      const formData = new FormData()
      formData.append('files', files[0])
      const res = await apiFormJson<ParsedUploadListResponse>('/evaluation/uploads/parse', formData)
      const parsed = res.items[0]
      if (!parsed) throw new Error('File could not be parsed.')
      setSingleSubmissionText(parsed.text)
      setSingleSubmissionDocIds([])
      setSingleTitle(parsed.name)
      setMessage(`Loaded submission from ${parsed.name}.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to parse submission file.')
    } finally {
      setLoading(false)
    }
  }

  function addBatchFiles(files: FileList | null) {
    if (!files?.length) return
    const incoming = Array.from(files)
    setBatchFiles((prev) => {
      const existing = new Set(prev.map((f) => `${f.name}:${f.size}`))
      return [...prev, ...incoming.filter((f) => !existing.has(`${f.name}:${f.size}`))]
    })
    if (batchInputRef.current) batchInputRef.current.value = ''
  }

  function removeBatchFile(index: number) {
    setBatchFiles((prev) => prev.filter((_, i) => i !== index))
  }

  async function generateAssignmentRubric() {
    setLoading(true); setError(null); setMessage(null)
    try {
      for await (const event of apiStream<RubricStreamEvent>('/evaluation/rubric/from-assignment/stream', {
        method: 'POST',
        body: JSON.stringify({ text: assignmentText, document_ids: assignmentDocIds, total_points: totalPoints }),
      })) {
        if (event.error) throw new Error(event.error)
        if (event.message) setMessage(event.message)
        if (event.done) {
          setAssignmentItemsWithSync(event.items || [])
          setGradeSource('assignment')
          setMessage('Assignment rubric generated.')
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate assignment rubric.')
    } finally {
      setLoading(false)
    }
  }

  async function generateTeacherRubric() {
    setLoading(true); setError(null); setMessage(null)
    try {
      for await (const event of apiStream<RubricStreamEvent>('/evaluation/rubric/from-teacher-key/stream', {
        method: 'POST',
        body: JSON.stringify({ text: teacherKeyText, document_ids: teacherKeyDocIds, total_points: totalPoints }),
      })) {
        if (event.error) throw new Error(event.error)
        if (event.message) setMessage(event.message)
        if (event.done) {
          setTeacherItemsWithSync(event.items || [])
          setGradeSource('teacher_key')
          setMessage('Teacher-key rubric generated. Review items below then go to Grade.')
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate teacher-key rubric.')
    } finally {
      setLoading(false)
    }
  }

  async function gradeSingleSubmission() {
    if (!activeItems.length) { setError('Generate or load a rubric first.'); return }
    if (activeItemsNeedReference && !hasReferenceMaterial) {
      setError('Please upload, select, or paste reference material before grading because one or more criteria use reference or hybrid grounding.')
      return
    }
    setLoading(true); setError(null); setMessage(null); setGradeResult(null)
    try {
      const res = await apiJson<GradeResponse>(
        '/evaluation/grade',
        {
          method: 'POST',
          body: JSON.stringify({
            submission_text: singleSubmissionText,
            submission_document_ids: singleSubmissionDocIds,
            items: activeItems,
            teacher_key_text: teacherKeyText,
            teacher_key_document_ids: teacherKeyDocIds,
            reference_text: referenceText,
            reference_document_ids: referenceDocIds,
            result_title: singleTitle || 'Web submission',
            save_history: saveHistory,
          }),
        },
        180_000
      )
      setGradeResult(res.record || null)
      if (saveHistory) await refreshHistory()
      setMessage('Graded successfully.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to grade submission.')
    } finally {
      setLoading(false)
    }
  }

  async function gradeBatchSubmissions() {
    if (!activeItems.length) { setError('Generate or load a rubric first.'); return }
    if (batchFiles.length === 0) { setError('Add at least one submission file.'); return }
    if (activeItemsNeedReference && !hasReferenceMaterial) {
      setError('Please upload, select, or paste reference material before grading because one or more criteria use reference or hybrid grounding.')
      return
    }
    setLoading(true); setError(null); setMessage(null); setBatchResults([]); setSelectedBatchIndex(0)
    try {
      const formData = new FormData()
      batchFiles.forEach((f) => formData.append('files', f))
      const parsed = await apiFormJson<ParsedUploadListResponse>('/evaluation/uploads/parse', formData)
      const submissions = (parsed.items || [])
        .map((item) => ({ title: item.name || 'Submission', submission_text: item.text || '', submission_document_ids: [] }))
        .filter((s) => s.submission_text.trim())
      if (submissions.length === 0) throw new Error('None of the selected files produced usable text.')

      const res = await apiJson<BatchGradeResponse>(
        '/evaluation/grade/batch',
        {
          method: 'POST',
          body: JSON.stringify({
            submissions,
            items: activeItems,
            teacher_key_text: teacherKeyText,
            teacher_key_document_ids: teacherKeyDocIds,
            reference_text: referenceText,
            reference_document_ids: referenceDocIds,
            batch_name: batchName.trim(),
            save_history: saveHistory,
          }),
        },
        180_000
      )
      const records = res.records || []
      setBatchResults(records)
      setSelectedBatchIndex(0)
      if (saveHistory) await refreshHistory()
      setMessage(`Batch grading done: ${records.length} submission(s)${res.batch_name ? ` in "${res.batch_name}"` : ''}.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to grade batch submissions.')
    } finally {
      setLoading(false)
    }
  }

  function applyJsonEdits(source: 'assignment' | 'teacher_key') {
    try {
      const raw = source === 'assignment' ? assignmentItemsJson : teacherItemsJson
      const parsed = parseRubricItems(raw)
      if (source === 'assignment') setAssignmentItems(parsed)
      else setTeacherItems(parsed)
      setMessage('JSON applied.')
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invalid rubric JSON.')
    }
  }

  async function savePreset() {
    const items = presetSource === 'teacher_key' ? teacherItems : assignmentItems
    if (!presetName.trim()) { setError('Enter a preset name.'); return }
    if (!items.length) { setError('Generate a rubric first.'); return }
    setLoading(true); setError(null); setMessage(null)
    try {
      const res = await apiJson<{ presets: Record<string, EvaluationPreset> }>(
        `/evaluation/presets/${encodeURIComponent(presetName.trim())}`,
        { method: 'PUT', body: JSON.stringify({ origin: presetSource, items, total_points: totalPoints }) }
      )
      setPresets(res.presets || {})
      setSelectedPreset(presetName.trim())
      setMessage(`Preset "${presetName.trim()}" saved.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save preset.')
    } finally {
      setLoading(false)
    }
  }

  function loadPreset(name: string) {
    const preset = presets[name]
    if (!preset) return
    if ((preset.origin || 'assignment') === 'teacher_key') {
      setTeacherItemsWithSync(preset.items || [])
      setGradeSource('teacher_key')
    } else {
      setAssignmentItemsWithSync(preset.items || [])
      setGradeSource('assignment')
    }
    setPresetName(name)
    setSelectedPreset(name)
    setTab('grade')
    setMessage(`Preset "${name}" loaded.`)
  }

  async function deletePreset(name: string) {
    setLoading(true); setError(null); setMessage(null)
    try {
      const res = await apiJson<{ presets: Record<string, EvaluationPreset> }>(
        `/evaluation/presets/${encodeURIComponent(name)}`,
        { method: 'DELETE' }
      )
      setPresets(res.presets || {})
      if (selectedPreset === name) setSelectedPreset('')
      setMessage(`Preset "${name}" deleted.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete preset.')
    } finally {
      setLoading(false)
    }
  }

  async function clearAllHistory() {
    setLoading(true); setError(null); setMessage(null)
    try {
      await apiJson('/evaluation/history', { method: 'DELETE' })
      setHistory([])
      setHistoryBatches([])
      setHistoryStats({})
      setSelectedHistoryIndex(0)
      setSelectedHistoryBatchIndex(0)
      setMessage('History cleared.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to clear history.')
    } finally {
      setLoading(false)
    }
  }

  function applySingleReview(record: EvaluationResult) {
    setGradeResult(record)
  }

  function applyBatchReview(record: EvaluationResult) {
    setBatchResults((prev) => prev.map((entry, index) => (index === selectedBatchIndex ? record : entry)))
  }

  function applyHistoryReview(record: EvaluationResult) {
    setHistory((prev) => prev.map((entry, index) => (index === selectedHistoryIndex ? record : entry)))
    setHistoryBatches((prev) =>
      prev.map((batch, batchIndex) =>
        batchIndex !== selectedHistoryBatchIndex
          ? batch
          : {
              ...batch,
              records: (batch.records || []).map((entry) => (entry.id === record.id ? record : entry)),
            }
      )
    )
  }

  async function saveReviewedRecord(record: EvaluationResult) {
    if (!record.id) {
      setError('This result does not have a saved history id yet.')
      return
    }
    setSavingReview(true); setError(null); setMessage(null)
    try {
      await apiJson(`/evaluation/history/${encodeURIComponent(record.id)}`, {
        method: 'PUT',
        body: JSON.stringify({ record }),
      })
      await refreshHistory({ selectedRecordId: String(record.id || ''), selectedBatchId: String(record.batch_id || '') })
      setMessage(`Saved teacher review changes for "${record.title || 'submission'}".`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save review changes.')
    } finally {
      setSavingReview(false)
    }
  }

  async function downloadSingleRecord(record: EvaluationResult, fmt: 'txt' | 'docx' | 'html') {
    setError(null); setMessage(null)
    try {
      const { blob, filename } = await apiDownload(
        `/evaluation/export/single/${fmt}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ record }),
        }
      )
      downloadBlob(blob, filename)
      setMessage(`Downloaded ${fmt.toUpperCase()} report for "${record.title || 'submission'}".`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to download report.')
    }
  }

  async function downloadBatchRecords(records: EvaluationResult[], fmt: 'txt' | 'docx' | 'html', batchName?: string) {
    setError(null); setMessage(null)
    try {
      const { blob, filename } = await apiDownload(
        `/evaluation/export/batch/${fmt}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ records }),
        }
      )
      downloadBlob(blob, filename)
      setMessage(`Downloaded ${fmt.toUpperCase()} batch report${batchName ? ` for "${batchName}"` : ''}.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to download batch report.')
    }
  }

  async function applyHistoryFilters() {
    if (historyDateFrom && historyDateTo && historyDateFrom > historyDateTo) {
      setError('The "from" date must be before the "to" date.')
      return
    }
    setLoading(true); setError(null); setMessage(null)
    try {
      await refreshHistory()
      setMessage('History filters applied.')
    } finally {
      setLoading(false)
    }
  }

  async function resetHistoryFilters() {
    setHistoryDateFrom('')
    setHistoryDateTo('')
    setHistorySearch('')
    setHistoryTypeFilter('all')
    setLoading(true); setError(null); setMessage(null)
    try {
      await refreshHistory({ dateFrom: '', dateTo: '', search: '', historyType: 'all' })
      setMessage('History filters reset.')
    } finally {
      setLoading(false)
    }
  }

  // ── Rubric panel (shared for assignment and teacher_key) ──────────────────

  function renderRubricPanel(
    source: 'assignment' | 'teacher_key',
    items: RubricItem[],
    setItems: (items: RubricItem[]) => void,
    json: string,
    setJson: (v: string) => void,
    showJson: boolean,
    setShowJson: (v: boolean) => void
  ) {
    const label = source === 'teacher_key' ? 'Teacher-key' : 'Assignment'
    return (
      <div className="panel" style={{ marginTop: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.85rem' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '1.08rem' }}>{label} rubric items</h2>
            <span style={{ color: 'var(--ink-soft)', fontSize: '0.88rem' }}>
              {items.length} item(s) · {rubricTotal(items)} / {totalPoints} pts
            </span>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn--ghost"
              style={{ fontSize: '0.85rem', padding: '0.3rem 0.75rem' }}
              onClick={() => setShowJson(!showJson)}
            >
              {showJson ? 'Visual editor' : 'View / edit JSON'}
            </button>
            <button
              type="button"
              className="btn btn--accent"
              style={{ fontSize: '0.85rem', padding: '0.3rem 0.75rem' }}
              onClick={() => setGradeSource(source)}
            >
              Use for grading
            </button>
          </div>
        </div>

        {!showJson && (
          <RubricTable items={items} source={source} onChange={setItems} />
        )}

        {showJson && (
          <div>
            <textarea
              rows={16}
              value={json}
              onChange={(e) => setJson(e.target.value)}
              style={{ fontFamily: 'monospace', fontSize: '0.82rem' }}
            />
            <button type="button" className="btn btn--ghost" style={{ marginTop: '0.5rem' }} onClick={() => applyJsonEdits(source)}>
              Apply JSON edits
            </button>
          </div>
        )}
      </div>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      <h1 className="page-title">Flexible Grader</h1>
      <p className="page-sub">
        Upload a teacher key or assignment to generate a rubric, then grade student submissions — single or batch.
      </p>

      {error && <div className="error" style={{ whiteSpace: 'pre-wrap' }}>{error}</div>}
      {message && <div className="success">{message}</div>}

      <div className="tabs">
        {(['assignment', 'teacher', 'presets', 'grade', 'history'] as const).map((t) => (
          <button
            key={t}
            type="button"
            className={tab === t ? 'active' : ''}
            onClick={() => setTab(t)}
          >
            {t === 'assignment' ? 'Assignment rubric' :
              t === 'teacher' ? 'Teacher key' :
              t === 'presets' ? 'Presets' :
              t === 'grade' ? 'Grade' : 'History'}
          </button>
        ))}
      </div>

      {/* ── Assignment tab ── */}
      {tab === 'assignment' && (
        <>
          <SourcePanel
            title="Assignment source"
            subtitle="Upload or paste your assignment. The AI will create a rubric from it."
            selectedIds={assignmentDocIds}
            setSelectedIds={setAssignmentDocIds}
            manualText={assignmentText}
            setManualText={setAssignmentText}
            docs={docs}
            docsLoading={docsLoading}
            onUpload={(f) => void uploadToLibrary(f, setAssignmentDocIds)}
            onDirectParse={(f) => void parseSourceUpload(f, assignmentText, setAssignmentText, 'assignment')}
            onRefresh={() => void refreshDocs()}
            onDelete={(doc) => void deleteDoc(doc)}
          />
          <div className="panel">
            <div className="field">
              <label htmlFor="assignment-total-points">Total points</label>
              <input
                id="assignment-total-points"
                type="number"
                min={1}
                max={2000}
                value={totalPoints}
                onChange={(e) => setTotalPoints(Number(e.target.value))}
              />
            </div>
            <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void generateAssignmentRubric()}>
              {loading ? 'Generating…' : 'Generate assignment rubric'}
            </button>
          </div>
          {renderRubricPanel(
            'assignment',
            assignmentItems,
            setAssignmentItemsWithSync,
            assignmentItemsJson,
            (v) => setAssignmentItemsJson(v),
            assignmentShowJson,
            setAssignmentShowJson
          )}
        </>
      )}

      {/* ── Teacher key tab ── */}
      {tab === 'teacher' && (
        <>
          <div className="panel" style={{ marginBottom: '1rem', background: 'rgba(30,58,95,0.04)', border: '1px solid rgba(30,58,95,0.12)' }}>
            <p style={{ margin: 0, fontSize: '0.92rem', color: 'var(--ink-soft)' }}>
              <strong style={{ color: 'var(--ink)' }}>How it works:</strong> Upload your teacher key (MCQ answer sheet, QA model answers, etc.).
              The AI extracts each question, its correct answer, and point value, then creates rubric items automatically.
              MCQ questions get <strong>exact</strong> mode (deterministic matching), QA questions get <strong>conceptual</strong> mode (semantic grading).
            </p>
          </div>

          <SourcePanel
            title="Teacher key source"
            subtitle="Upload or paste your teacher key. Supports any format — MCQ, QA, mixed."
            selectedIds={teacherKeyDocIds}
            setSelectedIds={setTeacherKeyDocIds}
            manualText={teacherKeyText}
            setManualText={setTeacherKeyText}
            docs={docs}
            docsLoading={docsLoading}
            onUpload={(f) => void uploadToLibrary(f, setTeacherKeyDocIds)}
            onDirectParse={(f) => void parseSourceUpload(f, teacherKeyText, setTeacherKeyText, 'teacher key')}
            onRefresh={() => void refreshDocs()}
            onDelete={(doc) => void deleteDoc(doc)}
          />

          <div className="panel">
            <div className="field">
              <label htmlFor="teacher-total-points">Total points</label>
              <input
                id="teacher-total-points"
                type="number"
                min={1}
                max={2000}
                value={totalPoints}
                onChange={(e) => setTotalPoints(Number(e.target.value))}
              />
              <p style={{ margin: '0.35rem 0 0', color: 'var(--ink-soft)', fontSize: '0.85rem' }}>
                If per-question points are in the teacher key, the AI will use those. Otherwise it distributes evenly.
              </p>
            </div>
            <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void generateTeacherRubric()}>
              {loading ? 'Generating…' : 'Generate teacher-key rubric'}
            </button>
          </div>

          {renderRubricPanel(
            'teacher_key',
            teacherItems,
            setTeacherItemsWithSync,
            teacherItemsJson,
            (v) => setTeacherItemsJson(v),
            teacherShowJson,
            setTeacherShowJson
          )}
        </>
      )}

      {/* ── Grade tab ── */}
      {tab === 'grade' && (
        <>
          <div className="panel" style={{ marginBottom: '1rem' }}>
            <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.08rem' }}>Active rubric</h2>
            <div className="field">
              <label htmlFor="grade-source">Rubric source</label>
              <select
                id="grade-source"
                value={gradeSource}
                onChange={(e) => setGradeSource(e.target.value as 'assignment' | 'teacher_key')}
              >
                <option value="assignment">Assignment rubric ({assignmentItems.length} items)</option>
                <option value="teacher_key">Teacher-key rubric ({teacherItems.length} items)</option>
              </select>
            </div>
            <div style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
              <span className={`pill ${activeItems.length > 0 ? 'pill--ok' : 'pill--warn'}`}>
                {activeItems.length} item(s)
              </span>
              <span className="pill">
                {rubricTotal(activeItems)} / {totalPoints} pts
              </span>
              {activeItems.filter((i) => i.mode === 'exact').length > 0 && (
                <span className="pill">{activeItems.filter((i) => i.mode === 'exact').length} MCQ exact</span>
              )}
              {activeItems.filter((i) => i.mode === 'conceptual').length > 0 && (
                <span className="pill">{activeItems.filter((i) => i.mode === 'conceptual').length} QA conceptual</span>
              )}
            </div>
            <label style={{ display: 'inline-flex', gap: '0.5rem', alignItems: 'center' }}>
              <input type="checkbox" checked={saveHistory} onChange={(e) => setSaveHistory(e.target.checked)} />
              Save results to history
            </label>
          </div>

          {/* Reference sources */}
          <div className="panel" style={{ marginBottom: '1rem' }}>
            <h2 style={{ margin: '0 0 0.5rem', fontSize: '1.08rem' }}>Reference material (optional)</h2>
            <p style={{ margin: '0 0 0.85rem', color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
              Used for rubric items with grounding set to "reference" or "hybrid".
            </p>
            {activeItemsNeedReference && !hasReferenceMaterial && (
              <div
                style={{
                  marginBottom: '0.85rem',
                  padding: '0.75rem 0.9rem',
                  borderRadius: 12,
                  border: '1px solid rgba(200,140,0,0.25)',
                  background: 'rgba(255,248,225,0.85)',
                  color: '#8a5d00',
                  fontSize: '0.9rem',
                }}
              >
                This rubric has at least one criterion using <strong>reference</strong> or <strong>hybrid</strong> grounding.
                Please upload, select, or paste reference material before grading.
              </div>
            )}
            <div className="field">
              <label htmlFor="ref-upload">Upload reference directly</label>
              <input
                id="ref-upload"
                type="file"
                multiple
                accept={PARSE_ACCEPT}
                onChange={(e) => void parseSourceUpload(e.target.files, referenceText, setReferenceText, 'reference')}
              />
            </div>
            <div className="field">
              <label>Or select from library</label>
              <p style={{ margin: '0.2rem 0 0.45rem', color: 'var(--ink-soft)', fontSize: '0.82rem' }}>
                Library documents use the system RAG retriever during grading.
              </p>
              <DocList docs={docs} selectedIds={referenceDocIds} onChange={setReferenceDocIds} onDelete={(doc) => void deleteDoc(doc)} loading={docsLoading} />
            </div>
            <div className="field">
              <label htmlFor="ref-text">Paste reference text</label>
              <textarea
                id="ref-text"
                rows={5}
                value={referenceText}
                onChange={(e) => setReferenceText(e.target.value)}
                placeholder="Paste course material, lecture notes, etc. here…"
              />
            </div>
          </div>

          {/* Single submission */}
          <div className="panel" style={{ marginBottom: '1rem' }}>
            <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.08rem' }}>Single submission</h2>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="field">
                <label htmlFor="single-upload">Upload submission file</label>
                <input
                  id="single-upload"
                  type="file"
                  accept={PARSE_ACCEPT}
                  onChange={(e) => void parseSingleSubmissionFile(e.target.files)}
                />
              </div>
              <div className="field">
                <label>Or use library document</label>
                <DocList docs={docs} selectedIds={singleSubmissionDocIds} onChange={setSingleSubmissionDocIds} onDelete={(doc) => void deleteDoc(doc)} loading={docsLoading} />
              </div>
            </div>
            <div className="field">
              <label htmlFor="single-title">Result title</label>
              <input id="single-title" value={singleTitle} onChange={(e) => setSingleTitle(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="single-text">
                Submission text
                <span style={{ fontWeight: 400, color: 'var(--ink-soft)', fontSize: '0.82rem', marginLeft: '0.5rem' }}>
                  — verify this matches what you uploaded. Edit if something looks wrong.
                </span>
              </label>
              <textarea
                id="single-text"
                rows={12}
                value={singleSubmissionText}
                onChange={(e) => setSingleSubmissionText(e.target.value)}
                placeholder="Paste or upload the student submission…"
                style={{ fontFamily: 'monospace', fontSize: '0.82rem' }}
              />
              {singleSubmissionText && (
                <p style={{ margin: '0.3rem 0 0', fontSize: '0.8rem', color: 'var(--ink-soft)' }}>
                  {singleSubmissionText.length.toLocaleString()} characters · {singleSubmissionText.split('\n').length} lines
                </p>
              )}
            </div>
            <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void gradeSingleSubmission()}>
              {loading ? 'Grading…' : 'Grade single submission'}
            </button>
          </div>

          <ResultCard record={gradeResult} onApply={applySingleReview} onSave={saveHistory ? saveReviewedRecord : undefined} saving={savingReview} />

          {/* Batch grading */}
          <div className="panel" style={{ marginBottom: '1rem' }}>
            <h2 style={{ margin: '0 0 0.5rem', fontSize: '1.08rem' }}>Batch grading</h2>
            <p style={{ margin: '0 0 0.85rem', color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
              Upload multiple submission files and grade them all at once.
            </p>
            <div className="field">
              <label htmlFor="batch-name">Batch name</label>
              <input
                id="batch-name"
                value={batchName}
                onChange={(e) => setBatchName(e.target.value)}
                placeholder="Midterm Section A - April 26"
              />
            </div>
            <div className="field">
              <label htmlFor="batch-upload">Add submission files</label>
              <input
                id="batch-upload"
                ref={batchInputRef}
                type="file"
                multiple
                accept={PARSE_ACCEPT}
                onChange={(e) => addBatchFiles(e.target.files)}
              />
            </div>

            <div style={{ display: 'flex', gap: '0.65rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
              <span className={`pill ${batchFiles.length > 0 ? 'pill--ok' : 'pill--warn'}`}>
                {batchFiles.length} file(s) queued
              </span>
              {batchFiles.length > 0 && (
                <button
                  type="button"
                  className="btn btn--ghost"
                  style={{ fontSize: '0.82rem', padding: '0.2rem 0.6rem' }}
                  onClick={() => setBatchFiles([])}
                >
                  Clear all
                </button>
              )}
              {batchResults.length > 0 && <span className="pill pill--ok">{batchResults.length} result(s)</span>}
            </div>

            <FileChips files={batchFiles} onRemove={removeBatchFile} />

            <div style={{ marginTop: '0.85rem' }}>
              <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void gradeBatchSubmissions()}>
                {loading ? 'Grading…' : 'Grade batch submissions'}
              </button>
            </div>
          </div>

          {batchResults.length > 0 && (
            <div className="panel" style={{ marginTop: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.85rem' }}>
                <div>
                  <h2 style={{ margin: '0 0 0.35rem', fontSize: '1.08rem' }}>Batch results</h2>
                  <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap' }}>
                    <span className="pill pill--ok">{batchResults.length} submissions</span>
                    <span className="pill">Average {fmtPercent(batchAveragePercent)}</span>
                    <span className="pill">High {fmtPercent(batchHighestPercent)}</span>
                    <span className="pill">Low {fmtPercent(batchLowestPercent)}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <button type="button" className="btn btn--ghost" onClick={() => void downloadBatchRecords(batchResults, 'txt', batchName || 'Current batch')}>TXT report</button>
                  <button type="button" className="btn btn--ghost" onClick={() => void downloadBatchRecords(batchResults, 'docx', batchName || 'Current batch')}>DOCX report</button>
                  <button type="button" className="btn btn--ghost" onClick={() => void downloadBatchRecords(batchResults, 'html', batchName || 'Current batch')}>HTML report</button>
                </div>
              </div>
              <div className="field">
                <label htmlFor="batch-select">Review result</label>
                <select
                  id="batch-select"
                  value={selectedBatchIndex}
                  onChange={(e) => setSelectedBatchIndex(Number(e.target.value))}
                >
                  {batchResults.map((r, i) => (
                    <option key={r.id || i} value={i}>
                      {r.title} — {r.overall_score}/{r.overall_out_of}
                    </option>
                  ))}
                </select>
              </div>
              {selectedBatchRecord && (
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                  <button type="button" className="btn btn--ghost" onClick={() => void downloadSingleRecord(selectedBatchRecord, 'txt')}>Selected TXT</button>
                  <button type="button" className="btn btn--ghost" onClick={() => void downloadSingleRecord(selectedBatchRecord, 'docx')}>Selected DOCX</button>
                  <button type="button" className="btn btn--ghost" onClick={() => void downloadSingleRecord(selectedBatchRecord, 'html')}>Selected HTML</button>
                </div>
              )}
              <ResultCard record={selectedBatchRecord} onApply={applyBatchReview} onSave={saveHistory ? saveReviewedRecord : undefined} saving={savingReview} />
            </div>
          )}
        </>
      )}

      {/* ── Presets tab ── */}
      {tab === 'presets' && (
        <>
          <div className="panel" style={{ marginBottom: '1rem' }}>
            <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.08rem' }}>Save current rubric as preset</h2>
            <div className="field">
              <label htmlFor="preset-source">Which rubric to save</label>
              <select
                id="preset-source"
                value={presetSource}
                onChange={(e) => setPresetSource(e.target.value as 'assignment' | 'teacher_key')}
              >
                <option value="assignment">Assignment rubric</option>
                <option value="teacher_key">Teacher-key rubric</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="preset-name">Preset name</label>
              <input id="preset-name" value={presetName} onChange={(e) => setPresetName(e.target.value)} />
            </div>
            <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void savePreset()}>
              {loading ? 'Saving…' : 'Save preset'}
            </button>
          </div>

          <div className="panel">
            <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.08rem' }}>Saved presets</h2>
            {Object.keys(presets).length === 0 && <p style={{ color: 'var(--ink-soft)' }}>No presets saved yet.</p>}
            {Object.entries(presets).map(([name, preset]) => (
              <div
                key={name}
                style={{
                  border: '1px solid var(--line)',
                  borderRadius: 14,
                  padding: '1rem',
                  background: 'rgba(255,255,255,0.6)',
                  marginBottom: '0.75rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                  <div>
                    <strong>{name}</strong>
                    <div style={{ color: 'var(--ink-soft)', fontSize: '0.88rem' }}>
                      {(preset.origin || 'assignment') === 'teacher_key' ? 'Teacher-key' : 'Assignment'} · {preset.items?.length || 0} items · {preset.total_points} pts
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button type="button" className="btn btn--ghost" onClick={() => loadPreset(name)}>Load</button>
                    <button type="button" className="btn btn--ghost" onClick={() => void deletePreset(name)}>Delete</button>
                  </div>
                </div>
                {/* Mini preview of items */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                  {(preset.items || []).slice(0, 6).map((item, i) => (
                    <span key={i} className="pill" style={{ fontSize: '0.78rem' }}>
                      {item.name || `Item ${i + 1}`} · {item.points}pt{item.mode ? ` · ${item.mode}` : ''}
                    </span>
                  ))}
                  {(preset.items || []).length > 6 && (
                    <span className="pill" style={{ fontSize: '0.78rem' }}>+{(preset.items || []).length - 6} more</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* ── History tab ── */}
      {tab === 'history' && (
        <>
          <div className="panel" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.85rem' }}>
              <div>
                <h2 style={{ margin: '0 0 0.35rem', fontSize: '1.08rem' }}>Grading history</h2>
                <p style={{ margin: 0, color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
                  Review saved submissions, grouped batches, date ranges, and downloadable reports.
                </p>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                <button type="button" className="btn btn--ghost" onClick={() => void refreshHistory()}>Refresh</button>
                <button type="button" className="btn btn--ghost" disabled={loading || history.length === 0} onClick={() => void clearAllHistory()}>Clear history</button>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="history-date-from">From</label>
                <input
                  id="history-date-from"
                  type="date"
                  value={safeDateInputValue(historyDateFrom)}
                  onChange={(e) => setHistoryDateFrom(e.target.value)}
                />
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="history-date-to">To</label>
                <input
                  id="history-date-to"
                  type="date"
                  value={safeDateInputValue(historyDateTo)}
                  onChange={(e) => setHistoryDateTo(e.target.value)}
                />
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="history-type-filter">Type</label>
                <select
                  id="history-type-filter"
                  value={historyTypeFilter}
                  onChange={(e) => setHistoryTypeFilter(e.target.value as 'all' | 'single' | 'batch')}
                >
                  <option value="all">All saved work</option>
                  <option value="single">Singles only</option>
                  <option value="batch">Batch submissions only</option>
                </select>
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="history-search">Search</label>
                <input
                  id="history-search"
                  value={historySearch}
                  onChange={(e) => setHistorySearch(e.target.value)}
                  placeholder="Search batch name or submission title"
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
              <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void applyHistoryFilters()}>
                {loading ? 'Loading...' : 'Apply filters'}
              </button>
              <button type="button" className="btn btn--ghost" disabled={loading} onClick={() => void resetHistoryFilters()}>
                Reset filters
              </button>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '0.85rem', marginBottom: '1rem' }}>
            {[
              { label: 'Saved submissions', value: String(historyStats.total_records || 0) },
              { label: 'Saved batches', value: String(historyStats.batch_count || 0) },
              { label: 'Average', value: fmtPercent(historyStats.average_percent) },
              { label: 'Highest', value: fmtPercent(historyStats.highest_percent) },
              { label: 'Lowest', value: fmtPercent(historyStats.lowest_percent) },
            ].map((card) => (
              <div
                key={card.label}
                className="panel"
                style={{
                  margin: 0,
                  padding: '0.9rem 1rem',
                  background: 'linear-gradient(180deg, rgba(255,255,255,0.88), rgba(245,241,232,0.92))',
                }}
              >
                <div style={{ color: 'var(--ink-soft)', fontSize: '0.82rem', marginBottom: '0.25rem' }}>{card.label}</div>
                <div style={{ fontSize: '1.45rem', fontWeight: 700 }}>{card.value}</div>
              </div>
            ))}
          </div>

          <div className="panel" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
              <div>
                <h2 style={{ margin: '0 0 0.35rem', fontSize: '1.08rem' }}>Batch sessions</h2>
                <p style={{ margin: 0, color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
                  Open a saved batch to see summary statistics and export the full run.
                </p>
              </div>
              {selectedHistoryBatch && selectedHistoryBatchRecords.length > 0 && (
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <button type="button" className="btn btn--ghost" onClick={() => void downloadBatchRecords(selectedHistoryBatchRecords, 'txt', selectedHistoryBatch.batch_name)}>TXT batch</button>
                  <button type="button" className="btn btn--ghost" onClick={() => void downloadBatchRecords(selectedHistoryBatchRecords, 'docx', selectedHistoryBatch.batch_name)}>DOCX batch</button>
                  <button type="button" className="btn btn--ghost" onClick={() => void downloadBatchRecords(selectedHistoryBatchRecords, 'html', selectedHistoryBatch.batch_name)}>HTML batch</button>
                </div>
              )}
            </div>

            {historyBatches.length === 0 ? (
              <p style={{ color: 'var(--ink-soft)', margin: 0 }}>No saved batches match the current filters.</p>
            ) : (
              <>
                <div className="field">
                  <label htmlFor="history-batch-select">Saved batch</label>
                  <select
                    id="history-batch-select"
                    value={selectedHistoryBatchIndex}
                    onChange={(e) => setSelectedHistoryBatchIndex(Number(e.target.value))}
                  >
                    {historyBatches.map((batch, index) => (
                      <option key={batch.batch_id || index} value={index}>
                        {(batch.batch_name || `Batch ${index + 1}`)} - {batch.submission_count || 0} submissions - avg {fmtPercent(batch.average_percent)}
                      </option>
                    ))}
                  </select>
                </div>

                {selectedHistoryBatch && (
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <span className="pill pill--ok">{selectedHistoryBatch.submission_count || 0} submissions</span>
                    <span className="pill">Average {fmtPercent(selectedHistoryBatch.average_percent)}</span>
                    <span className="pill">High {fmtPercent(selectedHistoryBatch.highest_percent)}</span>
                    <span className="pill">Low {fmtPercent(selectedHistoryBatch.lowest_percent)}</span>
                    {selectedHistoryBatch.created_at && <span className="pill">{formatShortDate(selectedHistoryBatch.created_at)}</span>}
                  </div>
                )}
              </>
            )}
          </div>

          <div className="panel">
            {history.length === 0 && <p style={{ color: 'var(--ink-soft)' }}>No history saved yet.</p>}
            {history.length > 0 && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                  <div>
                    <h2 style={{ margin: '0 0 0.35rem', fontSize: '1.08rem' }}>Saved submissions</h2>
                    <p style={{ margin: 0, color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
                      Browse individual saved results and export a report for the selected submission.
                    </p>
                  </div>
                  {selectedHistoryRecord && (
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                      <button type="button" className="btn btn--ghost" onClick={() => void downloadSingleRecord(selectedHistoryRecord, 'txt')}>TXT report</button>
                      <button type="button" className="btn btn--ghost" onClick={() => void downloadSingleRecord(selectedHistoryRecord, 'docx')}>DOCX report</button>
                      <button type="button" className="btn btn--ghost" onClick={() => void downloadSingleRecord(selectedHistoryRecord, 'html')}>HTML report</button>
                    </div>
                  )}
                </div>
                <div className="field">
                  <label htmlFor="history-select">Saved result</label>
                  <select
                    id="history-select"
                    value={selectedHistoryIndex}
                    onChange={(e) => setSelectedHistoryIndex(Number(e.target.value))}
                  >
                    {history.map((r, i) => (
                      <option key={r.id || i} value={i}>
                        {r.title} — {r.overall_score}/{r.overall_out_of} — {r.timestamp}
                      </option>
                    ))}
                  </select>
                </div>
                <ResultCard record={selectedHistoryRecord} onApply={applyHistoryReview} onSave={saveReviewedRecord} saving={savingReview} />
              </>
            )}
          </div>
        </>
      )}
    </>
  )
}
