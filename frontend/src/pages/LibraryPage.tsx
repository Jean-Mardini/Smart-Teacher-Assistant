import { useCallback, useEffect, useState } from 'react'
import { apiJson, apiUpload } from '../api/client'

type LocalDoc = {
  document_id: string
  title: string
  path: string
  filetype: string
}

export function LibraryPage() {
  const [docs, setDocs] = useState<LocalDoc[]>([])
  const [loading, setLoading] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const list = await apiJson<LocalDoc[]>('/documents/local')
      setDocs(list)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to list documents')
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
    setError(null)
    setMessage(null)
    try {
      await apiUpload('/documents/upload', files)
      setMessage('Files stored in the knowledge base.')
      await refresh()
      e.target.value = ''
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    }
  }

  async function reindex() {
    setReindexing(true)
    setError(null)
    setMessage(null)
    try {
      await apiJson('/rag/reindex', { method: 'POST', body: '{}' })
      setMessage('Index rebuilt. Dialogue and studio can use fresh chunks.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Reindex failed')
    } finally {
      setReindexing(false)
    }
  }

  return (
    <>
      <h1 className="page-title">Library</h1>
      <p className="page-sub">
        Add PDF, DOCX, PPTX, or text files. After uploading, rebuild the search index so Dialogue and Studio can see
        them.
      </p>

      {error && <div className="error">{error}</div>}
      {message && (
        <div className="panel" style={{ marginBottom: '1rem', background: 'rgba(80,160,120,0.08)', borderColor: 'rgba(80,160,120,0.25)' }}>
          {message}
        </div>
      )}

      <div className="panel">
        <div className="dropzone">
          <strong>Add to shelf</strong>
          <p style={{ margin: '0.5rem 0', color: 'var(--ink-soft)', fontSize: '0.92rem' }}>
            Drag is browser-limited — use the file picker. Multiple files allowed.
          </p>
          <input type="file" multiple accept=".pdf,.docx,.pptx,.txt,.md,.json" onChange={onUpload} />
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <button type="button" className="btn btn--primary" disabled={reindexing} onClick={() => void reindex()}>
            {reindexing ? 'Rebuilding index…' : 'Rebuild search index'}
          </button>
          <button type="button" className="btn btn--ghost" disabled={loading} onClick={() => void refresh()}>
            Refresh list
          </button>
        </div>
      </div>

      <div className="panel" style={{ marginTop: '1.25rem' }}>
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.15rem' }}>On the shelf</h2>
        {loading && <p style={{ color: 'var(--ink-soft)' }}>Loading…</p>}
        {!loading && docs.length === 0 && (
          <p style={{ color: 'var(--ink-soft)' }}>No documents yet. Upload above or place files in data/knowledge_base.</p>
        )}
        <ul className="doc-list">
          {docs.map((d) => (
            <li key={d.document_id}>
              <span>
                <strong>{d.title}</strong> <code>{d.document_id}</code>
              </span>
              <span style={{ color: 'var(--ink-soft)' }}>{d.filetype}</span>
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}
