/** Base URL for FastAPI (no trailing slash). */
export const API_BASE =
  import.meta.env.VITE_API_URL?.replace(/\/$/, '') || 'http://127.0.0.1:8000'

function wrapNetworkError(err: unknown): Error {
  if (err instanceof TypeError) {
    return new Error(
      `Cannot reach the API at ${API_BASE}.\n\n` +
        `1) Backend (repo root, venv activated):\n` +
        `   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000\n\n` +
        `2) If the API is not on ${API_BASE}, create frontend/.env.local:\n` +
        `   VITE_API_URL=http://127.0.0.1:8000\n` +
        `   (no trailing slash; match your Uvicorn host/port)\n\n` +
        `3) Restart the frontend: npm run dev\n\n` +
        `4) Open http://127.0.0.1:8000/docs — if that fails, the API is not running.`
    )
  }
  return err instanceof Error ? err : new Error(String(err))
}

export async function apiJson<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
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
    throw new Error(text || `${res.status} ${res.statusText}`)
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
