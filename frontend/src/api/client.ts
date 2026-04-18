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
