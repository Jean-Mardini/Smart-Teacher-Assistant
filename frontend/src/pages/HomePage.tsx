import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { API_BASE, apiJson } from '../api/client'

export function HomePage() {
  const [health, setHealth] = useState<string | null>(null)
  const [evalStatus, setEvalStatus] = useState<Record<string, unknown> | null>(null)
  const [rag, setRag] = useState<Record<string, unknown> | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const h = await apiJson<{ status: string }>('/health')
        if (!cancelled) setHealth(h.status)
        const e = await apiJson<Record<string, unknown>>('/evaluation/status')
        if (!cancelled) setEvalStatus(e)
        const r = await apiJson<Record<string, unknown>>('/rag/status')
        if (!cancelled) setRag(r)
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : 'API unreachable')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <header className="hero">
        <p className="hero__eyebrow">The atelier</p>
        <h1 className="hero__title">Where teaching meets quiet brilliance.</h1>
        <p className="hero__lead">
          A single workspace for your course materials, Socratic dialogue with your library, creative studio tools,
          and human-centered grading — powered by your Smart Teacher Assistant API.
        </p>
        <div className="status-row">
          <span className={`pill ${health === 'ok' ? 'pill--ok' : 'pill--warn'}`}>
            API {health === 'ok' ? '● live' : '○ offline'}
          </span>
          {rag && typeof rag.indexed_chunks === 'number' && (
            <span className="pill">
              Index · {String(rag.indexed_chunks)} chunks
            </span>
          )}
          {evalStatus && evalStatus.rubrics_implemented === true && (
            <span className="pill pill--ok">Evaluation ready</span>
          )}
        </div>
        {err && (
          <p className="error" style={{ marginTop: '1rem' }}>
            Connect the backend:{' '}
            <code>python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000</code> — UI expects{' '}
            <code>{API_BASE || '(dev: Vite proxy → http://127.0.0.1:8000)'}</code> (set{' '}
            <code>VITE_API_URL</code> in <code>frontend/.env.local</code> if different).
            <br />
            <small>{err}</small>
          </p>
        )}
      </header>

      <div className="bento">
        <Link to="/library">
          <article className="bento__card panel--lift">
            <h3>Library</h3>
            <p>Upload materials — the search index refreshes automatically for Dialogue.</p>
          </article>
        </Link>
        <Link to="/chat">
          <article className="bento__card panel--lift">
            <h3>Dialogue</h3>
            <p>Chat with your indexed documents — grounded answers.</p>
          </article>
        </Link>
        <Link to="/summarize">
          <article className="bento__card panel--lift">
            <h3>Summarize</h3>
            <p>Upload a PDF or Word file and get a structured summary.</p>
          </article>
        </Link>
        <Link to="/slides">
          <article className="bento__card panel--lift">
            <h3>Slides</h3>
            <p>Slide deck outline from one document.</p>
          </article>
        </Link>
        <Link to="/quiz">
          <article className="bento__card panel--lift">
            <h3>Quiz</h3>
            <p>Questions generated from your reading.</p>
          </article>
        </Link>
        <Link to="/grade">
          <article className="bento__card panel--lift">
            <h3>Grading</h3>
            <p>Rubrics and scoring with clear rationale.</p>
          </article>
        </Link>
      </div>
    </>
  )
}
