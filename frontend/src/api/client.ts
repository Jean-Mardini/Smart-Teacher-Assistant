/** Base URL for FastAPI (no trailing slash). */
export const API_BASE =
  import.meta.env.VITE_API_URL?.replace(/\/$/, '') || 'http://127.0.0.1:8000'

export async function apiJson<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
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
  const res = await fetch(`${API_BASE}${path}`, { method: 'POST', body: fd })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `${res.status}`)
  }
  return res.json()
}
