import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  apiDownload,
  apiFormJson,
  apiJson,
  apiPostEvaluationBatchGradeStream,
  apiStream,
  apiUpload,
} from '../api/client'
import type { EvaluationBatchGradeProgress } from '../api/client'

function formatDurationSeconds(totalSec: number): string {
  const s = Math.max(0, Math.floor(totalSec))
  const m = Math.floor(s / 60)
  const r = s % 60
  if (m === 0) return `${r}s`
  return `${m}m ${r}s`
}

function formatBatchGradeProgressLine(p: EvaluationBatchGradeProgress): string {
  const { completed, total, current_title, elapsed_sec, estimated_remaining_sec } = p
  if (total <= 0) return `Grading batch… ${formatDurationSeconds(elapsed_sec)} elapsed`
  const pct = Math.min(100, Math.round((completed / total) * 100))
  let rem: string
  if (estimated_remaining_sec == null) {
    rem = 'estimating time remaining…'
  } else if (estimated_remaining_sec <= 0 || completed >= total) {
    rem = 'finishing up…'
  } else {
    rem = `~${formatDurationSeconds(Math.ceil(estimated_remaining_sec))} remaining (estimate)`
  }
  const titleShort = current_title.length > 48 ? `${current_title.slice(0, 46)}…` : current_title
  return `${completed} of ${total} done (${pct}%) · ${rem} · ${formatDurationSeconds(Math.floor(elapsed_sec))} elapsed — ${titleShort}`
}

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

