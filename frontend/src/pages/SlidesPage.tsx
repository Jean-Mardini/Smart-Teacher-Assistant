import { useMemo, useState, type CSSProperties } from 'react'
import { DocPicker } from '../components/DocPicker'
import { LiveSlideDeck } from '../components/live/LiveSlideDeck'
import type { LiveSlidesResponse } from '../components/live/liveSlides.types'
import { assertLiveSlidesHaveImages, preloadLiveSlideImages } from '../components/live/validateLiveSlides'
import { apiJson, apiPostBlob, triggerDownload } from '../api/client'

type TemplatePreview = {
  outerBg: string
  cardBg: string
  titleColor: string
  bodyColor: string
  titleFont: string
  bodyFont: string
  boxShadow: string
}

type ThemeFilterId = 'dark' | 'light' | 'professional' | 'colorful'

type ThemeHeroChrome = {
  workspace: string
  smartFill: string
  smartBorder: string
  btnBg: string
  btnText: string
  btnGhostBorder: string
  imageWell: string
  linkColor: string
}

const THEME_FILTER_CHIPS: { id: ThemeFilterId; label: string }[] = [
  { id: 'dark', label: 'Dark' },
  { id: 'light', label: 'Light' },
  { id: 'professional', label: 'Professional' },
  { id: 'colorful', label: 'Colorful' },
]

