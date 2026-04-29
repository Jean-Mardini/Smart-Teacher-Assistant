import { useCallback, useEffect, useState } from 'react'
import { apiJson, apiUpload } from '../api/client'

export type DocRow = {
  document_id: string
  title: string
  path: string
  filetype: string
}

type Props = {
  value: string[]
  onChange: (documentIds: string[]) => void
  /** e.g. ".pdf,.docx" */
  accept: string
  /** Filter which types appear in list (optional) */
  filetypeHint?: string
  /** Lighter chrome for embedding (e.g. Dialogue page). */
  compact?: boolean
  /** When set, caps how many ids can be selected (add / select-all / upload merge). */
  maxSelection?: number
  /** Replaces the default compact intro paragraph when `compact` is true. */
  compactHint?: string
}

export function DocPicker({ value, onChange, accept, filetypeHint, compact, maxSelection, compactHint }: Props) {
  const [docs, setDocs] = useState<DocRow[]>([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const list = await apiJson<DocRow[]>('/documents/local')
      setDocs(list)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load library')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files
    if (!files?.length) return
    setErr(null)
    const prevIds = new Set(docs.map((d) => d.document_id))
    try {
      await apiUpload('/documents/upload', files)
      const list = await apiJson<DocRow[]>('/documents/local')
      setDocs(list)
      const added = list.filter((d) => !prevIds.has(d.document_id)).map((d) => d.document_id)
      if (added.length > 0) onChange(cap(Array.from(new Set([...value, ...added]))))
      e.target.value = ''
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : 'Upload failed')
    }
  }

  const options = filetypeHint
    ? docs.filter((d) => d.filetype.toLowerCase().includes(filetypeHint.toLowerCase()))
    : docs

  const selectedDocs = options.filter((d) => value.includes(d.document_id))

  function cap(ids: string[]) {
    if (maxSelection == null || maxSelection <= 0) return ids
    return ids.slice(0, maxSelection)
  }

  const uploadId = compact ? 'doc-upload-compact' : 'doc-upload'
  const listGroupId = compact ? 'doc-list-compact' : 'doc-list-full'

  function toggleDocument(documentId: string, checked: boolean) {
    if (checked) {
      if (maxSelection != null && maxSelection > 0 && value.length >= maxSelection) return
      onChange(cap(Array.from(new Set([...value, documentId]))))
    } else {
      onChange(value.filter((id) => id !== documentId))
    }
  }

  function selectAllVisible() {
    onChange(cap(Array.from(new Set([...value, ...options.map((d) => d.document_id)]))))
  }

  function clearSelection() {
    onChange([])
  }

  return (
    <div className={compact ? 'doc-picker doc-picker--compact' : 'panel'} style={compact ? undefined : { marginBottom: '1.25rem' }}>
      {!compact && (
        <>
          <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.05rem' }}>1. Add or choose documents</h2>
          <p style={{ margin: '0 0 1rem', color: 'var(--ink-soft)', fontSize: '0.92rem' }}>
            Upload one or more files into the library, then tick every document you want included (two or more is fine).
          </p>
        </>
      )}
      {compact && (
        <p style={{ margin: '0 0 0.85rem', color: 'var(--ink-soft)', fontSize: '0.88rem', lineHeight: 1.45 }}>
          {compactHint ??
            'Upload adds to the library (for RAG). Check one or more documents to scope the answer.'}
        </p>
      )}
      {err && <div className="error" style={{ whiteSpace: 'pre-wrap' }}>{err}</div>}
      <div className="field">
        <label htmlFor={uploadId}>Upload files</label>
        <input id={uploadId} type="file" multiple accept={accept} onChange={(e) => void onUpload(e)} />
      </div>
      <div className="field">
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between', gap: '0.5rem', marginBottom: '0.35rem' }}>
          <span id={listGroupId} style={{ fontWeight: 600, fontSize: '0.92rem' }}>
            Library documents
          </span>
          {options.length > 0 && (
            <span style={{ display: 'inline-flex', gap: '0.35rem', flexWrap: 'wrap' }}>
              <button type="button" className="btn btn--ghost" style={{ fontSize: '0.78rem', padding: '0.15rem 0.5rem' }} onClick={selectAllVisible} disabled={loading}>
                Select all
              </button>
              <button type="button" className="btn btn--ghost" style={{ fontSize: '0.78rem', padding: '0.15rem 0.5rem' }} onClick={clearSelection} disabled={loading || value.length === 0}>
                Clear
              </button>
            </span>
          )}
        </div>
        <div className="doc-picker__list" role="group" aria-labelledby={listGroupId}>
          {loading && options.length === 0 && <p style={{ margin: 0, color: 'var(--ink-soft)', fontSize: '0.9rem' }}>Loading…</p>}
          {!loading && options.length === 0 && (
            <p style={{ margin: 0, color: 'var(--ink-soft)', fontSize: '0.9rem' }}>No documents — upload above.</p>
          )}
          {options.map((d) => {
            const checked = value.includes(d.document_id)
            return (
              <label key={d.path} className="doc-picker__row">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => toggleDocument(d.document_id, e.target.checked)}
                  disabled={loading}
                />
                <span className="doc-picker__row-label">
                  <span className="doc-picker__title">{d.title}</span>
                  <span className="doc-picker__meta">{d.filetype}</span>
                </span>
              </label>
            )
          })}
        </div>
        {selectedDocs.length > 0 && (
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.85rem', color: 'var(--ink-soft)' }}>
            <span className="pill pill--ok" style={{ fontSize: '0.78rem', marginRight: '0.35rem' }}>
              {selectedDocs.length} selected
            </span>
            <strong style={{ color: 'var(--ink)' }}>{selectedDocs.map((d) => d.title).join(', ')}</strong>
          </p>
        )}
      </div>
      <button type="button" className="btn btn--ghost" onClick={() => void refresh()} disabled={loading}>
        {loading ? 'Refreshing…' : 'Refresh list'}
      </button>
    </div>
  )
}