type RubricGenerationResponse = {
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

/** Extensions the API stores in the knowledge base for RAG (must match server ``ALLOWED_EXTENSIONS``). */
const LIBRARY_ACCEPT = '.pdf,.docx,.pptx,.txt,.md,.json'
const PARSE_ACCEPT = '.pdf,.docx,.pptx,.txt,.md,.json,.csv,.html,.rtf,.zip'
const MOODLE_XML_ACCEPT = '.xml'

type DocumentUploadRow = {
  filename: string
  stored_path: string
  filetype: string
  reused_existing?: boolean
}

function normalizeFsPath(p: string) {
  return p.replace(/\\/g, '/').toLowerCase()
}

function resolveDocIdsFromUploadRows(docsList: DocRow[], uploads: DocumentUploadRow[]): string[] {
  const ids: string[] = []
  for (const u of uploads) {
    const want = normalizeFsPath(u.stored_path)
    const base = (u.filename || '').split(/[/\\]/).pop()?.toLowerCase() || ''
    const hit =
      docsList.find((d) => normalizeFsPath(d.path) === want) ||
      (base ? docsList.find((d) => normalizeFsPath(d.path).endsWith(`/${base}`) || d.path.toLowerCase().endsWith(base)) : undefined)
    if (hit) ids.push(hit.document_id)
  }
  return ids
}

function isKbLibraryFile(f: File): boolean {
  const n = f.name.toLowerCase()
  return ['.pdf', '.docx', '.pptx', '.txt', '.md', '.json'].some((ext) => n.endsWith(ext))
}

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

function presetOriginLabel(origin?: string) {
  if (origin === 'teacher_key' || origin === 'qa') return 'QA'
  if (origin === 'mcq') return 'MCQ (Moodle)'
  return 'Assignment'
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
  source: 'assignment' | 'qa' | 'mcq'
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
      source === 'assignment'
        ? { item_origin: 'assignment', name: '', description: '', points: 5, grounding: 'ai' }
        : source === 'qa'
          ? {
              item_origin: 'teacher_key',
              name: '',
              description: '',
              expected_answer: '',
              points: 5,
              mode: 'conceptual',
              grounding: 'ai',
            }
          : { item_origin: 'teacher_key', name: '', description: '', expected_answer: '', points: 5, mode: 'exact', grounding: '' }
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
        const isExact = source === 'qa' ? false : item.mode === 'exact'
        const showGrounding = source === 'assignment' || source === 'qa'
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

            {/* Expected answer (QA + MCQ) */}
            {(source === 'qa' || source === 'mcq') && (
              <div>
                <label style={{ fontSize: '0.76rem', color: 'var(--ink-soft)', display: 'block', marginBottom: 2 }}>
                  {source === 'qa' ? 'Model answer / key ideas' : isExact ? 'Correct answer (e.g. "A", "B", "True")' : 'Model answer / key ideas to cover'}
                </label>
                {source === 'qa' ? (
                  <textarea
                    rows={3}
                    value={item.expected_answer || ''}
                    onChange={(e) => update(index, { expected_answer: e.target.value })}
                    placeholder="What a strong student response should include…"
                    style={{ width: '100%', resize: 'vertical' }}
                  />
                ) : (
                  <input
                    value={item.expected_answer || ''}
                    onChange={(e) => update(index, { expected_answer: e.target.value })}
                    placeholder={isExact ? 'A' : 'Key concepts the student should address…'}
                    style={{ width: '100%' }}
                  />
                )}
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
  onAddFiles,
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
  onAddFiles: (files: FileList | null) => void
  onRefresh: () => void
  onDelete: (doc: DocRow) => void
}) {
  const panelId = title.replace(/\s+/g, '-').toLowerCase()
  const selectedCount = selectedIds.filter((id) => docs.some((d) => d.document_id === id)).length
  return (
    <div className="panel" style={{ marginBottom: '1rem' }}>
      <h2 style={{ margin: '0 0 0.5rem', fontSize: '1.08rem' }}>{title}</h2>
      <p style={{ margin: '0 0 1rem', color: 'var(--ink-soft)', fontSize: '0.92rem' }}>{subtitle}</p>

      <div className="field">
        <label htmlFor={`${panelId}-add`}>Add files</label>
        <p style={{ margin: '0.25rem 0 0.5rem', color: 'var(--ink-soft)', fontSize: '0.82rem' }}>
          PDF, Word, PowerPoint, text, and JSON are <strong>saved to your library</strong> for the system RAG retriever (duplicate uploads with identical content reuse the existing file). Other types are parsed into the text area only.
        </p>
        <input
          id={`${panelId}-add`}
          type="file"
          multiple
          accept={PARSE_ACCEPT}
          onChange={(e) => onAddFiles(e.target.files)}
        />
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
  const [tab, setTab] = useState<'assignment' | 'mcq' | 'qa' | 'presets' | 'grade' | 'history'>('assignment')

  const [docs, setDocs] = useState<DocRow[]>([])
  const [docsLoading, setDocsLoading] = useState(false)

  // Assignment rubric
  const [assignmentText, setAssignmentText] = useState('')
  const [assignmentDocIds, setAssignmentDocIds] = useState<string[]>([])
  const [assignmentItems, setAssignmentItems] = useState<RubricItem[]>([])
  const [assignmentItemsJson, setAssignmentItemsJson] = useState('[]')
  const [assignmentShowJson, setAssignmentShowJson] = useState(false)

  // QA rubric (open questions; teacher paste / docs — not Moodle MCQ)
  const [qaTeacherText, setQaTeacherText] = useState('')
  const [qaTeacherDocIds, setQaTeacherDocIds] = useState<string[]>([])
  const [qaItems, setQaItems] = useState<RubricItem[]>([])
  const [qaItemsJson, setQaItemsJson] = useState('[]')
  const [qaShowJson, setQaShowJson] = useState(false)
  const [qaDefaultGrounding, setQaDefaultGrounding] = useState<'ai' | 'reference' | 'hybrid'>('ai')

  // MCQ (Moodle XML key + deterministic compare)
  const [mcqItems, setMcqItems] = useState<RubricItem[]>([])
  const [mcqItemsJson, setMcqItemsJson] = useState('[]')
  const [mcqShowJson, setMcqShowJson] = useState(false)
  const [mcqKeyXml, setMcqKeyXml] = useState('')
  const [mcqStudentXml, setMcqStudentXml] = useState('')
  const [mcqBatchStudentXmls, setMcqBatchStudentXmls] = useState<Array<{ title: string; xml: string }>>([])
  const mcqBatchInputRef = useRef<HTMLInputElement>(null)

  const [totalPoints, setTotalPoints] = useState(100)
  const [gradeSource, setGradeSource] = useState<'assignment' | 'mcq' | 'qa'>('assignment')
  const [presetSource, setPresetSource] = useState<'assignment' | 'qa' | 'mcq'>('assignment')
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
  /** Live status while grading (batch uses server progress + ETA; single uses elapsed timer). */
  const [gradeProgressLine, setGradeProgressLine] = useState<string | null>(null)

  const activeItems =
    gradeSource === 'mcq' ? mcqItems : gradeSource === 'qa' ? qaItems : assignmentItems
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
  function setQaItemsWithSync(items: RubricItem[]) {
    const fixed = items.map((it) => {
      const g = String(it.grounding || '').trim().toLowerCase()
      const grounding = g === 'ai' || g === 'reference' || g === 'hybrid' ? g : 'ai'
      return { ...it, mode: 'conceptual', grounding }
    })
    setQaItems(fixed)
    setQaItemsJson(prettyJson(fixed))
  }
  function setMcqItemsWithSync(items: RubricItem[]) {
    setMcqItems(items)
    setMcqItemsJson(prettyJson(items))
  }

  useEffect(() => { void bootstrap() }, [])

  useEffect(() => {
    if (!error) return
    requestAnimationFrame(() => {
      document.getElementById('grade-flash-banner')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }, [error])

  useEffect(() => {
    const state = location.state as {
      rubric?: RubricItem[]
      origin?: string
      teacher_key_text?: string
      suggested_total_points?: number
      result_title_hint?: string
      importMessage?: string
    } | null
    if (!state?.rubric?.length) return
    if (state.origin === 'teacher_key' || state.origin === 'qa') {
      setQaItemsWithSync(state.rubric)
      setGradeSource('qa')
    } else if (state.origin === 'mcq') {
      setMcqItemsWithSync(state.rubric)
      setGradeSource('mcq')
    } else {
      setAssignmentItemsWithSync(state.rubric)
      setGradeSource('assignment')
    }
    if (typeof state.teacher_key_text === 'string' && state.teacher_key_text.trim()) {
      setQaTeacherText(state.teacher_key_text)
    }
    const stp = state.suggested_total_points
    if (typeof stp === 'number' && Number.isFinite(stp)) {
      const rounded = Math.round(stp)
      if (rounded >= 1 && rounded <= 2000) setTotalPoints(rounded)
    }
    if (typeof state.result_title_hint === 'string' && state.result_title_hint.trim()) {
      setSingleTitle(state.result_title_hint.trim())
    }
    setTab('grade')
    setMessage(state.importMessage || 'Rubric imported.')
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
      setQaTeacherDocIds((prev) => prev.filter((x) => x !== id))
      setReferenceDocIds((prev) => prev.filter((x) => x !== id))
      setSingleSubmissionDocIds((prev) => prev.filter((x) => x !== id))
      await refreshDocs()
      setMessage(`"${doc.title}" deleted from library.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete document.')
    }
  }

  async function refreshHistory(
    overrides?: Partial<{
      dateFrom: string
      dateTo: string
      search: string
      historyType: 'all' | 'single' | 'batch'
      selectedRecordId: string
      selectedBatchId: string
    }>,
    options?: { quiet?: boolean },
  ): Promise<boolean> {
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
      return true
    } catch (e) {
      if (!options?.quiet) {
        setError(e instanceof Error ? e.message : 'Failed to load history.')
      }
      return false
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

  async function ingestGradingSource(
    files: FileList | null,
    opts: {
      mergeDocIds: (ids: string[]) => void
      currentText: string
      setText: (v: string) => void
      label: string
    },
  ) {
    if (!files?.length) return
    const list = Array.from(files)
    setLoading(true); setError(null); setMessage(null)
    try {
      const kbList = list.filter(isKbLibraryFile)
      let uploadRows: DocumentUploadRow[] = []
      if (kbList.length) {
        uploadRows = (await apiUpload('/documents/upload', kbList)) as DocumentUploadRow[]
        const docsRes = await apiJson<DocRow[]>('/documents/local')
        setDocs(docsRes)
        const matched = resolveDocIdsFromUploadRows(docsRes, uploadRows)
        if (matched.length) opts.mergeDocIds(matched)
      }

      let parsedCount = 0
      let parseNote = ''
      try {
        const formData = new FormData()
        list.forEach((f) => formData.append('files', f))
        const res = await apiFormJson<ParsedUploadListResponse>('/evaluation/uploads/parse', formData)
        if (res.items?.length) {
          parsedCount = res.items.length
          const appended = res.items.map((item) => `=== FILE: ${item.name} ===\n${item.text}`).join('\n\n')
          opts.setText([opts.currentText.trim(), appended].filter(Boolean).join('\n\n'))
        }
      } catch (pe) {
        if (!kbList.length) throw pe
        parseNote = `Text extract failed (${pe instanceof Error ? pe.message : 'error'}); you can paste manually.`
      }

      const reused = uploadRows.some((r) => r.reused_existing)
      const parts: string[] = []
      if (kbList.length && uploadRows.length) {
        parts.push(
          reused
            ? 'Library: identical file(s) already indexed — reused for RAG (no duplicate saved).'
            : 'Library: file(s) saved for RAG and selected below.',
        )
      }
      if (parsedCount) parts.push(`Text: added extract from ${parsedCount} file(s).`)
      if (list.length > kbList.length) {
        parts.push(`${list.length - kbList.length} file(s) were only parsed (extension not stored in library).`)
      }
      if (parseNote) parts.push(parseNote)
      if (parts.length) setMessage(parts.join(' '))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add files.')
    } finally {
      setLoading(false)
    }
  }

  async function ingestSingleSubmissionFile(files: FileList | null) {
    if (!files?.length) return
    const f = files[0]
    setLoading(true); setError(null); setMessage(null)
    try {
      let reused = false
      if (isKbLibraryFile(f)) {
        const uploadRows = (await apiUpload('/documents/upload', [f])) as DocumentUploadRow[]
        const docsRes = await apiJson<DocRow[]>('/documents/local')
        setDocs(docsRes)
        const matched = resolveDocIdsFromUploadRows(docsRes, uploadRows)
        setSingleSubmissionDocIds(matched)
        reused = uploadRows.some((r) => r.reused_existing)
      } else {
        setSingleSubmissionDocIds([])
      }

      const formData = new FormData()
      formData.append('files', f)
      const res = await apiFormJson<ParsedUploadListResponse>('/evaluation/uploads/parse', formData)
      const parsed = res.items[0]
      if (!parsed) throw new Error('File could not be parsed.')
      setSingleSubmissionText(parsed.text)
      setSingleTitle(parsed.name)

      const libMsg = !isKbLibraryFile(f) ? '' : reused ? 'Matched existing library file (RAG). ' : 'Saved to library for RAG. '
      setMessage(`${libMsg}Loaded text from ${parsed.name}.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load submission file.')
    } finally {
      setLoading(false)
    }
  }

  async function loadTextFromXmlFile(files: FileList | null, setField: (v: string) => void, role: string) {
    if (!files?.length) return
    const f = files[0]
    if (!f.name.toLowerCase().endsWith('.xml')) {
      setError('Moodle MCQ requires a UTF-8 text file ending in .xml (Moodle quiz export).')
      return
    }
    setLoading(true); setError(null); setMessage(null)
    try {
      const text = await f.text()
      setField(text)
      setMessage(`Loaded ${role}: ${f.name}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not read the XML file.')
    } finally {
      setLoading(false)
    }
  }

  async function loadMcqRubricFromKeyXml() {
    const raw = mcqKeyXml.trim()
    if (!raw) {
      setError('Paste the Moodle answer-key XML or upload a .xml file first.')
      return
    }
    setLoading(true); setError(null); setMessage(null)
    try {
      const res = await apiJson<RubricGenerationResponse>('/evaluation/rubric/from-moodle-xml', {
        method: 'POST',
        body: JSON.stringify({ xml: raw }),
      })
      const items = res.items || []
      setMcqItemsWithSync(items)
      setGradeSource('mcq')
      const sum = rubricTotal(items)
      if (sum >= 1 && sum <= 2000) setTotalPoints(Math.round(sum))
      setMessage((res.summary && res.summary.join(' ')) || `Loaded ${items.length} MCQ item(s) from Moodle XML.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not parse Moodle XML key.')
    } finally {
      setLoading(false)
    }
  }

  async function addMcqBatchStudentXmlFiles(files: FileList | null) {
    if (!files?.length) return
    setError(null); setMessage(null)
    const list = Array.from(files).filter((f) => f.name.toLowerCase().endsWith('.xml'))
    if (list.length === 0) {
      setError('Add one or more files ending in .xml (Moodle quiz exports).')
      return
    }
    setLoading(true)
    try {
      const incoming: Array<{ title: string; xml: string }> = []
      for (const f of list) {
        const base = f.name.replace(/\.xml$/i, '') || 'Submission'
        incoming.push({ title: base, xml: await f.text() })
      }
      setMcqBatchStudentXmls((prev) => {
        const used = new Set(prev.map((p) => p.title))
        const merged = [...prev]
        for (const row of incoming) {
          let title = row.title
          let n = 2
          while (used.has(title)) {
            title = `${row.title} (${n})`
            n += 1
          }
          used.add(title)
          merged.push({ title, xml: row.xml })
        }
        return merged
      })
      setMessage(`Queued ${incoming.length} Moodle attempt file(s) for batch MCQ.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not read XML file(s).')
    } finally {
      setLoading(false)
      if (mcqBatchInputRef.current) mcqBatchInputRef.current.value = ''
    }
  }

  function removeMcqBatchStudent(index: number) {
    setMcqBatchStudentXmls((prev) => prev.filter((_, i) => i !== index))
  }

  async function gradeBatchMcq() {
    if (!mcqKeyXml.trim()) {
      setError('Load the answer key on the MCQ tab (paste or upload key XML) first.')
      return
    }
    if (mcqBatchStudentXmls.length === 0) {
      setError('Add at least one student Moodle .xml file to the batch queue.')
      return
    }
    setLoading(true); setError(null); setMessage(null); setBatchResults([]); setSelectedBatchIndex(0); setGradeResult(null)
    const nAttempts = mcqBatchStudentXmls.length
    const t0 = Date.now()
    const tick = window.setInterval(() => {
      setGradeProgressLine(
        `Grading ${nAttempts} Moodle attempt(s) · ${formatDurationSeconds((Date.now() - t0) / 1000)} elapsed`,
      )
    }, 500)
    try {
      const res = await apiJson<BatchGradeResponse>('/evaluation/grade/moodle-mcq/batch', {
        method: 'POST',
        body: JSON.stringify({
          key_xml: mcqKeyXml,
          submissions: mcqBatchStudentXmls.map((s) => ({ title: s.title, student_xml: s.xml })),
          batch_name: batchName.trim(),
          save_history: saveHistory,
        }),
      })
      const records = res.records || []
      setBatchResults(records)
      setSelectedBatchIndex(0)
      let histNote = ''
      if (saveHistory) {
        const okHist = await refreshHistory(undefined, { quiet: true })
        if (!okHist) histNote = ' History could not refresh — open the History tab and press Refresh.'
      }
      setMessage(`Moodle MCQ batch done: ${records.length} attempt(s)${res.batch_name ? ` in "${res.batch_name}"` : ''}.${histNote}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to grade Moodle MCQ batch.')
    } finally {
      window.clearInterval(tick)
      setGradeProgressLine(null)
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

  async function generateQaRubric() {
    setLoading(true); setError(null); setMessage(null)
    try {
      for await (const event of apiStream<RubricStreamEvent>('/evaluation/rubric/from-teacher-key/stream', {
        method: 'POST',
        body: JSON.stringify({
          text: qaTeacherText,
          document_ids: qaTeacherDocIds,
          total_points: totalPoints,
          default_grounding: qaDefaultGrounding,
        }),
      })) {
        if (event.error) throw new Error(event.error)
        if (event.message) setMessage(event.message)
        if (event.done) {
          setQaItemsWithSync(event.items || [])
          setGradeSource('qa')
          setMessage('QA rubric generated. Review items below, then use the Grade tab.')
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate QA rubric.')
    } finally {
      setLoading(false)
    }
  }

  async function gradeSingleSubmission() {
    if (gradeSource === 'mcq') {
      if (!mcqKeyXml.trim() || !mcqStudentXml.trim()) {
        setError('For MCQ, provide Moodle XML for both the answer key and the student attempt (paste or upload .xml).')
        return
      }
      setLoading(true); setError(null); setMessage(null); setGradeResult(null)
      const t0 = Date.now()
      const tick = window.setInterval(() => {
        setGradeProgressLine(`Grading Moodle MCQ · ${formatDurationSeconds((Date.now() - t0) / 1000)} elapsed`)
      }, 500)
      try {
        const res = await apiJson<GradeResponse>('/evaluation/grade/moodle-mcq', {
          method: 'POST',
          body: JSON.stringify({
            key_xml: mcqKeyXml,
            student_xml: mcqStudentXml,
            result_title: singleTitle || 'Moodle MCQ',
            save_history: saveHistory,
          }),
        })
        const record = res.record ?? null
        setGradeResult(record)
        if (!record) {
          setError(
            'The API returned no grading record. Check POST /evaluation/grade/moodle-mcq in the Network tab and confirm the backend is running.',
          )
          return
        }
        if (saveHistory) {
          const okHist = await refreshHistory(undefined, { quiet: true })
          setMessage(
            okHist
              ? 'MCQ graded (deterministic from Moodle XML).'
              : 'MCQ graded. History could not refresh — open the History tab and press Refresh.',
          )
        } else {
          setMessage('MCQ graded (deterministic from Moodle XML).')
        }
        requestAnimationFrame(() => {
          document.getElementById('grade-result-anchor')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        })
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to grade Moodle MCQ.')
      } finally {
        window.clearInterval(tick)
        setGradeProgressLine(null)
        setLoading(false)
      }
      return
    }

    if (!activeItems.length) { setError('Generate or load a rubric first.'); return }
    if (activeItemsNeedReference && !hasReferenceMaterial) {
      setError('Please upload, select, or paste reference material before grading because one or more criteria use reference or hybrid grounding.')
      return
    }
    if (!singleSubmissionText.trim() && singleSubmissionDocIds.length === 0) {
      setError(
        'Add submission text (paste or upload a file above) and/or select at least one library document that contains the student work. The server needs text to grade.',
      )
      return
    }
    setLoading(true); setError(null); setMessage(null); setGradeResult(null)
    const t0Open = Date.now()
    const tickOpen = window.setInterval(() => {
      setGradeProgressLine(`Grading with AI · ${formatDurationSeconds((Date.now() - t0Open) / 1000)} elapsed`)
    }, 500)
    try {
      const res = await apiJson<GradeResponse>('/evaluation/grade', {
        method: 'POST',
        body: JSON.stringify({
          submission_text: singleSubmissionText,
          submission_document_ids: singleSubmissionDocIds,
          items: activeItems,
          teacher_key_text: gradeSource === 'qa' ? qaTeacherText : '',
          teacher_key_document_ids: gradeSource === 'qa' ? qaTeacherDocIds : [],
          reference_text: referenceText,
          reference_document_ids: referenceDocIds,
          result_title: singleTitle || 'Web submission',
          save_history: saveHistory,
        }),
      })
      const record = res.record ?? null
      setGradeResult(record)
      if (!record) {
        setError(
          'The API returned no grading record. Check the browser Network tab for POST /evaluation/grade, confirm the backend is running, and verify GROQ_API_KEY in the API environment.',
        )
        return
      }
      if (saveHistory) {
        const okHist = await refreshHistory(undefined, { quiet: true })
        setMessage(
          okHist
            ? 'Graded successfully.'
            : 'Graded successfully. History could not refresh — open the History tab and press Refresh.',
        )
      } else {
        setMessage('Graded successfully.')
      }
      requestAnimationFrame(() => {
        document.getElementById('grade-result-anchor')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to grade submission.')
    } finally {
      window.clearInterval(tickOpen)
      setGradeProgressLine(null)
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
    let prepTick: ReturnType<typeof window.setInterval> | null = null
    const prepStarted = Date.now()
    prepTick = window.setInterval(() => {
      setGradeProgressLine(`Reading submission files · ${formatDurationSeconds((Date.now() - prepStarted) / 1000)} elapsed`)
    }, 400)
    try {
      const formData = new FormData()
      batchFiles.forEach((f) => formData.append('files', f))
      const parsed = await apiFormJson<ParsedUploadListResponse>('/evaluation/uploads/parse', formData)
      const submissions = (parsed.items || [])
        .map((item) => ({ title: item.name || 'Submission', submission_text: item.text || '', submission_document_ids: [] }))
        .filter((s) => s.submission_text.trim())
      if (submissions.length === 0) throw new Error('None of the selected files produced usable text.')

      if (prepTick) {
        window.clearInterval(prepTick)
        prepTick = null
      }
      setGradeProgressLine(`Grading ${submissions.length} submission(s) with AI…`)

      const streamBody = {
        submissions,
        items: activeItems,
        teacher_key_text: gradeSource === 'qa' ? qaTeacherText : '',
        teacher_key_document_ids: gradeSource === 'qa' ? qaTeacherDocIds : [],
        reference_text: referenceText,
        reference_document_ids: referenceDocIds,
        batch_name: batchName.trim(),
        save_history: saveHistory,
      }
      const res = (await apiPostEvaluationBatchGradeStream(streamBody, (p) => {
        setGradeProgressLine(formatBatchGradeProgressLine(p))
      })) as BatchGradeResponse
      const records = res.records || []
      setBatchResults(records)
      setSelectedBatchIndex(0)
      let histNote = ''
      if (saveHistory) {
        const okHist = await refreshHistory(undefined, { quiet: true })
        if (!okHist) histNote = ' History could not refresh — open the History tab and press Refresh.'
      }
      setMessage(`Batch grading done: ${records.length} submission(s)${res.batch_name ? ` in "${res.batch_name}"` : ''}.${histNote}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to grade batch submissions.')
    } finally {
      if (prepTick) window.clearInterval(prepTick)
      setGradeProgressLine(null)
      setLoading(false)
    }
  }

  function applyJsonEdits(source: 'assignment' | 'qa' | 'mcq') {
    try {
      const raw =
        source === 'assignment' ? assignmentItemsJson : source === 'qa' ? qaItemsJson : mcqItemsJson
      const parsed = parseRubricItems(raw)
      if (source === 'assignment') setAssignmentItemsWithSync(parsed)
      else if (source === 'qa') setQaItemsWithSync(parsed)
      else setMcqItemsWithSync(parsed)
      setMessage('JSON applied.')
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invalid rubric JSON.')
    }
  }

  async function savePreset() {
    const items =
      presetSource === 'assignment' ? assignmentItems : presetSource === 'qa' ? qaItems : mcqItems
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
    const o = preset.origin || 'assignment'
    if (o === 'teacher_key' || o === 'qa') {
      setQaItemsWithSync(preset.items || [])
      setGradeSource('qa')
    } else if (o === 'mcq') {
      setMcqItemsWithSync(preset.items || [])
      setGradeSource('mcq')
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

  // ── Rubric panel (assignment / QA / MCQ) ─────────────────────────────────

  function renderRubricPanel(
    source: 'assignment' | 'qa' | 'mcq',
    items: RubricItem[],
    setItems: (items: RubricItem[]) => void,
    json: string,
    setJson: (v: string) => void,
    showJson: boolean,
    setShowJson: (v: boolean) => void
  ) {
    const label = source === 'assignment' ? 'Assignment' : source === 'qa' ? 'QA' : 'MCQ (Moodle XML)'
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
        Build rubrics from an assignment, from QA model answers, or from a Moodle XML MCQ key. Grade open responses with AI, reference, or hybrid grounding; grade Moodle MCQ one attempt or many <code>.xml</code> files in a batch, with partial credit when a question has multiple correct options.
      </p>

      {error && (
        <div id="grade-flash-banner" className="error" style={{ whiteSpace: 'pre-wrap' }}>
          {error}
        </div>
      )}
      {message && <div className="success">{message}</div>}
      {gradeProgressLine && (
        <p
          role="status"
          aria-live="polite"
          style={{
            margin: '0.35rem 0 0',
            fontSize: '0.9rem',
            color: 'var(--ink-soft)',
            lineHeight: 1.45,
          }}
        >
          {gradeProgressLine}
        </p>
      )}

      <div className="tabs">
        {(['assignment', 'mcq', 'qa', 'presets', 'grade', 'history'] as const).map((t) => (
          <button
            key={t}
            type="button"
            className={tab === t ? 'active' : ''}
            onClick={() => setTab(t)}
          >
            {t === 'assignment' ? 'Assignment rubric' :
              t === 'mcq' ? 'MCQ (Moodle)' :
              t === 'qa' ? 'QA rubric' :
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
            subtitle="Add files (saved to your library for RAG when supported) and/or paste assignment text. The AI builds a rubric from the combined source."
            selectedIds={assignmentDocIds}
            setSelectedIds={setAssignmentDocIds}
            manualText={assignmentText}
            setManualText={setAssignmentText}
            docs={docs}
            docsLoading={docsLoading}
            onAddFiles={(f) =>
              void ingestGradingSource(f, {
                mergeDocIds: (ids) => setAssignmentDocIds((prev) => Array.from(new Set([...prev, ...ids]))),
                currentText: assignmentText,
                setText: setAssignmentText,
                label: 'Assignment source',
              })
            }
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

      {/* ── MCQ tab ── */}
      {tab === 'mcq' && (
        <>
          <div className="panel" style={{ marginBottom: '1rem', background: 'rgba(30,58,95,0.04)', border: '1px solid rgba(30,58,95,0.12)' }}>
            <p style={{ margin: 0, fontSize: '0.92rem', color: 'var(--ink-soft)' }}>
              <strong style={{ color: 'var(--ink)' }}>Moodle <code>&lt;quiz&gt;</code> XML only</strong> for the key and for each attempt. Scoring is deterministic (no LLM). On the <strong>Grade</strong> tab you can grade one attempt or batch-upload many <code>.xml</code> files.
              <br />
              <strong style={{ color: 'var(--ink)' }}>Multi-answer questions:</strong> if the key marks <em>n</em> correct options, each is worth <em>1/n</em> of the question points. The learner&apos;s net units = (correct choices − wrong choices), clamped to <em>[0, n]</em>, then scaled — one wrong selection removes one correct unit.
            </p>
          </div>

          <div className="panel" style={{ marginBottom: '1rem' }}>
            <h2 style={{ margin: '0 0 0.65rem', fontSize: '1.08rem' }}>Answer key (Moodle XML)</h2>
            <div className="field">
              <label htmlFor="mcq-key-upload">Upload answer-key XML</label>
              <input
                id="mcq-key-upload"
                type="file"
                accept={MOODLE_XML_ACCEPT}
                onChange={(e) => void loadTextFromXmlFile(e.target.files, setMcqKeyXml, 'answer key')}
              />
            </div>
            <div className="field">
              <label htmlFor="mcq-key-xml">Answer key (Moodle XML)</label>
              <textarea
                id="mcq-key-xml"
                rows={8}
                value={mcqKeyXml}
                onChange={(e) => setMcqKeyXml(e.target.value)}
                placeholder="Paste Moodle quiz export XML for the key…"
                style={{ fontFamily: 'monospace', fontSize: '0.78rem', width: '100%' }}
              />
            </div>
            <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void loadMcqRubricFromKeyXml()}>
              {loading ? 'Loading…' : 'Build MCQ rubric from key XML'}
            </button>
          </div>
          {renderRubricPanel(
            'mcq',
            mcqItems,
            setMcqItemsWithSync,
            mcqItemsJson,
            (v) => setMcqItemsJson(v),
            mcqShowJson,
            setMcqShowJson
          )}
        </>
      )}

      {/* ── QA tab ── */}
      {tab === 'qa' && (
        <>
          <div className="panel" style={{ marginBottom: '1rem', background: 'rgba(30,58,95,0.04)', border: '1px solid rgba(30,58,95,0.12)' }}>
            <p style={{ margin: 0, fontSize: '0.92rem', color: 'var(--ink-soft)' }}>
              For <strong style={{ color: 'var(--ink)' }}>open-ended</strong> work: paste or upload model questions/answers (not Moodle MCQ XML). Students submit <strong>plain text</strong> on the Grade tab. Generated rows are always <strong>conceptual</strong> (semantic grading vs. the model answer). Fine-tune each row&apos;s name, description, points, grounding, and model answer after generation.
            </p>
          </div>

          <SourcePanel
            title="QA — model questions / answers"
            subtitle="Paste or upload your reference answers. Used to build a rubric for open-text student work."
            selectedIds={qaTeacherDocIds}
            setSelectedIds={setQaTeacherDocIds}
            manualText={qaTeacherText}
            setManualText={setQaTeacherText}
            docs={docs}
            docsLoading={docsLoading}
            onAddFiles={(f) =>
              void ingestGradingSource(f, {
                mergeDocIds: (ids) => setQaTeacherDocIds((prev) => Array.from(new Set([...prev, ...ids]))),
                currentText: qaTeacherText,
                setText: setQaTeacherText,
                label: 'QA source',
              })
            }
            onRefresh={() => void refreshDocs()}
            onDelete={(doc) => void deleteDoc(doc)}
          />

          <div className="panel">
            <div className="field">
              <label htmlFor="qa-default-grounding">Default grounding for new QA criteria</label>
              <select
                id="qa-default-grounding"
                value={qaDefaultGrounding}
                onChange={(e) => setQaDefaultGrounding(e.target.value as 'ai' | 'reference' | 'hybrid')}
              >
                <option value="ai">AI reasoning</option>
                <option value="reference">Reference materials only</option>
                <option value="hybrid">Hybrid (AI + reference)</option>
              </select>
              <p style={{ margin: '0.35rem 0 0', color: 'var(--ink-soft)', fontSize: '0.85rem' }}>
                Applies to conceptual items from generation. Add reference text or library docs on the Grade tab when using reference or hybrid.
              </p>
            </div>
            <div className="field">
              <label htmlFor="qa-total-points">Total points</label>
              <input
                id="qa-total-points"
                type="number"
                min={1}
                max={2000}
                value={totalPoints}
                onChange={(e) => setTotalPoints(Number(e.target.value))}
              />
              <p style={{ margin: '0.35rem 0 0', color: 'var(--ink-soft)', fontSize: '0.85rem' }}>
                If per-question points appear in your key, the AI will prefer those; otherwise points are spread across items.
              </p>
            </div>
            <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void generateQaRubric()}>
              {loading ? 'Generating…' : 'Generate QA rubric'}
            </button>
          </div>

          {renderRubricPanel(
            'qa',
            qaItems,
            setQaItemsWithSync,
            qaItemsJson,
            (v) => setQaItemsJson(v),
            qaShowJson,
            setQaShowJson
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
                onChange={(e) => setGradeSource(e.target.value as 'assignment' | 'mcq' | 'qa')}
              >
                <option value="assignment">Assignment rubric ({assignmentItems.length} items)</option>
                <option value="qa">QA rubric ({qaItems.length} items)</option>
                <option value="mcq">MCQ — Moodle XML ({mcqItems.length} items)</option>
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
              {gradeSource === 'mcq'
                ? 'Not used for Moodle MCQ grading (scores come only from comparing the two XML files).'
                : 'Used for rubric items with grounding set to "reference" or "hybrid".'}
            </p>
            {gradeSource !== 'mcq' && activeItemsNeedReference && !hasReferenceMaterial && (
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
              <label htmlFor="ref-upload">Add reference files</label>
              <p style={{ margin: '0.25rem 0 0.45rem', color: 'var(--ink-soft)', fontSize: '0.82rem' }}>
                Supported documents are saved to your library for RAG; identical files are not stored twice. Text extract is appended below when parsing succeeds.
              </p>
              <input
                id="ref-upload"
                type="file"
                multiple
                accept={PARSE_ACCEPT}
                onChange={(e) =>
                  void ingestGradingSource(e.target.files, {
                    mergeDocIds: (ids) => setReferenceDocIds((prev) => Array.from(new Set([...prev, ...ids]))),
                    currentText: referenceText,
                    setText: setReferenceText,
                    label: 'Reference',
                  })
                }
              />
            </div>
            <div className="field">
              <label>Select from library</label>
              <p style={{ margin: '0.2rem 0 0.45rem', color: 'var(--ink-soft)', fontSize: '0.82rem' }}>
                Library documents are used by the system RAG retriever during grading.
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
            {gradeSource === 'mcq' ? (
              <>
                <p style={{ margin: '0 0 0.85rem', color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
                  Answer key XML must match what you loaded on the <strong>MCQ (Moodle)</strong> tab ({mcqKeyXml.trim() ? `${mcqKeyXml.length.toLocaleString()} characters in key buffer` : 'key buffer is empty — paste or upload the key there first'}).
                </p>
                <div className="field">
                  <label htmlFor="mcq-student-upload">Upload student attempt (.xml)</label>
                  <input
                    id="mcq-student-upload"
                    type="file"
                    accept={MOODLE_XML_ACCEPT}
                    onChange={(e) => void loadTextFromXmlFile(e.target.files, setMcqStudentXml, 'student attempt')}
                  />
                </div>
                <div className="field">
                  <label htmlFor="mcq-student-xml">Student Moodle XML (single attempt)</label>
                  <textarea
                    id="mcq-student-xml"
                    rows={12}
                    value={mcqStudentXml}
                    onChange={(e) => setMcqStudentXml(e.target.value)}
                    placeholder="Paste one learner’s Moodle quiz XML export…"
                    style={{ fontFamily: 'monospace', fontSize: '0.78rem', width: '100%' }}
                  />
                </div>
                <p style={{ margin: '0 0 0.75rem', color: 'var(--ink-soft)', fontSize: '0.88rem' }}>
                  For <strong>many attempts at once</strong>, use <em>Batch grading</em> below: queue multiple <code>.xml</code> files against the same key.
                </p>
              </>
            ) : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  <div className="field">
                    <label htmlFor="single-upload">Upload submission file (library types are saved for RAG)</label>
                    <input
                      id="single-upload"
                      type="file"
                      accept={PARSE_ACCEPT}
                      onChange={(e) => void ingestSingleSubmissionFile(e.target.files)}
                    />
                  </div>
                  <div className="field">
                    <label>Or use library document</label>
                    <DocList docs={docs} selectedIds={singleSubmissionDocIds} onChange={setSingleSubmissionDocIds} onDelete={(doc) => void deleteDoc(doc)} loading={docsLoading} />
                  </div>
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
              </>
            )}
            <div className="field">
              <label htmlFor="single-title">Result title</label>
              <input id="single-title" value={singleTitle} onChange={(e) => setSingleTitle(e.target.value)} />
            </div>
            <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void gradeSingleSubmission()}>
              {loading ? 'Grading…' : gradeSource === 'mcq' ? 'Grade Moodle MCQ' : 'Grade single submission'}
            </button>
          </div>

          <div id="grade-result-anchor" style={{ scrollMarginTop: '1rem' }} />
          <ResultCard record={gradeResult} onApply={applySingleReview} onSave={saveHistory ? saveReviewedRecord : undefined} saving={savingReview} />

          {/* Batch grading */}
          <div className="panel" style={{ marginBottom: '1rem' }}>
            <h2 style={{ margin: '0 0 0.5rem', fontSize: '1.08rem' }}>Batch grading</h2>
            {gradeSource === 'mcq' ? (
              <>
                <p style={{ margin: '0 0 0.85rem', color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
                  Upload multiple student Moodle <code>.xml</code> exports. Each file is graded against the same answer key from the <strong>MCQ (Moodle)</strong> tab.
                </p>
                <div className="field">
                  <label htmlFor="batch-name-mcq">Batch name</label>
                  <input
                    id="batch-name-mcq"
                    value={batchName}
                    onChange={(e) => setBatchName(e.target.value)}
                    placeholder="Section A Moodle attempts"
                  />
                </div>
                <div className="field">
                  <label htmlFor="mcq-batch-upload">Add student attempt XML files</label>
                  <input
                    id="mcq-batch-upload"
                    ref={mcqBatchInputRef}
                    type="file"
                    multiple
                    accept={MOODLE_XML_ACCEPT}
                    onChange={(e) => void addMcqBatchStudentXmlFiles(e.target.files)}
                  />
                </div>
                <div style={{ display: 'flex', gap: '0.65rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                  <span className={`pill ${mcqBatchStudentXmls.length > 0 ? 'pill--ok' : 'pill--warn'}`}>
                    {mcqBatchStudentXmls.length} attempt(s) queued
                  </span>
                  {mcqBatchStudentXmls.length > 0 && (
                    <button
                      type="button"
                      className="btn btn--ghost"
                      style={{ fontSize: '0.82rem', padding: '0.2rem 0.6rem' }}
                      onClick={() => setMcqBatchStudentXmls([])}
                    >
                      Clear queue
                    </button>
                  )}
                  {batchResults.length > 0 && <span className="pill pill--ok">{batchResults.length} result(s)</span>}
                </div>
                {mcqBatchStudentXmls.length > 0 && (
                  <ul style={{ margin: '0 0 0.75rem', paddingLeft: '1.1rem', fontSize: '0.88rem', color: 'var(--ink-soft)' }}>
                    {mcqBatchStudentXmls.map((row, i) => (
                      <li key={`${row.title}-${i}`} style={{ marginBottom: '0.25rem' }}>
                        <span style={{ color: 'var(--ink)' }}>{row.title}</span>
                        {' · '}
                        {row.xml.length.toLocaleString()} chars
                        {' '}
                        <button type="button" className="btn btn--ghost" style={{ fontSize: '0.75rem', padding: '0.1rem 0.45rem' }} onClick={() => removeMcqBatchStudent(i)}>
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <button type="button" className="btn btn--primary" disabled={loading} onClick={() => void gradeBatchMcq()}>
                  {loading ? 'Grading…' : 'Grade all Moodle MCQ attempts'}
                </button>
              </>
            ) : (
              <>
                <p style={{ margin: '0 0 0.85rem', color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
                  Upload multiple submission files and grade them all at once (parsed to text).
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
              </>
            )}
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
                onChange={(e) => setPresetSource(e.target.value as 'assignment' | 'qa' | 'mcq')}
              >
                <option value="assignment">Assignment rubric</option>
                <option value="qa">QA rubric</option>
                <option value="mcq">MCQ (Moodle) rubric</option>
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
                      {presetOriginLabel(preset.origin)} · {preset.items?.length || 0} items · {preset.total_points} pts
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