const SLIDE_TEMPLATES = [
  {
    id: 'academic_default',
    label: 'Default (modern deck)',
    themeName: 'Zephyr',
    tagline: 'Balanced density for real lessons',
    filters: ['light', 'professional', 'colorful'] as ThemeFilterId[],
    hero: {
      workspace: '#dbeafe',
      smartFill: '#eff6ff',
      smartBorder: '#bfdbfe',
      btnBg: '#3b82f6',
      btnText: '#ffffff',
      btnGhostBorder: '#93c5fd',
      imageWell: '#e2e8f0',
      linkColor: '#2563eb',
    } satisfies ThemeHeroChrome,
    preview: {
      outerBg: 'linear-gradient(155deg, #dbeafe 0%, #e0e7ff 55%, #f8fafc 100%)',
      cardBg: '#ffffff',
      titleColor: '#0f172a',
      bodyColor: '#64748b',
      titleFont: '600 11px ui-sans-serif, system-ui, sans-serif',
      bodyFont: '400 9px ui-sans-serif, system-ui, sans-serif',
      boxShadow: '0 10px 28px rgba(15, 23, 42, 0.1)',
    } satisfies TemplatePreview,
  },
  {
    id: 'minimal_clean',
    label: 'Minimal & clean',
    themeName: 'Serene',
    tagline: 'Quiet hierarchy, no filler',
    filters: ['light', 'professional'] as ThemeFilterId[],
    hero: {
      workspace: '#f1f5f9',
      smartFill: '#f8fafc',
      smartBorder: '#e2e8f0',
      btnBg: '#475569',
      btnText: '#ffffff',
      btnGhostBorder: '#94a3b8',
      imageWell: '#e2e8f0',
      linkColor: '#334155',
    } satisfies ThemeHeroChrome,
    preview: {
      outerBg: 'linear-gradient(180deg, #f8fafc 0%, #e2e8f0 100%)',
      cardBg: '#ffffff',
      titleColor: '#1e293b',
      bodyColor: '#94a3b8',
      titleFont: '600 11px ui-sans-serif, system-ui, sans-serif',
      bodyFont: '400 9px ui-sans-serif, system-ui, sans-serif',
      boxShadow: '0 6px 18px rgba(30, 41, 59, 0.08)',
    } satisfies TemplatePreview,
  },
  {
    id: 'workshop_interactive',
    label: 'Workshop / interactive',
    themeName: 'Seafoam',
    tagline: 'You / we prompts, activities',
    filters: ['light', 'colorful'] as ThemeFilterId[],
    hero: {
      workspace: '#ccfbf1',
      smartFill: '#f0fdfa',
      smartBorder: '#99f6e4',
      btnBg: '#0d9488',
      btnText: '#ffffff',
      btnGhostBorder: '#5eead4',
      imageWell: '#cbd5e1',
      linkColor: '#0f766e',
    } satisfies ThemeHeroChrome,
    preview: {
      outerBg: 'linear-gradient(165deg, #d1fae5 0%, #ecfdf5 45%, #f0fdfa 100%)',
      cardBg: '#ffffff',
      titleColor: '#0f766e',
      bodyColor: '#5b908a',
      titleFont: '600 11px ui-sans-serif, system-ui, sans-serif',
      bodyFont: '400 9px ui-sans-serif, system-ui, sans-serif',
      boxShadow: '0 8px 22px rgba(15, 118, 110, 0.12)',
    } satisfies TemplatePreview,
  },
  {
    id: 'executive_summary',
    label: 'Executive summary',
    themeName: 'Cigar',
    tagline: 'Outcomes and decisions first',
    filters: ['dark', 'professional'] as ThemeFilterId[],
    hero: {
      workspace: '#0f172a',
      smartFill: '#1e293b',
      smartBorder: '#334155',
      btnBg: '#f59e0b',
      btnText: '#0f172a',
      btnGhostBorder: '#94a3b8',
      imageWell: '#334155',
      linkColor: '#fcd34d',
    } satisfies ThemeHeroChrome,
    preview: {
      outerBg: 'linear-gradient(145deg, #1e293b 0%, #0f172a 100%)',
      cardBg: '#334155',
      titleColor: '#fef3c7',
      bodyColor: '#cbd5e1',
      titleFont: '600 11px Georgia, "Times New Roman", serif',
      bodyFont: '400 9px ui-sans-serif, system-ui, sans-serif',
      boxShadow: '0 12px 32px rgba(0, 0, 0, 0.35)',
    } satisfies TemplatePreview,
  },
  {
    id: 'deep_technical',
    label: 'Technical deep-dive',
    themeName: 'Wireframe',
    tagline: 'Precise terms, stepwise flow',
    filters: ['light', 'professional'] as ThemeFilterId[],
    hero: {
      workspace: '#e5e7eb',
      smartFill: '#f9fafb',
      smartBorder: '#d1d5db',
      btnBg: '#111827',
      btnText: '#f9fafb',
      btnGhostBorder: '#6b7280',
      imageWell: '#d1d5db',
      linkColor: '#1d4ed8',
    } satisfies ThemeHeroChrome,
    preview: {
      outerBg: 'linear-gradient(180deg, #e5e7eb 0%, #d1d5db 100%)',
      cardBg: '#f9fafb',
      titleColor: '#111827',
      bodyColor: '#6b7280',
      titleFont: '600 11px ui-monospace, SFMono-Regular, Menlo, monospace',
      bodyFont: '400 9px ui-monospace, SFMono-Regular, Menlo, monospace',
      boxShadow: '0 4px 14px rgba(17, 24, 39, 0.12)',
    } satisfies TemplatePreview,
  },
  {
    id: 'story_visual',
    label: 'Story / keynote',
    themeName: 'Aurora',
    tagline: 'Narrative arc, vivid wording',
    filters: ['colorful', 'light'] as ThemeFilterId[],
    hero: {
      workspace: 'linear-gradient(145deg, #ede9fe 0%, #fce7f3 50%, #e0f2fe 100%)',
      smartFill: '#faf5ff',
      smartBorder: '#ddd6fe',
      btnBg: '#7c3aed',
      btnText: '#ffffff',
      btnGhostBorder: '#a78bfa',
      imageWell: '#e9d5ff',
      linkColor: '#6d28d9',
    } satisfies ThemeHeroChrome,
    preview: {
      outerBg: 'linear-gradient(135deg, #ede9fe 0%, #fce7f3 40%, #cffafe 100%)',
      cardBg: '#ffffff',
      titleColor: '#4c1d95',
      bodyColor: '#7c3aed',
      titleFont: '600 11px ui-sans-serif, system-ui, sans-serif',
      bodyFont: '400 9px ui-sans-serif, system-ui, sans-serif',
      boxShadow: '0 10px 26px rgba(76, 29, 149, 0.12)',
    } satisfies TemplatePreview,
  },
] as const

type TemplateId = (typeof SLIDE_TEMPLATES)[number]['id']

type CreationMode = 'generate' | 'paste' | 'template' | 'import'

