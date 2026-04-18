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
            Connect the backend: <code>uvicorn app.main:app --reload</code> at <code>{API_BASE}</code>
            <br />
            <small>{err}</small>
          </p>
        )}
      </header>

      <div className="bento">
        <Link to="/library">
          <article className="bento__card panel--lift">
            <h3>Library</h3>
            <p>Upload readings and handouts; keep your knowledge base in one luminous shelf.</p>
          </article>
        </Link>
        <Link to="/chat">
          <article className="bento__card panel--lift">
            <h3>Dialogue</h3>
            <p>Ask questions grounded in your documents — answers with traceable sources.</p>
          </article>
        </Link>
        <Link to="/studio">
          <article className="bento__card panel--lift">
            <h3>Studio</h3>
            <p>Summaries, slide decks, and quizzes — crafted from a chosen text.</p>
          </article>
        </Link>
        <Link to="/grade">
          <article className="bento__card panel--lift">
            <h3>Grading salon</h3>
            <p>Rubrics and fair scoring with transparent rationale — Kristy&apos;s flexible grader.</p>
          </article>
        </Link>
      </div>
    </>
  )
}
