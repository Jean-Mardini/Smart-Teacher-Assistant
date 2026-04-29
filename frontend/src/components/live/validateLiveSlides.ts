import type { LiveSlidesResponse } from './liveSlides.types'

/** Aligns loosely with backend ``is_valid_live_slide_data_url``. */
function decodeDataUrlToBytes(s: string): Uint8Array | null {
  if (!s?.trim()) return null
  const low = s.toLowerCase()
  const marker = 'base64,'
  const idx = low.indexOf(marker)
  if (idx < 0) return null
  let b64 = s.slice(idx + marker.length).trim().replace(/\s/g, '').replace(/^"|"$/g, '')
  if (!b64.length) return null
  try {
    const pad = b64.length % 4 === 0 ? '' : '='.repeat(4 - (b64.length % 4))
    const bin = atob(b64 + pad)
    return Uint8Array.from(bin, (c) => c.charCodeAt(0))
  } catch {
    return null
  }
}

/** PNG IHDR width/height; only for standard layout (IHDR first chunk). */
function readPngIhdrDimensions(bytes: Uint8Array): { w: number; h: number } | null {
  if (bytes.length < 24) return null
  const sig = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]
  for (let i = 0; i < 8; i++) if (bytes[i] !== sig[i]) return null
  const w = (bytes[16] << 24) | (bytes[17] << 16) | (bytes[18] << 8) | bytes[19]
  const h = (bytes[20] << 24) | (bytes[21] << 16) | (bytes[22] << 8) | bytes[23]
  if (w > 0 && w < 1_000_000 && h > 0 && h < 1_000_000) return { w, h }
  return null
}

/**
 * Backend may embed `live_slide_placeholder_data_url`: valid but tiny solid-color PNGs.
 * Those must not render in the preview (they scale up as colored boxes).
 */
export function isLikelyPlaceholderSlideImage(s: string): boolean {
  const bytes = decodeDataUrlToBytes(s)
  if (!bytes?.length) return true
  const pngSig =
    bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47
  if (pngSig) {
    const dims = readPngIhdrDimensions(bytes)
    if (dims && dims.w <= 96 && dims.h <= 96) return true
    /* Minimal PNGs (e.g. 1×1 fallback) stay under ~120 bytes decoded */
    if (bytes.length < 140) return true
    return false
  }
  /* Tiny non-PNG payloads — treat as non-display */
  return bytes.length < 200
}

/**
 * True when the deck may show an `<img>` (non-empty, valid; tiny placeholders hidden except slide 0).
 * Slide 1 (index 0) is the live hero: backend may fall back to a small PNG — hiding it looked like “no image”.
 */
export function shouldDisplaySlideImage(
  s: string | undefined | null,
  slideIndex?: number,
): boolean {
  if (typeof s !== 'string' || !s.trim()) return false
  if (!isValidLiveSlideDataUrl(s)) return false
  if (slideIndex === 0) return true
  return !isLikelyPlaceholderSlideImage(s)
}

export function isValidLiveSlideDataUrl(s: string): boolean {
  if (!s?.trim()) return false
  const low = s.toLowerCase()
  const marker = 'base64,'
  const idx = low.indexOf(marker)
  if (idx < 0) return false
  let b64 = s.slice(idx + marker.length).trim().replace(/\s/g, '').replace(/^"|"$/g, '')
  if (!b64.length) return false
  try {
    const pad = b64.length % 4 === 0 ? '' : '='.repeat(4 - (b64.length % 4))
    const bin = atob(b64 + pad)
    const len = bin.length
    if (len >= 67) return true
    const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0))
    if (len >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47)
      return true
    if (len >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return true
    return len >= 32
  } catch {
    return false
  }
}

/** Throws if any slide is missing a usable image or duplicates another slide’s exact data URL string. */
export function assertLiveSlidesHaveImages(deck: LiveSlidesResponse): void {
  const slides = deck?.slides ?? []
  const missing: number[] = []
  slides.forEach((sl, i) => {
    const img = typeof sl?.image === 'string' ? sl.image : ''
    if (!isValidLiveSlideDataUrl(img)) missing.push(i)
  })
  if (missing.length) {
    throw new Error(
      `Live deck: missing or invalid image field at slide indices (0-based): ${missing.join(', ')}`,
    )
  }
  const seen = new Map<string, number>()
  slides.forEach((sl, i) => {
    const img = sl.image as string
    if (seen.has(img)) {
      throw new Error(
        `Slides ${seen.get(img)! + 1} and ${i + 1} share identical image data — export would be ambiguous.`,
      )
    }
    seen.set(img, i)
  })
}

/** Decode data URLs into ``<img>`` loads so screenshots capture pixels reliably. */
export async function preloadLiveSlideImages(deck: LiveSlidesResponse): Promise<void> {
  await Promise.all(
    deck.slides.map(
      (s) =>
        new Promise<void>((resolve) => {
          const im = new Image()
          im.decoding = 'async'
          im.onload = () => resolve()
          im.onerror = () => resolve()
          im.src = s.image
        }),
    ),
  )
}
