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
}

export function DocPicker({ value, onChange, accept, filetypeHint }: Props) {
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
      if (added.length > 0) onChange(added)
      e.target.value = ''
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : 'Upload failed')
    }
  }

  const options = filetypeHint
    ? docs.filter((d) => d.filetype.toLowerCase().includes(filetypeHint.toLowerCase()))
    : docs

  const selectedDocs = options.filter((d) => value.includes(d.document_id))

  return (
    <div className="panel" style={{ marginBottom: '1.25rem' }}>
      <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.05rem' }}>1. Add or choose documents</h2>
      <p style={{ margin: '0 0 1rem', color: 'var(--ink-soft)', fontSize: '0.92rem' }}>
        Upload one or more files into the library, then select them below. Hold{' '}
        <code>Ctrl</code> (or <code>Cmd</code>) to pick multiple from the list.
      </p>
      {err && <div className="error" style={{ whiteSpace: 'pre-wrap' }}>{err}</div>}
      <div className="field">
        <label htmlFor="doc-upload">Upload files</label>
        <input id="doc-upload" type="file" multiple accept={accept} onChange={(e) => void onUpload(e)} />
      </div>
      <div className="field">
        <label htmlFor="doc-select">Library documents</label>
        <select
          id="doc-select"
          multiple
          size={Math.min(8, Math.max(3, options.length || 3))}
          value={value}
          onChange={(e) => onChange(Array.from(e.target.selectedOptions).map((o) => o.value))}
          disabled={loading}
        >
          {options.length === 0 && (
            <option value="" disabled>
              {loading ? 'Loading…' : 'No documents — upload above'}
            </option>
          )}
          {options.map((d) => (
            <option key={d.path} value={d.document_id}>
              {d.title} · {d.filetype}
            </option>
          ))}
        </select>
        {selectedDocs.length > 0 && (
          <p style={{ margin: '0.4rem 0 0', fontSize: '0.85rem', color: 'var(--ink-soft)' }}>
            Selected ({selectedDocs.length}):{' '}
            <strong style={{ color: 'var(--ink)' }}>
              {selectedDocs.map((d) => d.title).join(', ')}
            </strong>
          </p>
        )}
      </div>
      <button type="button" className="btn btn--ghost" onClick={() => void refresh()} disabled={loading}>
        {loading ? 'Refreshing…' : 'Refresh list'}
      </button>
    </div>
  )
}
