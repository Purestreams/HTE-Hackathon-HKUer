import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { apiBaseUrl, apiFetch, type FileEntry, type FilesListResponse, type ModelsResponse } from '../lib/api'
import { useActiveSessionId } from '../hooks/useActiveSessionId'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MathJax, MathJaxContext } from 'better-react-mathjax'

export function ChatPage() {
  const [dir, setDir] = useState('')
  const [entries, setEntries] = useState<FileEntry[]>([])
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([])
  const [sources, setSources] = useState<Array<{ path: string; score?: number; snippet?: string }>>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [embedModels, setEmbedModels] = useState<string[]>([])
  const [embedModel, setEmbedModel] = useState('')
  const [topK, setTopK] = useState<number>(4)

  const bottomRef = useRef<HTMLDivElement | null>(null)

  const sessionId = useActiveSessionId()

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
    setError(null)
    try {
      const qs = new URLSearchParams()
      if (nextDir) qs.set('dir', nextDir)
      if (sessionId) qs.set('session_id', sessionId)
      const res = await apiFetch<FilesListResponse>(`/api/files/list?${qs.toString()}`)
      setDir(res.dir === '.' ? '' : res.dir)
      setEntries(res.entries)
    } catch (e: any) {
      setError(String(e?.message ?? e))
    }
  }

  useEffect(() => {
    refresh('').catch(() => {})
    ;(async () => {
      try {
        const res = await apiFetch<ModelsResponse>('/api/models')
        const merged = Array.from(new Set([...(res.models || []), ...(res.text_models || [])]))
        setModels(merged)
        setEmbedModels(res.embed_models || [])
        if (!model && res.main_model && merged.includes(res.main_model)) setModel(res.main_model)
        if (!embedModel && res.embed_models && res.embed_models.length) setEmbedModel(res.embed_models[0])
      } catch {
        setModels([])
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, busy])

  const selectedFiles = useMemo(() => Object.keys(selected).filter((k) => selected[k]), [selected])

  function toggle(path: string) {
    setSelected((prev) => ({ ...prev, [path]: !prev[path] }))
  }

  async function sendMessage() {
    setError(null)
    setSources([])

    const q = query.trim()
    if (!q) {
      setError('Enter a question')
      return
    }
    if (selectedFiles.length === 0) {
      setError('Select at least one file')
      return
    }

    setBusy(true)
    setMessages((prev) => [...prev, { role: 'user', content: q }, { role: 'assistant', content: '' }])
    setQuery('')

    try {
      const payload: any = { query: q, files: selectedFiles, top_k: topK, stream: true }
      if (model.trim()) payload.model = model.trim()
      if (embedModel.trim()) payload.embed_model = embedModel.trim()
      if (sessionId) payload.session_id = sessionId

      const sessionHeader: Record<string, string> = {}
      try {
        const v = localStorage.getItem('hte_active_session_v1')
        if (v && v.trim()) sessionHeader['X-HTE-Session'] = v.trim()
      } catch {
        // ignore
      }

      const url = `${apiBaseUrl}/api/chat/query`
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          ...sessionHeader,
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const txt = await res.text()
        throw new Error(txt || res.statusText)
      }
      if (!res.body) throw new Error('Missing response body')

      const reader = res.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buf = ''
      let done = false

      const appendDelta = (delta: string) => {
        if (!delta) return
        setMessages((prev) => {
          if (!prev.length) return prev
          const next = prev.slice()
          const last = next[next.length - 1]
          if (!last || last.role !== 'assistant') return prev
          next[next.length - 1] = { ...last, content: (last.content || '') + delta }
          return next
        })
      }

      while (!done) {
        const { value, done: rdDone } = await reader.read()
        if (rdDone) break
        buf += decoder.decode(value, { stream: true })
        let idx
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const raw = buf.slice(0, idx)
          buf = buf.slice(idx + 2)
          const lines = raw.split('\n')
          for (const line of lines) {
            if (!line.startsWith('data:')) continue
            const payloadStr = line.slice(5).trim()
            if (!payloadStr) continue
            let evt: any
            try {
              evt = JSON.parse(payloadStr)
            } catch {
              continue
            }
            if (evt.type === 'delta') {
              appendDelta(String(evt.delta || ''))
            } else if (evt.type === 'meta') {
              setSources(evt.sources || [])
            } else if (evt.type === 'error') {
              setError(String(evt.error || 'Streaming error'))
            } else if (evt.type === 'done') {
              done = true
            }
          }
        }
      }
    } catch (e: any) {
      setMessages((prev) => {
        if (!prev.length) return prev
        const next = prev.slice()
        const last = next[next.length - 1]
        if (last && last.role === 'assistant' && !last.content) {
          next[next.length - 1] = { role: 'assistant', content: 'Error: failed to get response.' }
          return next
        }
        return [...prev, { role: 'assistant', content: 'Error: failed to get response.' }]
      })
      setError(String(e?.message ?? e))
    } finally {
      setBusy(false)
    }
  }

  async function ask(e: FormEvent) {
    e.preventDefault()
    await sendMessage()
  }

  const mathjaxConfig = useMemo(
    () => ({
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
      },
      options: { renderActions: { addMenu: [] } },
    }),
    [],
  )

  return (
    <div className="max-w-7xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Chat</h1>
        <p className="mt-1 text-sm text-gray-600">Select files for RAG and ask questions.</p>
      </div>

      {error && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <aside className="rounded-lg border bg-white p-4 shadow-sm">
          <div className="mb-2 text-sm font-medium text-gray-800">Files</div>
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
          <div className="mt-3 max-h-[28rem] overflow-auto rounded-md border">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-gray-700">
                <tr>
                  <th className="px-3 py-2 font-medium">Pick</th>
                  <th className="px-3 py-2 font-medium">Name</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.path} className="border-t">
                    <td className="px-3 py-2">
                      {e.type === 'file' ? (
                        <input type="checkbox" checked={!!selected[e.path]} onChange={() => toggle(e.path)} />
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      {e.type === 'dir' ? (
                        <button className="hover:underline" type="button" onClick={() => refresh(e.path)}>
                          {e.name}
                        </button>
                      ) : (
                        <span>{e.name}</span>
                      )}
                      <div className="text-xs text-gray-500">{e.path}</div>
                    </td>
                  </tr>
                ))}
                {entries.length === 0 && (
                  <tr>
                    <td className="px-3 py-6 text-center text-gray-600" colSpan={2}>
                      Empty directory.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="mt-2 text-xs text-gray-500">Selected: {selectedFiles.length} file(s)</div>

          <div className="mt-4 space-y-3">
            <div>
              <label className="text-sm font-medium text-gray-700">Model</label>
              {models.length ? (
                <select className="mt-1 w-full rounded-md border px-3 py-2 text-sm" value={model} onChange={(e) => setModel(e.target.value)}>
                  <option value="">(default)</option>
                  {models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              ) : (
                <input className="mt-1 w-full rounded-md border px-3 py-2 text-sm" value={model} onChange={(e) => setModel(e.target.value)} placeholder="model" />
              )}
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700">Embedding model</label>
              {embedModels.length ? (
                <select className="mt-1 w-full rounded-md border px-3 py-2 text-sm" value={embedModel} onChange={(e) => setEmbedModel(e.target.value)}>
                  {embedModels.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              ) : (
                <input className="mt-1 w-full rounded-md border px-3 py-2 text-sm" value={embedModel} onChange={(e) => setEmbedModel(e.target.value)} placeholder="embedding model" />
              )}
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700">Top K</label>
              <input className="mt-1 w-full rounded-md border px-3 py-2 text-sm" type="number" value={topK} onChange={(e) => setTopK(Number(e.target.value))} min={1} max={20} />
            </div>
          </div>
        </aside>

        <section className="flex h-[70vh] flex-col rounded-lg border bg-white shadow-sm">
          <MathJaxContext version={3} config={mathjaxConfig}>
          <div className="flex-1 overflow-auto p-4">
            {messages.length === 0 && (
              <div className="text-sm text-gray-500">Start by selecting files and asking a question.</div>
            )}
            <div className="space-y-4">
              {messages.map((m, idx) => (
                <div key={idx} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                  <div
                    className={
                      m.role === 'user'
                        ? 'max-w-[75%] rounded-2xl bg-gray-900 px-4 py-2 text-sm text-white'
                        : 'max-w-[75%] rounded-2xl bg-gray-100 px-4 py-2 text-sm text-gray-900'
                    }
                  >
                    {m.role === 'assistant' ? (
                      <MathJax dynamic hideUntilTypeset="first">
                        <div className="chat-markdown">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              a: (props: any) => (
                                <a className="text-blue-700 underline" href={props.href} target="_blank" rel="noreferrer">
                                  {props.children}
                                </a>
                              ),
                              code: (props: any) => {
                                const inline = !!props.inline
                                const children = props.children
                                return inline ? (
                                  <code className="rounded bg-black/5 px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
                                ) : (
                                  <pre className="overflow-auto rounded-md bg-black px-3 py-2 text-xs text-white">
                                    <code className="font-mono">{children}</code>
                                  </pre>
                                )
                              },
                            }}
                          >
                            {m.content}
                          </ReactMarkdown>
                        </div>
                      </MathJax>
                    ) : (
                      <div className="whitespace-pre-wrap">{m.content}</div>
                    )}
                  </div>
                </div>
              ))}
              {busy && (
                <div className="flex justify-start">
                  <div className="max-w-[75%] rounded-2xl bg-gray-100 px-4 py-2 text-sm text-gray-700">
                    Thinking…
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          </div>
          </MathJaxContext>

          {sources.length > 0 && (
            <div className="border-t bg-gray-50 px-4 py-2 text-xs text-gray-600">
              <div className="font-medium">Sources</div>
              <ul className="mt-1 list-disc pl-4">
                {sources.map((s, idx) => (
                  <li key={`${s.path}-${idx}`} className="break-all">
                    {s.path} {typeof s.score === 'number' ? `(score ${s.score.toFixed(3)})` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <form onSubmit={ask} className="border-t p-3">
            <div className="flex items-end gap-2">
              <textarea
                className="min-h-[44px] flex-1 resize-none rounded-md border px-3 py-2 text-sm"
                placeholder="Ask a question..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    if (!busy) sendMessage().catch(() => {})
                  }
                }}
              />
              <button
                className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-60"
                disabled={busy || !query.trim()}
                type="submit"
              >
                {busy ? 'Asking…' : 'Send'}
              </button>
            </div>
            <div className="mt-1 text-xs text-gray-500">Enter to send · Shift+Enter for newline</div>
          </form>
        </section>
      </div>
    </div>
  )
}
