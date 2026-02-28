import { useEffect, useState } from 'react'
import { apiFetch, type Session, type SessionActivateResponse, type SessionCreateResponse, type SessionsListResponse } from '../lib/api'
import { setActiveSessionId } from '../lib/session'
import { useActiveSessionId } from '../hooks/useActiveSessionId'

export function SessionSelector() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [serverActive, setServerActive] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')

  const activeId = useActiveSessionId()
  const selected = activeId || serverActive || 'repo'

  async function refresh() {
    setLoading(true)
    setError(null)
    try {
      const res = await apiFetch<SessionsListResponse>('/api/sessions')
      setSessions(res.sessions)
      setServerActive(res.active)
      // If local storage isn't set yet, bootstrap from server.
      if ((activeId === 'repo' || !activeId) && res.active) setActiveSessionId(res.active)
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function activate(id: string) {
    setError(null)
    setActiveSessionId(id)
    try {
      await apiFetch<SessionActivateResponse>(`/api/sessions/${id}/activate`, { method: 'POST' })
      setServerActive(id)
    } catch (e: any) {
      setError(String(e?.message ?? e))
    }
  }

  async function create() {
    setCreating(true)
    setError(null)
    try {
      const res = await apiFetch<SessionCreateResponse>('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName || 'session' }),
      })
      await refresh()
      await activate(res.session.id)
      setNewName('')
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setCreating(false)
    }
  }

  async function removeSession(id: string) {
    if (id === 'repo') {
      setError('Default session cannot be deleted')
      return
    }
    const ok = window.confirm(`Delete session ${id}? This will remove all its files.`)
    if (!ok) return

    setError(null)
    try {
      await apiFetch<{ ok: true }>(`/api/sessions/${id}`, { method: 'DELETE' })
      await refresh()
      if (selected === id) {
        await activate('repo')
      }
    } catch (e: any) {
      setError(String(e?.message ?? e))
    }
  }

  return (
    <div className="flex items-center gap-2">
      <div className="text-xs text-gray-500">Session</div>
      <select
        className="max-w-56 rounded-md border px-2 py-1 text-sm"
        value={selected}
        onChange={(e) => activate(e.target.value)}
        disabled={loading}
        title={loading ? 'Loading…' : 'Select session'}
      >
        {sessions.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name ? `${s.name} (${s.id})` : s.id}
          </option>
        ))}
        {sessions.length === 0 && <option value="repo">repo</option>}
      </select>

      <button
        className="rounded-md border px-2 py-1 text-sm hover:bg-gray-50 disabled:opacity-60"
        type="button"
        onClick={() => removeSession(selected)}
        disabled={loading || selected === 'repo'}
        title={selected === 'repo' ? 'Default session cannot be deleted' : 'Delete session'}
      >
        Delete
      </button>

      <details className="relative">
        <summary className="cursor-pointer select-none rounded-md border px-2 py-1 text-sm hover:bg-gray-50">New</summary>
        <div className="absolute right-0 z-10 mt-2 w-72 rounded-lg border bg-white p-3 shadow-lg">
          <div className="text-sm font-medium text-gray-800">Create session</div>
          <input
            className="mt-2 w-full rounded-md border px-3 py-2 text-sm"
            placeholder="e.g. COMP2119 Midterm"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <div className="mt-2 flex items-center justify-between gap-2">
            <button
              className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-black disabled:opacity-60"
              disabled={creating}
              type="button"
              onClick={create}
            >
              {creating ? 'Creating…' : 'Create'}
            </button>
            <button className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50" type="button" onClick={refresh}>
              Refresh
            </button>
          </div>
          {error && <div className="mt-2 text-xs text-red-700">{error}</div>}
          <div className="mt-2 text-xs text-gray-500">All API calls will use this session.</div>
        </div>
      </details>
    </div>
  )
}
