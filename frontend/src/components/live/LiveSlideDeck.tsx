import { useLayoutEffect, useRef, useState } from 'react'
import type { ComponentType, CSSProperties, ReactNode } from 'react'
import * as LucideIcons from 'lucide-react'
import type { LiveSlideSpec, LiveSlidesResponse } from './liveSlides.types'
import { shouldDisplaySlideImage } from './validateLiveSlides'

const SLIDE_W = 1280
const SLIDE_H = 720

/** Shared “card” panel — Gamma / Notion-style soft tiles; height follows content. */
const cardSurface: CSSProperties = {
  padding: 20,
  borderRadius: 20,
  background: '#eef3f8',
  border: '1px solid rgba(148, 163, 184, 0.35)',
  height: 'auto',
  maxWidth: 280,
  width: '100%',
  boxSizing: 'border-box',
  alignSelf: 'start',
  boxShadow: '0 8px 20px rgba(0, 0, 0, 0.05)',
  textAlign: 'left',
}

/** Slide canvas: soft gradient, generous radius; grows with content (no fixed height). */
const slideChrome: CSSProperties = {
  width: SLIDE_W,
  minHeight: SLIDE_H,
  height: 'auto',
  boxSizing: 'border-box',
  background: 'linear-gradient(135deg, #e6eef7 0%, #cfdceb 100%)',
  borderRadius: 30,
  boxShadow: '0 20px 44px rgba(15, 23, 42, 0.09)',
  overflow: 'hidden',
  display: 'flex',
  flexDirection: 'column',
  padding: 40,
  gap: 22,
}

/** Vertically + horizontally centers slide content (card grids, balanced decks). */
const slideBodyCentered: CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'center',
  alignItems: 'center',
  width: '100%',
  minHeight: 0,
  textAlign: 'center',
}

/** Vertical center only — keeps hero/text slides balanced without forcing centered text. */
const slideMainGrow: CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'center',
  minHeight: 0,
  width: '100%',
}

const titleCenterBlock: CSSProperties = {
  marginBottom: 20,
  width: '100%',
  maxWidth: 960,
  textAlign: 'center',
}

/** Horizontally centered row of cards; items align to top so heights can differ. */
const cardsRowFlex: CSSProperties = {
  display: 'flex',
  gap: 20,
  justifyContent: 'center',
  alignItems: 'flex-start',
  flexWrap: 'wrap',
  width: '100%',
}

/** Centered CSS grid of fixed-width cards. */
function cardsGridColumns(cols: number): CSSProperties {
  return {
    display: 'grid',
    gap: 20,
    width: '100%',
    justifyContent: 'center',
    justifyItems: 'center',
    alignItems: 'start',
    gridTemplateColumns: `repeat(${cols}, minmax(0, 280px))`,
  }
}

/** Scales slide to column width; clip height tracks content so short cards don’t leave a giant frame. */
function ScaledSlideFrame({ children }: { children: ReactNode }) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const slideRef = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(1)
  const [slidePxH, setSlidePxH] = useState(SLIDE_H)

  useLayoutEffect(() => {
    const outer = wrapRef.current
    const slide = slideRef.current
    if (!outer || !slide) return

    const sync = () => {
      const w = outer.clientWidth
      if (w > 0) setScale(Math.min(1, w / SLIDE_W))
      setSlidePxH(Math.max(SLIDE_H, slide.scrollHeight))
    }

    sync()
    const roOuter = new ResizeObserver(sync)
    const roSlide = new ResizeObserver(sync)
    roOuter.observe(outer)
    roSlide.observe(slide)
    return () => {
      roOuter.disconnect()
      roSlide.disconnect()
    }
  }, [])

  const scaledH = slidePxH * scale
  const scaledW = SLIDE_W * scale

  return (
    <div
      ref={wrapRef}
      style={{
        width: '100%',
        maxWidth: SLIDE_W,
        marginLeft: 'auto',
        marginRight: 'auto',
        minWidth: 0,
      }}
    >
      <div
        style={{
          width: scaledW,
          height: scaledH,
          margin: '0 auto',
          position: 'relative',
          overflow: 'hidden',
          borderRadius: 30,
        }}
      >
        <div
          ref={slideRef}
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            width: SLIDE_W,
            minHeight: SLIDE_H,
            height: 'auto',
            transform: `scale(${scale})`,
            transformOrigin: 'top left',
          }}
        >
          {children}
        </div>
      </div>
    </div>
  )
}

