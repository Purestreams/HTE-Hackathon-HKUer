import { useEffect, useState } from 'react'
import { apiFetch, type SnapshotsListResponse, type SnapshotCreateResponse } from '../lib/api'

export function SnapshotsPage() {
  const [items, setItems] = useState<SnapshotsListResponse['snapshots']>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    setError(null)
    const res = await apiFetch<SnapshotsListResponse>('/api/snapshots')
    setItems(res.snapshots)
    setActiveId(res.active ?? null)
  }

  useEffect(() => {
    refresh().catch((e) => setError(String(e?.message ?? e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function createSnapshot() {
    setBusy(true)
    setError(null)
    try {
      await apiFetch<SnapshotCreateResponse>('/api/snapshots', { method: 'POST' })
      await refresh()
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setBusy(false)
    }
  }

  async function activate(id: string) {
    setBusy(true)
    setError(null)
    try {
      await apiFetch(`/api/snapshots/${id}/activate`, { method: 'POST' })
      await refresh()
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setBusy(false)
    }
  }

  async function fork(id: string) {
    setBusy(true)
    setError(null)
    try {
      await apiFetch(`/api/snapshots/${id}/fork`, { method: 'POST' })
      await refresh()
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Snapshots</h1>
          <p className="mt-1 text-sm text-gray-600">File-based source snapshots (manifest + activate + fork).</p>
        </div>
        <button
          className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-60"
          onClick={createSnapshot}
          disabled={busy}
        >
          {busy ? 'Working…' : 'Create snapshot'}
        </button>
      </div>

      {error && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      <div className="overflow-hidden rounded-lg border bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-gray-700">
            <tr>
              <th className="px-4 py-3 font-medium">ID</th>
              <th className="px-4 py-3 font-medium">Created</th>
              <th className="px-4 py-3 font-medium">Active</th>
              <th className="px-4 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.id} className="border-t">
                <td className="px-4 py-3 font-mono text-xs text-gray-800">{s.id}</td>
                <td className="px-4 py-3 text-gray-700">{formatSnapshotCreatedAt(s.id) ?? '-'}</td>
                <td className="px-4 py-3">
                  {activeId === s.id ? (
                    <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">Active</span>
                  ) : (
                    <span className="text-xs text-gray-500">—</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      className="rounded-md border px-3 py-1 text-xs hover:bg-gray-50 disabled:opacity-60"
                      disabled={busy || activeId === s.id}
                      onClick={() => activate(s.id)}
                      type="button"
                    >
                      Activate
                    </button>
                    <button
                      className="rounded-md border px-3 py-1 text-xs hover:bg-gray-50 disabled:opacity-60"
                      disabled={busy}
                      onClick={() => fork(s.id)}
                      type="button"
                    >
                      Fork
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td className="px-4 py-8 text-center text-gray-600" colSpan={4}>
                  No snapshots yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function formatSnapshotCreatedAt(id: string): string | null {
  // Expected prefix: YYYYMMDDTHHMMSSZ_...
  const m = id.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z_/) 
  if (!m) return null
  const [_, yy, mo, dd, hh, mm, ss] = m
  const d = new Date(`${yy}-${mo}-${dd}T${hh}:${mm}:${ss}Z`)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleString()
}