const CREATION_CARDS: {
  id: CreationMode
  icon: string
  title: string
  description: string
  badge?: string
}[] = [
  {
    id: 'generate',
    icon: '✦',
    title: 'Generate',
    description: 'Create from a one-line prompt in a few seconds',
    badge: 'Quick',
  },
  {
    id: 'paste',
    icon: 'Aa',
    title: 'Paste in text',
    description: 'Create from notes, an outline, or existing content',
  },
  {
    id: 'template',
    icon: '▥',
    title: 'Create from template',
    description: 'Use a library document and a slide tone / structure preset',
  },
  {
    id: 'import',
    icon: '↑',
    title: 'Import file or URL',
    description: 'Upload a document from the library or pull text from a web page',
  },
]

const cardGrid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
  gap: '1rem',
  alignItems: 'start',
  marginBottom: '1.5rem',
}

const cardBase: CSSProperties = {
  textAlign: 'left',
  padding: '1.1rem 1rem',
  borderRadius: '12px',
  border: '1px solid var(--line, #e2e8f0)',
  background: 'var(--panel, #fff)',
  cursor: 'pointer',
  transition: 'border-color 0.15s, box-shadow 0.15s',
}

export function SlidesPage() {
  const [creationMode, setCreationMode] = useState<CreationMode>('template')
  const [docId, setDocId] = useState('')
  const [promptLine, setPromptLine] = useState('')
  const [pastedText, setPastedText] = useState('')
  const [importUrl, setImportUrl] = useState('')
  const [sourceTitle, setSourceTitle] = useState('')
  const [nSlides, setNSlides] = useState(5)
  const [presentationDetail, setPresentationDetail] = useState<'standard' | 'deep'>('standard')
  const [template, setTemplate] = useState<TemplateId>('academic_default')
  const [themeSearch, setThemeSearch] = useState('')
  const [themeFilter, setThemeFilter] = useState<ThemeFilterId | null>(null)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /** Gamma-style live deck from ``POST /generate-slides`` (JSON + data URL images). */
  const [liveDeck, setLiveDeck] = useState<LiveSlidesResponse | null>(null)
  const [liveWarnings, setLiveWarnings] = useState<string[] | null>(null)

  const filteredSlideThemes = useMemo(() => {
    return SLIDE_TEMPLATES.filter((t) => {
      if (themeFilter && !t.filters.includes(themeFilter)) return false
      const q = themeSearch.trim().toLowerCase()
      if (!q) return true
      return (
        t.themeName.toLowerCase().includes(q) ||
        t.label.toLowerCase().includes(q) ||
        t.tagline.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q)
      )
    })
  }, [themeSearch, themeFilter])

  const selectedThemeDef = useMemo(
    () => SLIDE_TEMPLATES.find((t) => t.id === template) ?? SLIDE_TEMPLATES[0],
    [template],
  )

  function pickRandomTheme() {
    const pool = filteredSlideThemes.length ? filteredSlideThemes : [...SLIDE_TEMPLATES]
    const t = pool[Math.floor(Math.random() * pool.length)]
    if (t) setTemplate(t.id)
  }

  /** Body for ``POST /generate-slides`` (live React deck — same sources, no template). */
  function liveSlidesBody(): Record<string, unknown> {
    const base: Record<string, unknown> = {
      n_slides: nSlides,
      deck_title: sourceTitle.trim() || undefined,
      image_style: 'vector_science',
      presentation_detail: presentationDetail,
    }
    if (creationMode === 'generate') {
      base.source_text = promptLine.trim()
      return base
    }
    if (creationMode === 'paste') {
      base.source_text = pastedText.trim()
      return base
    }
    if (creationMode === 'import' && importUrl.trim()) {
      base.source_url = importUrl.trim()
      return base
    }
    base.document_id = docId.trim()
    return base
  }

  function validateSource(): string | null {
    if (creationMode === 'generate') {
      if (!promptLine.trim()) return 'Enter a one-line topic or prompt.'
      return null
    }
    if (creationMode === 'paste') {
      if (!pastedText.trim()) return 'Paste your notes or outline.'
      return null
    }
    if (creationMode === 'template') {
      if (!docId.trim()) return 'Choose a document from the library.'
      return null
    }
    if (creationMode === 'import') {
      if (!docId.trim() && !importUrl.trim()) return 'Pick a library document or enter a page URL (https…).'
      return null
    }
    return null
  }

  /** Live Gamma-style deck in the browser (Groq JSON + rotating layouts + images). */
  async function run() {
    const v = validateSource()
    if (v) {
      setError(v)
      return
    }
    setLoading(true)
    setError(null)
    setLiveDeck(null)
    setLiveWarnings(null)
    try {
      const res = await apiJson<LiveSlidesResponse>('/generate-slides', {
        method: 'POST',
        body: JSON.stringify(liveSlidesBody()),
      })
      assertLiveSlidesHaveImages(res)
      await preloadLiveSlideImages(res)
      if (import.meta.env.DEV) {
        const n = res.slides.length
        const withImg = res.slides.filter((s) => (s.image ?? '').trim().length > 0).length
        console.log('Slides:', n)
        console.log('Images:', withImg)
        console.assert(n === withImg, 'Every slide must have an image before setLiveDeck')
      }
      setLiveDeck(res)
      setLiveWarnings(res.warnings && res.warnings.length ? res.warnings : null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  async function exportPptx() {
    setError(null)
    if (!liveDeck?.slides?.length) {
      setError('Generate a live deck first, then export PowerPoint.')
      return
    }
    assertLiveSlidesHaveImages(liveDeck)
    setExporting(true)
    try {
      const { blob, filename } = await apiPostBlob('/generate-slides/export-pptx', {
        slides: liveDeck.slides,
      })
      triggerDownload(blob, filename.endsWith('.pptx') ? filename : `${filename}.pptx`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const canRun = validateSource() === null

  return (
    <>
      <h1 className="page-title">Slides</h1>
      <p className="page-sub">
        <strong>Create with AI</strong> — pick how you want to start.
      </p>

      <h2 style={{ fontSize: '1.1rem', margin: '0 0 0.75rem', fontWeight: 600 }}>How would you like to get started?</h2>
      <div style={cardGrid}>
        {CREATION_CARDS.map((c) => {
          const active = creationMode === c.id
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => {
                setCreationMode(c.id)
                setError(null)
              }}
              style={{
                ...cardBase,
                borderColor: active ? 'var(--accent, #3b5bdb)' : cardBase.border as string,
                boxShadow: active ? '0 0 0 2px color-mix(in srgb, var(--accent, #3b5bdb) 25%, transparent)' : 'none',
              }}
            >
              <div style={{ fontSize: '1.75rem', marginBottom: '0.35rem', opacity: 0.85 }}>{c.icon}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexWrap: 'wrap' }}>
                <strong style={{ fontSize: '1rem' }}>{c.title}</strong>
                {c.badge && (
                  <span
                    style={{
                      fontSize: '0.65rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      color: 'var(--ink-soft)',
                      border: '1px solid var(--line)',
                      borderRadius: '4px',
                      padding: '0.1rem 0.35rem',
                    }}
                  >
                    {c.badge}
                  </span>
                )}
              </div>
              <p style={{ margin: '0.45rem 0 0', fontSize: '0.85rem', color: 'var(--ink-soft)', lineHeight: 1.35 }}>
                {c.description}
              </p>
            </button>
          )
        })}
      </div>

      <div className="panel" style={{ marginBottom: '1.25rem' }}>
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.05rem' }}>Source</h2>

        {creationMode === 'generate' && (
          <div className="field">
            <label htmlFor="oneprompt">One-line prompt</label>
            <input
              id="oneprompt"
              type="text"
              value={promptLine}
              onChange={(e) => setPromptLine(e.target.value)}
              placeholder="e.g. Intro deck on photosynthesis for grade 9 biology"
            />
            <p style={{ margin: '0.35rem 0 0', fontSize: '0.85rem', color: 'var(--ink-soft)' }}>
              The model expands this into a full deck outline, then slide images follow each slide topic.
            </p>
          </div>
        )}

        {creationMode === 'paste' && (
          <div className="field">
            <label htmlFor="paste">Notes or outline</label>
            <textarea
              id="paste"
              rows={10}
              value={pastedText}
              onChange={(e) => setPastedText(e.target.value)}
              placeholder="Paste bullets, a lesson plan, or raw notes…"
              style={{ width: '100%', fontFamily: 'inherit', fontSize: '0.95rem' }}
            />
          </div>
        )}

        {(creationMode === 'generate' || creationMode === 'paste') && (
          <div className="field">
            <label htmlFor="dtitle">Deck title (optional)</label>
            <input
              id="dtitle"
              type="text"
              value={sourceTitle}
              onChange={(e) => setSourceTitle(e.target.value)}
              placeholder="Shown as the presentation title when set"
            />
          </div>
        )}

        {(creationMode === 'template' || creationMode === 'import') && (
          <>
            <DocPicker
              value={docId ? [docId] : []}
              onChange={(ids) => setDocId(ids[0] ?? '')}
              accept=".pdf,.docx,.pptx,.txt,.md"
            />
            {creationMode === 'import' && (
              <div className="field" style={{ marginTop: '1rem' }}>
                <label htmlFor="url">Or import from URL</label>
                <input
                  id="url"
                  type="url"
                  value={importUrl}
                  onChange={(e) => setImportUrl(e.target.value)}
                  placeholder="https://… (article or page; text is extracted on the server)"
                />
                {importUrl.trim() ? (
                  <p style={{ margin: '0.35rem 0 0', fontSize: '0.85rem', color: 'var(--ink-soft)' }}>
                    When a URL is set, it is used instead of the library document for this run.
                  </p>
                ) : null}
              </div>
            )}
          </>
        )}
      </div>

      <div className="panel">
        <h2 style={{ margin: '0 0 1rem', fontSize: '1.05rem' }}>Slide options</h2>
        <div className="field">
          <div id="slide-theme-heading" style={{ fontWeight: 600, fontSize: '1.02rem', marginBottom: '0.35rem' }}>
            Writing tone
          </div>
          <p style={{ margin: '0 0 0.85rem', fontSize: '0.82rem', color: 'var(--ink-soft)', maxWidth: '52rem' }}>
            Choose how Groq <strong>writes</strong> titles, bullets, and speaker notes (density and voice). The gallery
            preview reflects writing tone only. <strong>Export PowerPoint</strong> sends the same slide JSON as this page
            and renders each slide as a full-bleed image so the deck matches the preview layout (rounded cards, grids,
            split layouts). Requires Playwright/Chromium on the API server; if HTML export is unavailable, the server
            falls back to a simpler python-pptx layout. Three equal cards in a row appear when the JSON sets{' '}
            <code style={{ fontSize: '0.78rem' }}>layout: grid_triple</code>.
          </p>
          <div
            style={{
              display: 'flex',
              flexDirection: 'row',
              flexWrap: 'wrap',
              gap: '1.25rem',
              alignItems: 'stretch',
            }}
          >
            {/* Left: gallery (Gamma-style) */}
            <div
              role="radiogroup"
              aria-labelledby="slide-theme-heading"
              style={{
                flex: '1 1 260px',
                maxWidth: '100%',
                minWidth: '220px',
                border: '1px solid var(--line, #e2e8f0)',
                borderRadius: '14px',
                padding: '0.85rem 0.9rem',
                background: 'var(--panel, #fff)',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>All tones</div>
              <p style={{ margin: '0.15rem 0 0.65rem', fontSize: '0.78rem', color: 'var(--ink-soft)' }}>
                View and select a writing tone for the model.
              </p>
              <div style={{ display: 'flex', gap: '0.45rem', marginBottom: '0.55rem' }}>
                <input
                  type="search"
                  value={themeSearch}
                  onChange={(e) => setThemeSearch(e.target.value)}
                  placeholder="Search for a tone"
                  aria-label="Search writing tones"
                  style={{
                    flex: 1,
                    minWidth: 0,
                    padding: '0.45rem 0.55rem',
                    borderRadius: '10px',
                    border: '1px solid var(--line, #e2e8f0)',
                    fontSize: '0.85rem',
                  }}
                />
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => pickRandomTheme()}
                  title="Pick a random writing tone"
                  style={{ padding: '0.45rem 0.6rem', flexShrink: 0 }}
                >
                  ↻
                </button>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginBottom: '0.65rem' }}>
                {THEME_FILTER_CHIPS.map((chip) => {
                  const on = themeFilter === chip.id
                  return (
                    <button
                      key={chip.id}
                      type="button"
                      onClick={() => setThemeFilter(on ? null : chip.id)}
                      style={{
                        padding: '0.28rem 0.55rem',
                        borderRadius: '999px',
                        fontSize: '0.75rem',
                        border: on ? '1px solid var(--accent, #3b5bdb)' : '1px solid var(--line, #e2e8f0)',
                        background: on ? 'color-mix(in srgb, var(--accent, #3b5bdb) 14%, transparent)' : 'transparent',
                        cursor: 'pointer',
                        color: 'var(--ink, inherit)',
                      }}
                    >
                      {chip.label}
                    </button>
                  )
                })}
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '0.5rem',
                  maxHeight: '380px',
                  overflowY: 'auto',
                  paddingRight: '2px',
                }}
              >
                {filteredSlideThemes.map((t) => {
                  const selected = template === t.id
                  const p = t.preview
                  return (
                    <button
                      key={t.id}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      aria-label={`Writing tone ${t.themeName}: ${t.label}`}
                      onClick={() => setTemplate(t.id)}
                      style={{
                        textAlign: 'left',
                        cursor: 'pointer',
                        borderRadius: '12px',
                        padding: '0.45rem',
                        border: selected
                          ? '2px solid var(--accent, #3b5bdb)'
                          : '1px solid var(--line, #e2e8f0)',
                        background: selected
                          ? 'color-mix(in srgb, var(--accent, #3b5bdb) 10%, transparent)'
                          : 'var(--panel, #fff)',
                        outline: 'none',
                      }}
                    >
                      <div
                        style={{
                          borderRadius: '8px',
                          minHeight: '72px',
                          padding: '0.3rem',
                          background: p.outerBg,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <div
                          style={{
                            width: '100%',
                            borderRadius: '6px',
                            background: p.cardBg,
                            padding: '0.28rem 0.32rem',
                            boxShadow: p.boxShadow,
                          }}
                        >
                          <div style={{ font: p.titleFont, color: p.titleColor, lineHeight: 1.1 }}>Title</div>
                          <div style={{ font: p.bodyFont, color: p.bodyColor, marginTop: '3px', lineHeight: 1.15 }}>
                            Body & link
                          </div>
                        </div>
                      </div>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.25rem',
                          marginTop: '0.35rem',
                        }}
                      >
                        <span style={{ fontWeight: 700, fontSize: '0.78rem' }}>{t.themeName}</span>
                        {selected ? (
                          <span style={{ color: 'var(--accent, #3b5bdb)', fontSize: '0.85rem' }} aria-hidden>
                            ✓
                          </span>
                        ) : null}
                      </div>
                    </button>
                  )
                })}
              </div>
              {filteredSlideThemes.length === 0 ? (
                <p style={{ margin: '0.5rem 0 0', fontSize: '0.8rem', color: 'var(--ink-soft)' }}>
                  No tones match — clear search or filters.
                </p>
              ) : null}
            </div>

            {/* Right: large layered preview */}
            <div
              style={{
                flex: '2 1 320px',
                minWidth: 'min(100%, 320px)',
                borderRadius: '16px',
                padding: '1rem 1.1rem 1.15rem',
                background: selectedThemeDef.hero.workspace,
                border: '1px solid var(--line, #e2e8f0)',
                position: 'relative',
              }}
            >
              <div style={{ fontSize: '0.78rem', color: selectedThemeDef.preview.bodyColor, marginBottom: '0.45rem' }}>
                Selected: <strong>{selectedThemeDef.themeName}</strong> · {selectedThemeDef.label}
              </div>
              <div
                style={{
                  fontSize: '1.05rem',
                  fontWeight: 700,
                  color: '#94a3b8',
                  marginBottom: '0.55rem',
                  fontFamily: 'ui-sans-serif, system-ui, sans-serif',
                }}
              >
                This is a heading
              </div>
              <div
                style={{
                  background: selectedThemeDef.preview.cardBg,
                  borderRadius: '20px',
                  boxShadow: selectedThemeDef.preview.boxShadow,
                  padding: '1.1rem 1.15rem',
                  border: '1px solid rgba(15, 23, 42, 0.06)',
                }}
              >
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(0, 1fr) minmax(108px, 34%)',
                    gap: '1rem',
                    alignItems: 'start',
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontSize: '0.8rem',
                        color: selectedThemeDef.preview.bodyColor,
                        marginBottom: '0.35rem',
                      }}
                    >
                      Hello 👋
                    </div>
                    <h3
                      style={{
                        margin: '0 0 0.45rem',
                        fontSize: '1.2rem',
                        fontWeight: 700,
                        color: selectedThemeDef.preview.titleColor,
                        lineHeight: 1.2,
                        fontFamily:
                          selectedThemeDef.id === 'executive_summary'
                            ? 'Georgia, "Times New Roman", serif'
                            : selectedThemeDef.id === 'deep_technical'
                              ? 'ui-monospace, Menlo, monospace'
                              : 'ui-sans-serif, system-ui, sans-serif',
                      }}
                    >
                      This is a theme preview
                    </h3>
                    <p
                      style={{
                        margin: '0 0 0.45rem',
                        fontSize: '0.82rem',
                        lineHeight: 1.45,
                        color: selectedThemeDef.preview.bodyColor,
                        fontFamily: 'ui-sans-serif, system-ui, sans-serif',
                      }}
                    >
                      Fonts, colors, and slide density follow this tone when Groq writes your deck. Swap themes anytime
                      before you generate.
                    </p>
                    <a
                      href="#"
                      onClick={(e) => e.preventDefault()}
                      style={{
                        fontSize: '0.82rem',
                        fontWeight: 600,
                        color: selectedThemeDef.hero.linkColor,
                        textDecoration: 'underline',
                        fontFamily: 'ui-sans-serif, system-ui, sans-serif',
                      }}
                    >
                      Learn more about this tone
                    </a>
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        gap: '0.45rem',
                        marginTop: '0.65rem',
                      }}
                    >
                      <div
                        style={{
                          borderRadius: '12px',
                          padding: '0.45rem 0.5rem',
                          fontSize: '0.72rem',
                          lineHeight: 1.35,
                          color: selectedThemeDef.preview.bodyColor,
                          background: selectedThemeDef.hero.smartFill,
                          border: `1px solid ${selectedThemeDef.hero.smartBorder}`,
                        }}
                      >
                        Smart layout: use as a text block for two parallel ideas on one slide.
                      </div>
                      <div
                        style={{
                          borderRadius: '12px',
                          padding: '0.45rem 0.5rem',
                          fontSize: '0.72rem',
                          lineHeight: 1.35,
                          color: selectedThemeDef.preview.bodyColor,
                          background: selectedThemeDef.hero.smartFill,
                          border: `1px solid ${selectedThemeDef.hero.smartBorder}`,
                        }}
                      >
                        Second block: comparisons, steps, or before / after.
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem', marginTop: '0.75rem' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '0.38rem 0.75rem',
                          borderRadius: '999px',
                          fontSize: '0.78rem',
                          fontWeight: 600,
                          background: selectedThemeDef.hero.btnBg,
                          color: selectedThemeDef.hero.btnText,
                          fontFamily: 'ui-sans-serif, system-ui, sans-serif',
                        }}
                      >
                        Primary button
                      </span>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '0.38rem 0.75rem',
                          borderRadius: '999px',
                          fontSize: '0.78rem',
                          fontWeight: 600,
                          border: `1px solid ${selectedThemeDef.hero.btnGhostBorder}`,
                          color: selectedThemeDef.preview.titleColor,
                          background: 'transparent',
                          fontFamily: 'ui-sans-serif, system-ui, sans-serif',
                        }}
                      >
                        Secondary button
                      </span>
                    </div>
                  </div>
                  <div
                    style={{
                      borderRadius: '28% 72% 40% 60% / 45% 35% 65% 55%',
                      background: selectedThemeDef.hero.imageWell,
                      minHeight: '168px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#94a3b8',
                      fontSize: '2rem',
                      opacity: 0.95,
                    }}
                    aria-hidden
                  >
                    🖼
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="field">
          <label htmlFor="ns">Number of slides</label>
          <input
            id="ns"
            type="number"
            min={1}
            max={20}
            value={nSlides}
            onChange={(e) => {
              const raw = Number(e.target.value)
              if (!Number.isFinite(raw)) return
              setNSlides(Math.min(20, Math.max(1, Math.round(raw))))
            }}
          />
          <p style={{ margin: '0.35rem 0 0', fontSize: '0.82rem', color: 'var(--ink-soft)' }}>
            Live generation accepts 1–20 slides (server validation).
          </p>
        </div>
        <div className="field">
          <label htmlFor="pres-depth">Presentation depth</label>
          <select
            id="pres-depth"
            value={presentationDetail}
            onChange={(e) => setPresentationDetail(e.target.value as 'standard' | 'deep')}
          >
            <option value="standard">Standard — balanced teaching bullets</option>
            <option value="deep">Deep — longer bullets, trade-offs, arc, synthesis on last slide</option>
          </select>
          <p style={{ margin: '0.35rem 0 0', fontSize: '0.82rem', color: 'var(--ink-soft)' }}>
            Deep mode requests more text from Groq (bigger payload; may hit rate limits on free tiers).
          </p>
        </div>
        <div className="field">
          <span className="summarize-field-label">Slide images</span>
          <p style={{ margin: '0.35rem 0 0', fontSize: '0.85rem', color: 'var(--ink-soft)' }}>
            Images use the automatic science-style vector look from each slide’s title and bullets (<code>vector_science</code>
            on the server). HF / xAI / OpenAI when configured; otherwise local placeholders.
          </p>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
          <button
            type="button"
            className="btn btn--accent"
            disabled={loading || !canRun}
            onClick={() => void run()}
          >
            {loading ? 'Building live deck…' : 'Generate slides (live)'}
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            disabled={exporting || !liveDeck?.slides?.length}
            onClick={() => void exportPptx()}
          >
            {exporting ? 'Building PowerPoint…' : 'Export PowerPoint (.pptx)'}
          </button>
        </div>
        {loading && (
          <p style={{ margin: '0.65rem 0 0', fontSize: '0.88rem', color: 'var(--ink-soft)' }} aria-live="polite">
            <span
              style={{
                display: 'inline-block',
                width: '0.85rem',
                height: '0.85rem',
                marginRight: '0.45rem',
                border: '2px solid color-mix(in srgb, var(--accent, #3b5bdb) 35%, transparent)',
                borderTopColor: 'var(--accent, #3b5bdb)',
                borderRadius: '50%',
                animation: 'live-spin 0.7s linear infinite',
                verticalAlign: '-0.15em',
              }}
            />
            Calling Groq and rendering slide images…
          </p>
        )}
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.82rem', color: 'var(--ink-soft)', maxWidth: '44rem' }}>
          Slides preview at 1280×720 (16:9). Exported .pptx uses server-side HTML/CSS → Playwright screenshots at
          1920×1080 (Gamma-style full-bleed slides). If Playwright is unavailable, the API falls back to python-pptx
          layout export. Only slide 1 gets an AI/stock image attempt (slides 2–N are always simple color tiles by design,
          not full photos). If slide 1’s image fails, the server tries Pollinations, then optional stock keys, then a
          local gradient preview.
        </p>
      </div>

      {error && <div className="error">{error}</div>}

      {liveWarnings && liveWarnings.length > 0 && (
        <div
          className="panel"
          style={{
            marginTop: '1.25rem',
            padding: '0.9rem 1.1rem',
            borderRadius: '12px',
            background: 'color-mix(in srgb, var(--accent, #c17f59) 12%, transparent)',
            border: '1px solid color-mix(in srgb, var(--accent, #c17f59) 35%, transparent)',
            fontSize: '0.9rem',
            lineHeight: 1.45,
          }}
        >
          <strong>Images:</strong> No image API returned a picture (often <strong>HF quota / 402</strong>). Slides used{' '}
          <strong>local placeholders</strong>. Fixes: add <code>OPENAI_API_KEY</code> or <code>XAI_API_KEY</code>, top up
          HF credits, <strong>or remove</strong> <code>SLIDE_IMAGE_PROVIDER=huggingface</code> from{' '}
          <code>.env</code> so all keys are tried in order (HF → xAI → OpenAI). Optionally{' '}
          <code>SLIDE_IMAGE_TRY_ORDER=openai,xai,huggingface</code>.
          <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.2rem' }}>
            {liveWarnings.slice(0, 6).map((w, i) => (
              <li key={i} style={{ marginBottom: '0.25rem' }}>
                {w}
              </li>
            ))}
          </ul>
          {liveWarnings.length > 6 && (
            <p style={{ margin: '0.35rem 0 0', fontSize: '0.85rem', opacity: 0.9 }}>
              …and {liveWarnings.length - 6} more.
            </p>
          )}
        </div>
      )}

      {liveDeck && liveDeck.slides.length > 0 && (
        <div className="panel" style={{ marginTop: '1.25rem', minWidth: 0 }}>
          <LiveSlideDeck deck={liveDeck} workspaceBg={selectedThemeDef.preview.outerBg} />
        </div>
      )}

    </>
  )
}
