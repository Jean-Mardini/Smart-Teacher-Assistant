import { useEffect, useState } from 'react'
import { API_BASE, apiJson } from '../api/client'

type EvaluationConfig = {
  has_api_key: boolean
  api_key_preview: string
  model: string
}

export function AiSettingsPanel() {
  const [apiKey, setApiKey] = useState('')
  const [savedConfig, setSavedConfig] = useState<EvaluationConfig | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    async function checkApiHealth() {
      const controller = new AbortController()
      const timer = window.setTimeout(() => controller.abort(), 2500)
      try {
        const response = await fetch(`${API_BASE}/health`, { signal: controller.signal })
        if (active) {
          setApiOnline(response.ok)
        }
      } catch {
        if (active) {
          setApiOnline(false)
        }
      } finally {
        window.clearTimeout(timer)
      }
    }

    async function loadConfig() {
      setLoading(true)
      try {
        const [res] = await Promise.all([
          apiJson<EvaluationConfig>('/evaluation/config'),
          checkApiHealth(),
        ])
        if (active) {
          setSavedConfig(res)
        }
      } catch (e) {
        if (active) {
          setError(e instanceof Error ? e.message : 'Failed to load AI settings.')
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    void loadConfig()

    return () => {
      active = false
    }
  }, [])

  async function saveApiKey() {
    if (!apiKey.trim()) return
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const res = await apiJson<EvaluationConfig>('/evaluation/config', {
        method: 'PUT',
        body: JSON.stringify({ groq_api_key: apiKey }),
      })
      setSavedConfig(res)
      setApiOnline(true)
      setApiKey('')
      setMessage('Saved for all AI tools. API online.')
    } catch (e) {
      setApiOnline(false)
      setError(e instanceof Error ? e.message : 'Failed to save AI key.')
    } finally {
      setSaving(false)
    }
  }

  async function clearApiKey() {
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const res = await apiJson<EvaluationConfig>('/evaluation/config', {
        method: 'PUT',
        body: JSON.stringify({ groq_api_key: '' }),
      })
      setSavedConfig(res)
      setApiOnline(true)
      setApiKey('')
      setMessage('Saved key cleared.')
    } catch (e) {
      setApiOnline(false)
      setError(e instanceof Error ? e.message : 'Failed to clear AI key.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      style={{
        marginTop: 'auto',
        padding: '0.9rem',
        borderRadius: '16px',
        border: '1px solid rgba(255,255,255,0.08)',
        background: 'rgba(255,255,255,0.05)',
      }}
    >
      <div style={{ fontSize: '0.8rem', fontWeight: 700, marginBottom: '0.35rem' }}>AI Key</div>
      <p style={{ margin: '0 0 0.65rem', fontSize: '0.74rem', lineHeight: 1.45, opacity: 0.7 }}>
        Shared by grading, dialogue, summaries, quizzes, and slides.
      </p>
      <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginBottom: '0.65rem' }}>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            padding: '0.28rem 0.55rem',
            borderRadius: '999px',
            fontSize: '0.72rem',
            fontWeight: 700,
            background:
              apiOnline === true
                ? 'rgba(80,160,120,0.18)'
                : apiOnline === false
                  ? 'rgba(200,90,90,0.18)'
                  : 'rgba(255,255,255,0.08)',
            color: '#fff',
            border:
              apiOnline === true
                ? '1px solid rgba(80,160,120,0.4)'
                : apiOnline === false
                  ? '1px solid rgba(200,90,90,0.4)'
                  : '1px solid rgba(255,255,255,0.12)',
          }}
        >
          {apiOnline === true ? 'API online' : apiOnline === false ? 'API offline' : 'Checking API'}
        </span>
        {savedConfig?.has_api_key && (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              padding: '0.28rem 0.55rem',
              borderRadius: '999px',
              fontSize: '0.72rem',
              fontWeight: 700,
              background: 'rgba(255,255,255,0.08)',
              color: '#fff',
              border: '1px solid rgba(255,255,255,0.12)',
            }}
          >
            Key saved
          </span>
        )}
      </div>
      <input
        type="password"
        value={apiKey}
        placeholder={savedConfig?.has_api_key ? 'Saved key exists. Paste a new one to replace it.' : 'gsk_...'}
        onChange={(event) => setApiKey(event.target.value)}
        style={{
          width: '100%',
          padding: '0.65rem 0.8rem',
          borderRadius: '12px',
          border: '1px solid rgba(255,255,255,0.1)',
          background: 'rgba(255,255,255,0.94)',
          color: '#152433',
          fontSize: '0.88rem',
          marginBottom: '0.65rem',
        }}
      />
      <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={() => void saveApiKey()}
          disabled={saving || !apiKey.trim()}
          style={{
            padding: '0.55rem 0.75rem',
            borderRadius: '12px',
            border: 'none',
            background: 'rgba(193,127,89,0.95)',
            color: '#fff',
            fontWeight: 700,
            cursor: saving || !apiKey.trim() ? 'default' : 'pointer',
          }}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          onClick={() => void clearApiKey()}
          disabled={saving || !savedConfig?.has_api_key}
          style={{
            padding: '0.55rem 0.75rem',
            borderRadius: '12px',
            border: '1px solid rgba(255,255,255,0.12)',
            background: 'transparent',
            color: '#fff',
            fontWeight: 700,
            cursor: saving || !savedConfig?.has_api_key ? 'default' : 'pointer',
          }}
        >
          Clear
        </button>
      </div>
      {loading && <p style={{ margin: '0.6rem 0 0', fontSize: '0.72rem', opacity: 0.7 }}>Loading saved key…</p>}
      {!loading && savedConfig?.has_api_key && (
        <p style={{ margin: '0.6rem 0 0', fontSize: '0.72rem', opacity: 0.8 }}>
          Saved: <code>{savedConfig.api_key_preview}</code>
        </p>
      )}
      {message && <p style={{ margin: '0.6rem 0 0', fontSize: '0.72rem', color: '#c7f0d8' }}>{message}</p>}
      {error && <p style={{ margin: '0.6rem 0 0', fontSize: '0.72rem', color: '#ffd1d1' }}>{error}</p>}
    </div>
  )
}
