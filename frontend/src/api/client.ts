/**
 * Base URL for FastAPI (no trailing slash).
 * - In **dev**, if `VITE_API_URL` is unset, use same-origin paths so Vite’s `server.proxy` forwards to FastAPI
 *   (fixes common “Cannot reach http://127.0.0.1:8000” when the app is opened at `http://localhost:5173`).
 * - Set `VITE_API_URL` in `.env.local` to hit a different host (e.g. LAN IP) or for production builds.
 */
function resolveApiBase(): string {
  const explicit = import.meta.env.VITE_API_URL?.replace(/\/$/, '').trim()
  if (explicit) return explicit
  if (import.meta.env.DEV) return ''
  return 'http://127.0.0.1:8000'
}

export const API_BASE = resolveApiBase()

/** Turn FastAPI / Starlette error bodies into a short readable message. */
export function parseHttpErrorBody(text: string, status: number, statusText: string): string {
  const raw = (text || '').trim()
  if (!raw) return `${status} ${statusText}`.trim()
  try {
    const j = JSON.parse(raw) as { detail?: unknown }
    const d = j?.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) {
      const parts = d.map((item: unknown) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg?: string }).msg || '')
        }
        return ''
      })
      const joined = parts.filter(Boolean).join(' ')
      if (joined) return joined
    }
  } catch {
    /* not JSON */
  }
  if (raw.length > 800) return `${raw.slice(0, 800)}…`
  return raw
}

function wrapNetworkError(err: unknown): Error {
  if (err instanceof TypeError) {
    const where =
      API_BASE.trim() !== ''
        ? API_BASE
        : `${typeof window !== 'undefined' ? window.location.origin : ''} → Vite proxy → http://127.0.0.1:8000`
    return new Error(
      `Cannot reach the API (${where}).\n\n` +
        `1) Backend (repo root, venv activated):\n` +
        `   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000\n\n` +
        `2) Restart the frontend so Vite picks up the dev proxy: npm run dev\n\n` +
        `3) Optional: in frontend/.env.local set VITE_API_URL=http://127.0.0.1:8000 (no slash) to skip the proxy.\n\n` +
        `4) Open http://127.0.0.1:8000/docs — if that fails, the API is not running.`
    )
  }
  return err instanceof Error ? err : new Error(String(err))
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers || {}),
      },
    })
  } catch (e) {
    throw wrapNetworkError(e)
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(parseHttpErrorBody(text, res.status, res.statusText))
  }
  return res.json() as Promise<T>
}

export async function apiUpload(
  path: string,
  files: FileList | File[]
): Promise<unknown> {
  const fd = new FormData()
  const list = Array.from(files)
  for (const f of list) fd.append('files', f)
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { method: 'POST', body: fd })
  } catch (e) {
    throw wrapNetworkError(e)
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(parseHttpErrorBody(text, res.status, res.statusText))
  }
  return res.json()
}

export async function apiFormJson<T>(path: string, formData: FormData): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { method: 'POST', body: formData })
  } catch (e) {
    throw wrapNetworkError(e)
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(parseHttpErrorBody(text, res.status, res.statusText))
  }
  return res.json() as Promise<T>
}

/**
 * Consume a Server-Sent Events endpoint and yield each parsed event payload.
 * Each SSE line must be: `data: <json>\n\n`
 */
export async function* apiStream<T>(
  path: string,
  init?: RequestInit
): AsyncGenerator<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers || {}),
      },
    })
  } catch (e) {
    throw wrapNetworkError(e)
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(parseHttpErrorBody(text, res.status, res.statusText))
  }

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          yield JSON.parse(line.slice(6)) as T
        } catch {
          // skip malformed line
        }
      }
    }
  }
}

/** Server-sent events from ``POST /evaluation/grade/batch/stream`` (progress + final result). */
export type EvaluationBatchGradeProgress = {
  completed: number
  total: number
  current_title: string
  elapsed_sec: number
  estimated_remaining_sec: number | null
}

export type EvaluationBatchGradeStreamResult = {
  records?: unknown[]
  batch_id?: string
  batch_name?: string
  stats?: Record<string, unknown>
}

export async function apiPostEvaluationBatchGradeStream(
  body: object,
  onProgress: (p: EvaluationBatchGradeProgress) => void,
): Promise<EvaluationBatchGradeStreamResult> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/evaluation/grade/batch/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (e) {
    throw wrapNetworkError(e)
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(parseHttpErrorBody(text, res.status, res.statusText))
  }
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalPayload: EvaluationBatchGradeStreamResult | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      let data: Record<string, unknown>
      try {
        data = JSON.parse(line.slice(6)) as Record<string, unknown>
      } catch {
        continue
      }
      const ev = data.event
      if (ev === 'progress') {
        onProgress({
          completed: Number(data.completed) || 0,
          total: Number(data.total) || 0,
          current_title: String(data.current_title ?? ''),
          elapsed_sec: Number(data.elapsed_sec) || 0,
          estimated_remaining_sec:
            data.estimated_remaining_sec === null || data.estimated_remaining_sec === undefined
              ? null
              : Number(data.estimated_remaining_sec),
        })
      } else if (ev === 'complete') {
        const r = data.result
        finalPayload =
          r && typeof r === 'object' && !Array.isArray(r)
            ? (r as EvaluationBatchGradeStreamResult)
            : { records: [] }
      } else if (ev === 'error') {
        const detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? 'Error')
        throw new Error(detail)
      }
    }
  }

  if (!finalPayload) {
    throw new Error('Batch grading stream ended without a result.')
  }
  return finalPayload
}

export async function apiDownload(
  path: string,
  init?: RequestInit
): Promise<{ blob: Blob; filename: string }> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, init)
  } catch (e) {
    throw wrapNetworkError(e)
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(parseHttpErrorBody(text, res.status, res.statusText))
  }

  const disposition = res.headers.get('content-disposition') || ''
  const match = disposition.match(/filename="([^"]+)"/i)
  return {
    blob: await res.blob(),
    filename: match?.[1] || 'download',
  }
}

/** POST JSON, return binary (e.g. PPTX / Moodle XML). Parses filename from Content-Disposition when present. */
export async function apiPostBlob(path: string, body: object): Promise<{ blob: Blob; filename: string }> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (e) {
    throw wrapNetworkError(e)
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(parseHttpErrorBody(text, res.status, res.statusText))
  }
  let filename = 'download'
  const cd = res.headers.get('Content-Disposition')
  if (cd) {
    const m = cd.match(/filename="([^"]+)"/) || cd.match(/filename=([^;]+)/)
    if (m) filename = m[1].trim().replace(/^"|"$/g, '')
  }
  const blob = await res.blob()
  return { blob, filename }
}

export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