function BoldLine({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith('**') && p.endsWith('**') ? (
          <strong key={i}>{p.slice(2, -2)}</strong>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  )
}

function SlideImg({ src, compact, slideIndex }: { src: string; compact?: boolean; slideIndex?: number }) {
  if (!shouldDisplaySlideImage(src, slideIndex)) return null
  return (
    <img
      src={src}
      alt=""
      draggable={false}
      style={{
        width: '100%',
        height: compact ? 200 : '100%',
        objectFit: 'cover',
        borderRadius: 12,
        background: '#f1f5f9',
      }}
    />
  )
}

function IconMaybe({
  name,
  small,
  sizePx,
}: {
  name?: string | null
  small?: boolean
  sizePx?: number
}) {
  if (!name) return null
  const Cmp = (LucideIcons as unknown as Record<string, ComponentType<Record<string, unknown>>>)[name]
  if (!Cmp) return null
  const size = sizePx ?? (small ? 18 : 22)
  return <Cmp size={size} strokeWidth={1.75} />
}

const BULLET_ICON_CYCLE = [
  'CircleDot',
  'CheckCircle2',
  'ArrowRightCircle',
  'Sparkles',
  'Star',
] as const

function bulletIconForLine(i: number, themeIcon: string | undefined | null): string {
  if (themeIcon && i === 0) return themeIcon
  return BULLET_ICON_CYCLE[i % BULLET_ICON_CYCLE.length]
}

function SlideTitle({
  title,
  iconName,
  h2Style,
  centered,
  slideIndex = 0,
}: {
  title: string
  iconName?: string | null
  h2Style: CSSProperties
  centered?: boolean
  slideIndex?: number
}) {
  const numbered = slideIndex >= 1
  const displayTitle = numbered ? `${slideIndex}- ${title}` : title

  if (numbered) {
    return (
      <h2 style={{ ...h2Style, textAlign: centered ? 'center' : (h2Style.textAlign ?? undefined) }}>
        {displayTitle}
      </h2>
    )
  }

  if (!iconName) {
    return (
      <h2 style={{ ...h2Style, textAlign: centered ? 'center' : (h2Style.textAlign ?? undefined) }}>
        {title}
      </h2>
    )
  }
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        width: '100%',
        justifyContent: centered ? 'center' : 'flex-start',
        minWidth: 0,
      }}
    >
      <span
        aria-hidden
        style={{
          flexShrink: 0,
          width: 52,
          height: 52,
          borderRadius: 14,
          background: 'linear-gradient(145deg, #eff6ff 0%, #e0e7ff 100%)',
          display: 'grid',
          placeItems: 'center',
          color: '#1d4ed8',
          boxShadow: '0 4px 14px rgba(29, 78, 216, 0.14)',
        }}
      >
        <IconMaybe name={iconName} sizePx={28} />
      </span>
      <h2
        style={{
          ...h2Style,
          margin: 0,
          flex: centered ? '0 1 auto' : 1,
          minWidth: 0,
          textAlign: (centered ? 'center' : h2Style.textAlign ?? 'left') as CSSProperties['textAlign'],
        }}
      >
        {title}
      </h2>
    </div>
  )
}

function BulletList({
  bullets,
  slide,
  iconName,
}: {
  bullets: string[]
  slide: LiveSlideSpec
  iconName?: string | null
}) {
  const useIcons = Boolean(slide.use_icons && iconName)
  return (
    <ul
      style={{
        margin: 0,
        paddingLeft: useIcons ? 0 : '1.1rem',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        color: '#334155',
        fontSize: '1.05rem',
        lineHeight: 1.45,
        listStyle: useIcons ? 'none' : undefined,
      }}
    >
      {bullets.map((b, i) => (
        <li key={i} style={{ listStyle: useIcons ? 'none' : 'disc', marginLeft: useIcons ? 0 : undefined }}>
          <span style={{ display: 'inline-flex', gap: 10, alignItems: 'flex-start' }}>
            {useIcons ? <IconMaybe name={bulletIconForLine(i, iconName)} small /> : null}
            <span>
              <BoldLine text={b} />
            </span>
          </span>
        </li>
      ))}
    </ul>
  )
}

