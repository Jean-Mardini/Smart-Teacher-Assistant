/** Base URL for FastAPI (no trailing slash). */
export const API_BASE =
  import.meta.env.VITE_API_URL?.replace(/\/$/, '') || 'http://127.0.0.1:8000'

function wrapNetworkError(err: unknown): Error {
  if (err instanceof TypeError) {
    return new Error(
      `Cannot reach the API at ${API_BASE}.\n\n` +
        `1) Start the backend (project folder, venv on):\n` +
        `   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000\n\n` +
        `2) In frontend/.env.local set:\n` +
        `   VITE_API_URL=http://127.0.0.1:8000\n\n` +
        `3) Restart: npm run dev\n\n` +
        `4) Open http://127.0.0.1:8000/docs — if that fails, the API is not running.`
    )
  }
  return err instanceof Error ? err : new Error(String(err))
}

export async function apiJson<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 12_000
): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: init?.signal ?? controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers || {}),
      },
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new Error(`Request timed out (${timeoutMs / 1000}s). Is the backend running?`)
    }
    throw wrapNetworkError(e)
  } finally {
    window.clearTimeout(timer)
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `${res.status} ${res.statusText}`)
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
    throw new Error(text || `${res.status}`)
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
    throw new Error(text || `${res.status}`)
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
    throw new Error(text || `${res.status} ${res.statusText}`)
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
    throw new Error(text || `${res.status} ${res.statusText}`)
  }

  const disposition = res.headers.get('content-disposition') || ''
  const match = disposition.match(/filename="([^"]+)"/i)
  return {
    blob: await res.blob(),
    filename: match?.[1] || 'download',
  }
}
