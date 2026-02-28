import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch, apiBaseUrl, type FileEntry, type FilesListResponse, type MdToPdfResponse } from '../lib/api'
import { useActiveSessionId } from '../hooks/useActiveSessionId'

export function LibraryPage() {
  const [dir, setDir] = useState<string>('')
  const [entries, setEntries] = useState<FileEntry[]>([])
  const [busy, setBusy] = useState(false)
  const [deletingPath, setDeletingPath] = useState<string | null>(null)
  const [generating, setGenerating] = useState<Record<string, number>>({})
  const [error, setError] = useState<string | null>(null)

  const sessionId = useActiveSessionId()
  const navigate = useNavigate()

  const crumbs = useMemo(() => {
    const parts = (dir || '').split('/').filter(Boolean)
    const out: Array<{ label: string; dir: string }> = [{ label: 'sources', dir: '' }]
    let cur = ''
    for (const p of parts) {
      cur = cur ? `${cur}/${p}` : p
      out.push({ label: p, dir: cur })
    }
    return out
  }, [dir])

  async function refresh(nextDir: string) {
    setBusy(true)
    setError(null)
    try {
      const qs = new URLSearchParams()
      if (nextDir) qs.set('dir', nextDir)
      // session_id is optional for list, but useful for parity.
      if (sessionId) qs.set('session_id', sessionId)
      const res = await apiFetch<FilesListResponse>(`/api/files/list?${qs.toString()}`)
      setDir(res.dir === '.' ? '' : res.dir)
      setEntries(res.entries)
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(entry: FileEntry) {
    if (entry.type !== 'file') return
    const ok = window.confirm(`Delete ${entry.name}? This cannot be undone.`)
    if (!ok) return

    setDeletingPath(entry.path)
    setError(null)
    try {
      const qs = new URLSearchParams()
      qs.set('path', entry.path)
      if (sessionId) qs.set('session_id', sessionId)
      await apiFetch<{ ok: true }>(`/api/files?${qs.toString()}`, { method: 'DELETE' })
      await refresh(dir)
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setDeletingPath(null)
    }
  }

  useEffect(() => {
    refresh('').catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  function fileLink(e: FileEntry): { label: string; to?: string; href?: string } {
    const ext = (e.ext || '').toLowerCase()
    if (ext === 'md' || ext === 'markdown') {
      return { label: 'View', to: `/view/md?path=${encodeURIComponent(e.path)}` }
    }
    if (ext === 'pdf') {
      return { label: 'Open', to: `/view/pdf?path=${encodeURIComponent(e.path)}` }
    }
    const raw = `${apiBaseUrl}/api/files/raw?path=${encodeURIComponent(e.path)}&download=1&session_id=${encodeURIComponent(sessionId)}`
    return { label: 'Download', href: raw }
  }

  async function handleViewPdfFromMarkdown(e: FileEntry) {
    if (e.type !== 'file') return
    const ext = (e.ext || '').toLowerCase()
    if (ext !== 'md' && ext !== 'markdown') return

    setError(null)

    // Indeterminate-ish progress: climb to 92% while waiting.
    let t: any = null
    setGenerating((prev) => ({ ...prev, [e.path]: 10 }))
    t = window.setInterval(() => {
      setGenerating((prev) => {
        const cur = prev[e.path] ?? 10
        const next = Math.min(92, cur + 8)
        return { ...prev, [e.path]: next }
      })
    }, 180)

    try {
      const res = await apiFetch<MdToPdfResponse>('/api/convert/md_to_pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: e.path }),
      })
      setGenerating((prev) => ({ ...prev, [e.path]: 100 }))
      window.setTimeout(() => {
        setGenerating((prev) => {
          const { [e.path]: _, ...rest } = prev
          return rest
        })
      }, 450)

      navigate(`/view/pdf?path=${encodeURIComponent(res.pdf_path)}`)
    } catch (err: any) {
      setError(String(err?.message ?? err))
      setGenerating((prev) => {
        const { [e.path]: _, ...rest } = prev
        return rest
      })
    } finally {
      if (t) window.clearInterval(t)
    }
  }

  return (
    <div className="max-w-6xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Library</h1>
          <p className="mt-1 text-sm text-gray-600">Browse the current session’s sources (rendered Markdown + original PDFs).</p>
        </div>
        <button
          className="rounded-md border px-3 py-2 text-sm hover:bg-gray-50 disabled:opacity-60"
          type="button"
          onClick={() => refresh(dir)}
          disabled={busy}
        >
          {busy ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {error && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      <div className="rounded-lg border bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-2 text-sm text-gray-700">
          {crumbs.map((c, idx) => (
            <div key={c.dir} className="flex items-center gap-2">
              {idx > 0 && <span className="text-gray-400">/</span>}
              <button className="hover:underline" type="button" onClick={() => refresh(c.dir)}>
                {c.label}
              </button>
            </div>
          ))}
        </div>

        <div className="mt-4 overflow-hidden rounded-md border">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-50 text-gray-700">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Size</th>
                <th className="px-4 py-3 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const action = fileLink(e)
                const ext = (e.ext || '').toLowerCase()
                const genPct = generating[e.path]
                return (
                  <tr key={e.path} className="border-t">
                    <td className="px-4 py-3">
                      {e.type === 'dir' ? (
                        <button className="font-medium text-gray-900 hover:underline" type="button" onClick={() => refresh(e.path)}>
                          {e.name}
                        </button>
                      ) : (
                        <span className="text-gray-900">{e.name}</span>
                      )}
                      <div className="text-xs text-gray-500">{e.path}</div>
                    </td>
                    <td className="px-4 py-3 text-gray-700">{e.type}</td>
                    <td className="px-4 py-3 text-gray-700">{e.bytes ? formatBytes(e.bytes) : e.type === 'dir' ? '—' : '—'}</td>
                    <td className="px-4 py-3">
                      {e.type === 'dir' ? null : (
                        <div className="flex items-center gap-3">
                          {action.to ? (
                            <Link className="text-blue-700 hover:underline" to={action.to}>
                              {action.label}
                            </Link>
                          ) : (
                            <a className="text-blue-700 hover:underline" href={action.href}>
                              {action.label}
                            </a>
                          )}

                          {ext === 'md' || ext === 'markdown' ? (
                            <button
                              className="text-blue-700 hover:underline disabled:opacity-60"
                              type="button"
                              onClick={() => handleViewPdfFromMarkdown(e)}
                              disabled={genPct != null}
                            >
                              {genPct != null ? 'Generating…' : 'View PDF'}
                            </button>
                          ) : null}

                          <button
                            className="text-red-700 hover:underline disabled:opacity-60"
                            type="button"
                            onClick={() => handleDelete(e)}
                            disabled={deletingPath === e.path}
                          >
                            {deletingPath === e.path ? 'Deleting…' : 'Delete'}
                          </button>
                        </div>
                      )}

                      {genPct != null ? (
                        <div className="mt-2 h-1.5 w-40 overflow-hidden rounded bg-gray-200">
                          <div
                            className="h-full bg-blue-600 transition-all"
                            style={{ width: `${Math.max(6, Math.min(100, genPct))}%` }}
                          />
                        </div>
                      ) : null}
                    </td>
                  </tr>
                )
              })}
              {entries.length === 0 && (
                <tr>
                  <td className="px-4 py-8 text-center text-gray-600" colSpan={4}>
                    Empty directory.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function formatBytes(n: number): string {
  if (!Number.isFinite(n)) return String(n)
  if (n < 1024) return `${n} B`
  const kb = n / 1024
  if (kb < 1024) return `${kb.toFixed(1)} KB`
  const mb = kb / 1024
  if (mb < 1024) return `${mb.toFixed(1)} MB`
  const gb = mb / 1024
  return `${gb.toFixed(2)} GB`
}
