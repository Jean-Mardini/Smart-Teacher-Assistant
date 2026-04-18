import { useCallback, useEffect, useState } from 'react'
import { apiJson, apiUpload } from '../api/client'

export type DocRow = {
  document_id: string
  title: string
  path: string
  filetype: string
}

type Props = {
  value: string
  onChange: (documentId: string) => void
  /** e.g. ".pdf,.docx" */
  accept: string
  /** Filter which types appear in dropdown (optional) */
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
    const firstName = files[0].name
    try {
      await apiUpload('/documents/upload', files)
      const list = await apiJson<DocRow[]>('/documents/local')
      setDocs(list)
      const hit =
        list.find((d) => d.path.replace(/\\/g, '/').endsWith(firstName)) ||
        list.find((d) => d.title && firstName.includes(d.title.slice(0, 20))) ||
        list[list.length - 1]
      if (hit) onChange(hit.document_id)
      e.target.value = ''
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : 'Upload failed')
    }
  }

  const options = filetypeHint
    ? docs.filter((d) => d.filetype.toLowerCase().includes(filetypeHint.toLowerCase()))
    : docs

  return (
    <div className="panel" style={{ marginBottom: '1.25rem' }}>
      <h2 style={{ margin: '0 0 0.75rem', fontSize: '1.05rem' }}>1. Add or choose a document</h2>
      <p style={{ margin: '0 0 1rem', color: 'var(--ink-soft)', fontSize: '0.92rem' }}>
        Upload a file into the library, then pick it below. You can also use files already on the shelf from the{' '}
        <strong>Library</strong> page.
      </p>
      {err && <div className="error" style={{ whiteSpace: 'pre-wrap' }}>{err}</div>}
      <div className="field">
        <label htmlFor="doc-upload">Upload</label>
        <input id="doc-upload" type="file" accept={accept} onChange={(e) => void onUpload(e)} />
      </div>
      <div className="field">
        <label htmlFor="doc-select">Active document</label>
        <select
          id="doc-select"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={loading || options.length === 0}
        >
          <option value="">{loading ? 'Loading…' : options.length === 0 ? 'No documents — upload above' : 'Select…'}</option>
          {options.map((d) => (
            <option key={d.path} value={d.document_id}>
              {d.title} ({d.document_id}) · {d.filetype}
            </option>
          ))}
        </select>
      </div>
      <button type="button" className="btn btn--ghost" onClick={() => void refresh()} disabled={loading}>
        Refresh list
      </button>
    </div>
  )
}
