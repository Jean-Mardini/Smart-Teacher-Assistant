import { useState } from 'react'
import { DocPicker } from '../components/DocPicker'
import { apiJson } from '../api/client'

type Slide = { slide_title: string; bullets: string[]; speaker_notes?: string }

type SlideResult = {
  title?: string
  slides?: Slide[]
  processing_notes?: string[]
}

export function SlidesPage() {
  const [docIds, setDocIds] = useState<string[]>([])
  const [nSlides, setNSlides] = useState(5)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<SlideResult | null>(null)

  async function run() {
    if (!docIds.length) {
      setError('Choose at least one document above.')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await apiJson<SlideResult>('/agents/slides', {
        method: 'POST',
        body: JSON.stringify({
          document_id: docIds[0],
          n_slides: nSlides,
          generate_images: false,
          max_generated_images: 0,
        }),
      }, 120_000)
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <h1 className="page-title">Slides</h1>
      <p className="page-sub">Generate a slide deck outline from one document (titles + bullets + speaker notes).</p>

      <DocPicker value={docIds} onChange={setDocIds} accept=".pdf,.docx,.pptx,.txt,.md" />

      <div className="panel">
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.05rem' }}>2. Options</h2>
        <div className="field">
          <label htmlFor="ns">Number of slides</label>
          <input
            id="ns"
            type="number"
            min={1}
            max={20}
            value={nSlides}
            onChange={(e) => setNSlides(Number(e.target.value))}
          />
        </div>
        <button type="button" className="btn btn--accent" disabled={loading || !docIds.length} onClick={() => void run()}>
          {loading ? 'Generating…' : 'Generate slides'}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {result?.slides && result.slides.length > 0 && (
        <div className="panel" style={{ marginTop: '1.25rem' }}>
          <h2 style={{ margin: '0 0 1rem', fontSize: '1.15rem' }}>{result.title || 'Slide deck'}</h2>
          {result.slides.map((s, idx) => (
            <div
              key={idx}
              style={{
                marginBottom: '1.25rem',
                paddingBottom: '1rem',
                borderBottom: idx < result.slides!.length - 1 ? '1px solid var(--line)' : undefined,
              }}
            >
              <h3 style={{ margin: '0 0 0.5rem', fontSize: '1.05rem' }}>
                {idx + 1}. {s.slide_title}
              </h3>
              <ul style={{ margin: 0 }}>
                {(s.bullets || []).map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
              {s.speaker_notes && (
                <p style={{ fontSize: '0.88rem', color: 'var(--ink-soft)', marginTop: '0.5rem' }}>
                  <em>Notes:</em> {s.speaker_notes}
                </p>
              )}
            </div>
          ))}
          {result.processing_notes && result.processing_notes.length > 0 && (
            <p style={{ fontSize: '0.85rem', color: 'var(--ink-soft)' }}>{result.processing_notes.join(' ')}</p>
          )}
        </div>
      )}
    </>
  )
}
