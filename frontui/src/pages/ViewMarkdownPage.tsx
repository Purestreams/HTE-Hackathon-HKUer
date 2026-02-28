import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MathJax, MathJaxContext } from 'better-react-mathjax'

import { apiFetch, apiBaseUrl, type FileStatResponse, type FileTextResponse } from '../lib/api'
import { useActiveSessionId } from '../hooks/useActiveSessionId'

export function ViewMarkdownPage() {
  const location = useLocation()
  const qs = useMemo(() => new URLSearchParams(location.search), [location.search])
  const path = qs.get('path') || ''

  const sessionId = useActiveSessionId()

  const [text, setText] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [pdfExists, setPdfExists] = useState<boolean | null>(null)
  const pdfPath = useMemo(() => {
    if (!path) return ''
    if (path.toLowerCase().endsWith('.md')) return path.slice(0, -3) + '.pdf'
    if (path.toLowerCase().endsWith('.markdown')) return path.replace(/\.markdown$/i, '.pdf')
    return ''
  }, [path])

  const rawUrl = useMemo(() => {
    if (!path) return ''
    return `${apiBaseUrl}/api/files/raw?path=${encodeURIComponent(path)}&session_id=${encodeURIComponent(sessionId)}`
  }, [path, sessionId])

  useEffect(() => {
    if (!path) return
    setBusy(true)
    setError(null)
    ;(async () => {
      try {
        const res = await apiFetch<FileTextResponse>(`/api/files/text?path=${encodeURIComponent(path)}`)
        setText(res.text)

        if (pdfPath) {
          const st = await apiFetch<FileStatResponse>(`/api/files/stat?path=${encodeURIComponent(pdfPath)}`)
          setPdfExists(Boolean(st.exists))
        } else {
          setPdfExists(false)
        }
      } catch (e: any) {
        setError(String(e?.message ?? e))
      } finally {
        setBusy(false)
      }
    })()
  }, [path, pdfPath, sessionId])

  if (!path) {
    return (
      <div className="max-w-4xl space-y-3">
        <h1 className="text-2xl font-semibold text-gray-900">Markdown</h1>
        <div className="text-sm text-gray-700">Missing query param: <span className="font-mono">path</span></div>
        <Link className="text-blue-700 hover:underline" to="/library">
          Go to Library
        </Link>
      </div>
    )
  }

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Markdown</h1>
          <div className="mt-1 text-xs text-gray-500">{path}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <a className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50" href={rawUrl} target="_blank" rel="noreferrer">
            Raw
          </a>
          {pdfPath && pdfExists ? (
            <Link className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50" to={`/view/pdf?path=${encodeURIComponent(pdfPath)}`}>
              Open PDF
            </Link>
          ) : pdfPath && pdfExists === false ? (
            <span className="text-xs text-gray-500">No sibling PDF</span>
          ) : null}
          <Link className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50" to="/library">
            Library
          </Link>
        </div>
      </div>

      {error && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
      {busy ? (
        <div className="rounded-md border bg-white p-4 text-sm text-gray-700">Loading…</div>
      ) : (
        <MathJaxContext
          version={3}
          config={{
            loader: { load: ['input/tex', 'output/chtml'] },
            tex: {
              inlineMath: [
                ['$', '$'],
                ['\\(', '\\)'],
              ],
              displayMath: [
                ['$$', '$$'],
                ['\\[', '\\]'],
              ],
              processEscapes: true,
              processEnvironments: true,
            },
            options: {
              skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
            },
          }}
        >
          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <MathJax dynamic>
              <div>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
              </div>
            </MathJax>
          </div>
        </MathJaxContext>
      )}
    </div>
  )
}