function SlideCard({
  slide,
  index,
}: {
  slide: LiveSlideSpec
  index: number
}) {
  const layout = (slide.layout || slide.type || 'split_left').toLowerCase()
  const title = slide.title?.trim() || 'Slide'
  const bullets = slide.bullets ?? []
  const img = slide.image
  const iconName = slide.icon ?? undefined
  const showImg = shouldDisplaySlideImage(img, index)

  const titleStyle: CSSProperties = {
    margin: 0,
    fontSize: index === 0 ? '2.1rem' : '1.75rem',
    fontWeight: 700,
    color: '#0f172a',
    letterSpacing: '-0.02em',
    lineHeight: 1.15,
  }

  const shell: CSSProperties = { ...slideChrome }

  const flexGrow: CSSProperties = { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 14 }

  /* ── Hero / image-forward (slide 0 + hero pool) ───────────────── */
  if (
    layout === 'split_right' ||
    layout === 'split_left' ||
    layout === 'feature' ||
    layout === 'highlight'
  ) {
    if (!showImg) {
      return (
        <div style={shell}>
          <div style={slideBodyCentered}>
            <div style={titleCenterBlock}>
              <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
            </div>
            <div style={{ width: '100%', maxWidth: 920, textAlign: 'left' }}>
              <BulletList bullets={bullets} slide={slide} iconName={iconName} />
            </div>
          </div>
        </div>
      )
    }
    const imgFirst = layout === 'split_left' || layout === 'feature' || layout === 'highlight'
    const row = (
      <div style={{ display: 'flex', flex: 1, gap: 28, minHeight: 0, alignItems: 'flex-start' }}>
        {imgFirst ? (
          <>
            <div style={{ flex: '0 0 54%', minWidth: 0 }}>
              <SlideImg src={img} slideIndex={index} />
            </div>
            <div style={{ ...flexGrow }}>
              <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} />
              <BulletList bullets={bullets} slide={slide} iconName={iconName} />
            </div>
          </>
        ) : (
          <>
            <div style={{ ...flexGrow }}>
              <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} />
              <BulletList bullets={bullets} slide={slide} iconName={iconName} />
            </div>
            <div style={{ flex: '0 0 54%', minWidth: 0 }}>
              <SlideImg src={img} slideIndex={index} />
            </div>
          </>
        )}
      </div>
    )
    return (
      <div style={shell}>
        <div style={slideMainGrow}>{row}</div>
      </div>
    )
  }

  if (layout === 'grid') {
    const top = bullets.slice(0, 2)
    const bottom = bullets.slice(2, 4)
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
          </div>
          {showImg ? (
            <div style={{ width: '100%', maxWidth: 880, marginBottom: 18 }}>
              <SlideImg src={img} slideIndex={index} />
            </div>
          ) : null}
          <div style={{ ...cardsGridColumns(2) }}>
          {[top, bottom].map((grp, gi) => (
            <div key={gi} style={{ ...cardSurface }}>
              {grp.map((b, i) => (
                <p key={i} style={{ margin: i ? '10px 0 0' : 0, color: '#334155', fontSize: '0.98rem' }}>
                  <BoldLine text={b} />
                </p>
              ))}
            </div>
          ))}
          </div>
        </div>
      </div>
    )
  }

  if (layout === 'top_bottom' || layout === 'image_top_text_bottom') {
    if (!showImg) {
      return (
        <div style={shell}>
          <div style={slideBodyCentered}>
            <div style={titleCenterBlock}>
              <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
            </div>
            <div style={{ width: '100%', maxWidth: 920, textAlign: 'left' }}>
              <BulletList bullets={bullets} slide={slide} iconName={iconName} />
            </div>
          </div>
        </div>
      )
    }
    return (
      <div style={shell}>
        <div style={slideMainGrow}>
          <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={{ ...titleStyle, flex: '0 0 auto' }} />
          <div style={{ flex: '0 0 46%', minHeight: 0 }}>
            <SlideImg src={img} slideIndex={index} />
          </div>
          <div style={flexGrow}>
            <BulletList bullets={bullets} slide={slide} iconName={iconName} />
          </div>
        </div>
      </div>
    )
  }

  if (layout === 'image_dominant') {
    if (!showImg) {
      return (
        <div style={shell}>
          <div style={slideBodyCentered}>
            <div style={titleCenterBlock}>
              <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
            </div>
            <div style={{ width: '100%', maxWidth: 920, textAlign: 'left' }}>
              <BulletList bullets={bullets.slice(0, 4)} slide={slide} iconName={iconName} />
            </div>
          </div>
        </div>
      )
    }
    return (
      <div style={shell}>
        <div style={slideMainGrow}>
          <div style={{ flex: '0 0 62%', minHeight: 0 }}>
            <SlideImg src={img} slideIndex={index} />
          </div>
          <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} />
          <BulletList bullets={bullets.slice(0, 4)} slide={slide} iconName={iconName} />
        </div>
      </div>
    )
  }

  if (layout === 'comparison') {
    const half = Math.max(1, Math.ceil(bullets.length / 2))
    const left = bullets.slice(0, half)
    const right = bullets.slice(half)
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          {showImg ? (
            <div style={{ width: '100%', maxWidth: 720, marginBottom: 16 }}>
              <SlideImg src={img} slideIndex={index} />
            </div>
          ) : null}
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={{ ...titleStyle, textAlign: 'center' }} centered />
          </div>
          <div style={{ ...cardsGridColumns(2) }}>
          {[left, right].map((col, ci) => (
            <div
              key={ci}
              style={{
                ...cardSurface,
                background: ci ? '#fffbeb' : '#eef3f8',
                borderColor: '#e2e8f0',
              }}
            >
              {col.map((b, i) => (
                <p key={i} style={{ margin: i ? 12 : 0, color: '#1e293b' }}>
                  <BoldLine text={b} />
                </p>
              ))}
            </div>
          ))}
          </div>
        </div>
      </div>
    )
  }

  /* ── Text-first / body layouts ───────────────── */
  if (layout === 'text_comparison') {
    const half = Math.max(1, Math.ceil(bullets.length / 2))
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
          </div>
          <div style={{ ...cardsGridColumns(2) }}>
            <div style={{ ...cardSurface }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {bullets.slice(0, half).map((b, i) => (
                  <p key={i} style={{ margin: 0, color: '#334155' }}>
                    <BoldLine text={b} />
                  </p>
                ))}
              </div>
            </div>
            <div style={{ ...cardSurface }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {bullets.slice(half).map((b, i) => (
                  <p key={i} style={{ margin: 0, color: '#334155' }}>
                    <BoldLine text={b} />
                  </p>
                ))}
              </div>
            </div>
          </div>
          {showImg ? (
            <div style={{ marginTop: 18, width: 280, maxWidth: '100%' }}>
              <SlideImg src={img} slideIndex={index} compact />
            </div>
          ) : null}
        </div>
      </div>
    )
  }

  if (layout === 'grid_cards_2x2' || layout === 'grid_cards_3') {
    const cols = layout === 'grid_cards_3' ? 3 : 2
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
          </div>
          <div style={{ ...cardsGridColumns(cols) }}>
            {bullets.slice(0, cols === 3 ? 9 : 8).map((b, i) => (
              <div key={i} style={{ ...cardSurface, fontSize: '0.95rem' }}>
                <BoldLine text={b} />
              </div>
            ))}
          </div>
          {showImg ? (
            <div style={{ marginTop: 18, width: 220, maxWidth: '100%' }}>
              <SlideImg src={img} slideIndex={index} compact />
            </div>
          ) : null}
        </div>
      </div>
    )
  }

  if (layout === 'timeline_horizontal' || layout === 'process_flow_boxes') {
    return (
      <div style={{ ...shell, gap: 22 }}>
        <div style={slideBodyCentered}>
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
          </div>
          <div style={{ ...cardsRowFlex }}>
            {bullets.slice(0, 6).map((b, i) => (
              <div
                key={i}
                style={{
                  flex: '0 1 280px',
                  minWidth: 0,
                  maxWidth: 280,
                  ...cardSurface,
                  background: `linear-gradient(180deg, #eef3f8 0%, ${i % 2 ? '#e8ecff' : '#e6faf0'} 100%)`,
                  fontSize: '0.88rem',
                }}
              >
                <div style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: 6 }}>Step {i + 1}</div>
                <BoldLine text={b} />
              </div>
            ))}
          </div>
          {showImg ? (
            <div style={{ marginTop: 18, width: '100%', maxWidth: 520 }}>
              <SlideImg src={img} slideIndex={index} compact />
            </div>
          ) : null}
        </div>
      </div>
    )
  }

  if (layout === 'timeline_vertical') {
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
          </div>
          <div
            style={{
              display: 'flex',
              gap: 24,
              alignItems: 'flex-start',
              justifyContent: 'center',
              flexWrap: 'wrap',
              width: '100%',
            }}
          >
            {showImg ? (
              <div style={{ width: 200, flexShrink: 0 }}>
                <SlideImg src={img} slideIndex={index} compact />
              </div>
            ) : null}
            <div
              style={{
                flex: '1 1 280px',
                maxWidth: showImg ? 560 : 720,
                textAlign: 'left',
                width: '100%',
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {bullets.map((b, i) => (
                  <div
                    key={i}
                    style={{
                      borderLeft: '4px solid #3b82f6',
                      paddingLeft: 14,
                      color: '#334155',
                    }}
                  >
                    <BoldLine text={b} />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (layout === 'icon_list') {
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
          </div>
          <div style={{ ...cardSurface, maxWidth: 720, width: '100%', textAlign: 'left' }}>
            <BulletList bullets={bullets} slide={{ ...slide, use_icons: true }} iconName={iconName} />
          </div>
          {showImg ? (
            <div style={{ marginTop: 20, width: 260, maxWidth: '100%' }}>
              <SlideImg src={img} slideIndex={index} compact />
            </div>
          ) : null}
        </div>
      </div>
    )
  }

  if (layout === 'quote_highlight') {
    const q = bullets[0] ?? title
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          <div
            style={{
              ...cardSurface,
              maxWidth: 720,
              fontSize: '1.35rem',
              fontStyle: 'italic',
              color: '#1e293b',
              borderLeft: '6px solid #6366f1',
              paddingLeft: 24,
              lineHeight: 1.5,
              textAlign: 'left',
            }}
          >
            <BoldLine text={q} />
          </div>
          {showImg ? (
            <div style={{ width: 300, maxWidth: '100%', marginTop: 20 }}>
              <SlideImg src={img} slideIndex={index} compact />
            </div>
          ) : null}
        </div>
      </div>
    )
  }

  if (layout === 'title_top_2_columns') {
    const mid = Math.max(1, Math.ceil(bullets.length / 2))
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={{ ...titleStyle, textAlign: 'center' }} centered />
          </div>
          <div style={{ ...cardsGridColumns(2) }}>
            <div style={{ ...cardSurface, width: '100%' }}>
              <BulletList bullets={bullets.slice(0, mid)} slide={slide} iconName={iconName} />
            </div>
            <div style={{ ...cardSurface, width: '100%' }}>
              <BulletList bullets={bullets.slice(mid)} slide={slide} iconName={iconName} />
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (layout === 'big_number_stats') {
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
          </div>
          <div style={{ ...cardsRowFlex }}>
            {bullets.slice(0, 4).map((b, i) => (
              <div
                key={i}
                style={{
                  flex: '0 1 280px',
                  minWidth: 0,
                  maxWidth: 280,
                  height: 'auto',
                  background: '#0f172a',
                  color: '#fff',
                  borderRadius: 20,
                  padding: 20,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'flex-start',
                  boxShadow: '0 8px 20px rgba(0, 0, 0, 0.12)',
                  textAlign: 'left',
                }}
              >
                <div style={{ fontSize: '2rem', fontWeight: 800, opacity: 0.95 }}>{i + 1}</div>
                <div style={{ marginTop: 10, fontSize: '0.92rem', opacity: 0.92 }}>
                  <BoldLine text={b} />
                </div>
              </div>
            ))}
          </div>
          {showImg ? (
            <div style={{ marginTop: 18, width: '100%', maxWidth: 420 }}>
              <SlideImg src={img} slideIndex={index} compact />
            </div>
          ) : null}
        </div>
      </div>
    )
  }

  if (layout === 'split_3_columns') {
    const third = Math.max(1, Math.ceil(bullets.length / 3))
    const c1 = bullets.slice(0, third)
    const c2 = bullets.slice(third, third * 2)
    const c3 = bullets.slice(third * 2)
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
          </div>
          <div style={{ ...cardsGridColumns(3) }}>
            {[c1, c2, c3].map((col, ci) => (
              <div key={ci} style={{ ...cardSurface, width: '100%' }}>
                <BulletList bullets={col} slide={slide} iconName={iconName} />
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (layout === 'callout_blocks') {
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, width: '100%' }}>
            {bullets.map((b, i) => (
              <div
                key={i}
                style={{
                  ...cardSurface,
                  background: i % 2 ? '#fff7ed' : '#eef3f8',
                  borderColor: '#fde68a',
                }}
              >
                <BoldLine text={b} />
              </div>
            ))}
          </div>
          {showImg ? (
            <div style={{ marginTop: 18, width: 240, maxWidth: '100%' }}>
              <SlideImg src={img} slideIndex={index} compact />
            </div>
          ) : null}
        </div>
      </div>
    )
  }

  if (layout === 'stacked_sections' || layout === 'feature_highlight') {
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, width: '100%' }}>
            {bullets.map((b, i) => (
              <div
                key={i}
                style={{
                  ...cardSurface,
                  background: i % 2 ? '#eef3f8' : '#ffffff',
                  borderColor: '#e2e8f0',
                }}
              >
                <BoldLine text={b} />
              </div>
            ))}
          </div>
          {showImg ? (
            <div style={{ marginTop: 18, width: '100%', maxWidth: 400 }}>
              <SlideImg src={img} slideIndex={index} compact />
            </div>
          ) : null}
        </div>
      </div>
    )
  }

  if (layout === 'text_only_centered' || layout === 'text_only') {
    return (
      <div
        style={{
          ...shell,
          justifyContent: 'center',
          alignItems: 'center',
          textAlign: 'center',
          position: 'relative',
        }}
      >
        <div style={{ maxWidth: 880 }}>
          <div style={{ marginBottom: 20 }}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={{ ...titleStyle, marginBottom: 0 }} centered />
          </div>
          <BulletList bullets={bullets} slide={slide} iconName={iconName} />
        </div>
        {showImg ? (
          <div style={{ position: 'absolute', bottom: 28, right: 40, width: 200 }}>
            <SlideImg src={img} slideIndex={index} compact />
          </div>
        ) : null}
      </div>
    )
  }

  /* Default: split_left */
  if (!showImg) {
    return (
      <div style={shell}>
        <div style={slideBodyCentered}>
          <div style={titleCenterBlock}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} centered />
          </div>
          <div style={{ width: '100%', maxWidth: 920, textAlign: 'left' }}>
            <BulletList bullets={bullets} slide={slide} iconName={iconName} />
          </div>
        </div>
      </div>
    )
  }
  return (
    <div style={shell}>
      <div style={slideMainGrow}>
        <div style={{ display: 'flex', flex: 1, gap: 28, minHeight: 0, alignItems: 'flex-start' }}>
          <div style={{ flex: '0 0 54%', minWidth: 0 }}>
            <SlideImg src={img} slideIndex={index} />
          </div>
          <div style={flexGrow}>
            <SlideTitle slideIndex={index} title={title} iconName={iconName} h2Style={titleStyle} />
            <BulletList bullets={bullets} slide={slide} iconName={iconName} />
          </div>
        </div>
      </div>
    </div>
  )
}

export type LiveSlideDeckProps = {
  deck: LiveSlidesResponse
  workspaceBg: string
}

export function LiveSlideDeck({ deck, workspaceBg }: LiveSlideDeckProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '2.5rem',
        padding: '1rem 0 2rem',
        background: workspaceBg,
        borderRadius: 12,
        width: '100%',
        minWidth: 0,
        boxSizing: 'border-box',
      }}
    >
      <p style={{ margin: 0, fontSize: '0.95rem', color: '#475569', fontWeight: 600 }}>
        {deck.deck_title}
      </p>
      {deck.slides.map((slide, i) => (
        <ScaledSlideFrame key={i}>
          <SlideCard slide={slide} index={i} />
        </ScaledSlideFrame>
      ))}
    </div>
  )
}
