import { useMemo } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { apiBaseUrl } from '../lib/api'
import { useActiveSessionId } from '../hooks/useActiveSessionId'

export function ViewPdfPage() {
  const location = useLocation()
  const qs = useMemo(() => new URLSearchParams(location.search), [location.search])
  const path = qs.get('path') || ''
  const sessionId = useActiveSessionId()

  const src = useMemo(() => {
    if (!path) return ''
    return `${apiBaseUrl}/api/files/raw?path=${encodeURIComponent(path)}&session_id=${encodeURIComponent(sessionId)}`
  }, [path, sessionId])

  if (!path) {
    return (
      <div className="max-w-4xl space-y-3">
        <h1 className="text-2xl font-semibold text-gray-900">PDF</h1>
        <div className="text-sm text-gray-700">Missing query param: <span className="font-mono">path</span></div>
        <Link className="text-blue-700 hover:underline" to="/library">
          Go to Library
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">PDF</h1>
          <div className="mt-1 text-xs text-gray-500">{path}</div>
        </div>
        <div className="flex items-center gap-2">
          <a className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50" href={src} target="_blank" rel="noreferrer">
            Open in new tab
          </a>
          <Link className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50" to="/library">
            Library
          </Link>
        </div>
      </div>

      <div className="h-[75vh] overflow-hidden rounded-lg border bg-white shadow-sm">
        <iframe title="pdf" src={src} className="h-full w-full" />
      </div>
    </div>
  )
}
