import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { apiBaseUrl, apiFetch, type FileEntry, type FilesListResponse, type JobCreateResponse, type JobStatusResponse } from '../lib/api'
import { JobStatusCard } from '../components/JobStatusCard'
import { saveJob } from '../lib/jobHistory'
import { useActiveSessionId } from '../hooks/useActiveSessionId'

export function ValidatePage() {
  const [runCode, setRunCode] = useState(true)
  const [mock, setMock] = useState(true)
  const [models, setModels] = useState<string[]>([])
  const [mainModel, setMainModel] = useState('')
  const [subModel, setSubModel] = useState('')
  const [aiReview, setAiReview] = useState(true)

  const [dir, setDir] = useState('')
  const [entries, setEntries] = useState<FileEntry[]>([])
  const [selected, setSelected] = useState<Record<string, boolean>>({})

  const sessionId = useActiveSessionId()

  const [jobId, setJobId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [lastResult, setLastResult] = useState<JobStatusResponse | null>(null)

  const [logMessages, setLogMessages] = useState<Array<{ role: 'assistant' | 'system'; content: string }>>([])
  const [logBusy, setLogBusy] = useState(false)
  const [streamProgress, setStreamProgress] = useState<{ stage?: string; message?: string; elapsed_sec?: number } | null>(null)

  const crumbs = (dir || '')
    .split('/')
    .filter(Boolean)
    .reduce<Array<{ label: string; dir: string }>>(
      (acc, part) => {
        const prev = acc.length ? acc[acc.length - 1]!.dir : ''
        const next = prev ? `${prev}/${part}` : part
        acc.push({ label: part, dir: next })
        return acc
      },
      [{ label: 'sources', dir: '' }],
    )

  const selectedFiles = Object.keys(selected).filter((k) => selected[k])

  function toggle(path: string) {
    setSelected((prev) => ({ ...prev, [path]: !prev[path] }))
  }

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
        const res = await apiFetch<{ ok: true; models: string[]; text_models: string[]; main_model?: string }>('/api/models')
        const merged = Array.from(new Set([...(res.models || []), ...(res.text_models || [])]))
        setModels(merged)
        if (!mainModel && res.main_model && merged.includes(res.main_model)) {
          setMainModel(res.main_model)
        }
        if (!subModel && merged.length) {
          const candidate = merged.find((m) => m !== (res.main_model || mainModel)) || ''
          setSubModel(candidate)
        }
      } catch {
        setModels([])
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  useEffect(() => {
    if (!jobId) return
    let cancelled = false
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
    setLogMessages([])
    setLogBusy(true)
    setStreamProgress(null)

    ;(async () => {
      try {
        const url = `${apiBaseUrl}/api/jobs/${encodeURIComponent(jobId)}/stream`
        const res = await fetch(url, { headers: { Accept: 'text/event-stream' } })
        if (!res.ok) {
          const txt = await res.text()
          throw new Error(txt || res.statusText)
        }
        if (!res.body) throw new Error('Missing response body')

        reader = res.body.getReader()
        const decoder = new TextDecoder('utf-8')
        let buf = ''
        let done = false

        const push = (role: 'assistant' | 'system', content: string) => {
          if (!content) return
          setLogMessages((prev) => [...prev, { role, content }])
        }

        while (!done && !cancelled) {
          const { value, done: rdDone } = await reader.read()
          if (rdDone) break
          buf += decoder.decode(value, { stream: true })

          let idx
          while ((idx = buf.indexOf('\n\n')) >= 0) {
            const raw = buf.slice(0, idx)
            buf = buf.slice(idx + 2)
            for (const line of raw.split('\n')) {
              if (!line.startsWith('data:')) continue
              const payloadStr = line.slice(5).trim()
              if (!payloadStr) continue
              let evt: any
              try {
                evt = JSON.parse(payloadStr)
              } catch {
                continue
              }
              if (evt.type === 'meta') {
                push('system', `Streaming log connected (job ${evt.job_id})`)
              } else if (evt.type === 'log') {
                push('assistant', String(evt.message || ''))
              } else if (evt.type === 'progress') {
                setStreamProgress(evt.progress || null)
              } else if (evt.type === 'error') {
                push('system', `Error: ${String(evt.error || 'stream error')}`)
              } else if (evt.type === 'done') {
                if (evt.status) push('system', `Stream done (${String(evt.status)})`)
                done = true
              }
            }
          }
        }
      } catch (e: any) {
        if (!cancelled) setError(String(e?.message ?? e))
      } finally {
        if (!cancelled) setLogBusy(false)
      }
    })()

    return () => {
      cancelled = true
      try {
        reader?.cancel()
      } catch {
        // ignore
      }
      setLogBusy(false)
    }
  }, [jobId])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setJobId(null)

    try {
      if (selectedFiles.length === 0) {
        throw new Error('Select at least one .md file')
      }
      const payload: any = { files: selectedFiles, run_code: runCode, mock }
      if (aiReview) payload.ai_review = true
      if (mainModel.trim()) payload.main_model = mainModel.trim()
      if (subModel.trim()) payload.sub_model = subModel.trim()
      const res = await apiFetch<JobCreateResponse>('/api/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      setJobId(res.job_id)
      saveJob({ id: res.job_id, type: 'validate', createdAt: new Date().toISOString() })
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setBusy(false)
    }
  }

  async function fetchOnce() {
    if (!jobId) return
    try {
      const res = await apiFetch<JobStatusResponse>(`/api/jobs/${jobId}`)
      setLastResult(res)
    } catch {
      // If the backend restarted and forgot this in-memory job, just clear it.
      setJobId(null)
      setLastResult(null)
    }
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Validate</h1>
        <p className="mt-1 text-sm text-gray-600">Runs code-block sandbox checks, mockpaper sanity checks, and optional two-model consensus review.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <form onSubmit={submit} className="rounded-lg border bg-white p-4 shadow-sm">
          <div className="space-y-4">
            <div>
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium text-gray-700">Files</div>
                <div className="text-xs text-gray-500">Selected: {selectedFiles.length}</div>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-gray-700">
                {crumbs.map((c, idx) => (
                  <div key={c.dir} className="flex items-center gap-2">
                    {idx > 0 && <span className="text-gray-400">/</span>}
                    <button className="hover:underline" type="button" onClick={() => refresh(c.dir)}>
                      {c.label}
                    </button>
                  </div>
                ))}
              </div>
              <div className="mt-2 max-h-80 overflow-auto rounded-md border">
                <table className="w-full text-left text-sm">
                  <thead className="bg-gray-50 text-gray-700">
                    <tr>
                      <th className="px-3 py-2 font-medium">Pick</th>
                      <th className="px-3 py-2 font-medium">Name</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((e) => {
                      const isMd = e.type === 'file' && (e.ext === 'md' || e.name.toLowerCase().endsWith('.md'))
                      return (
                        <tr key={e.path} className="border-t">
                          <td className="px-3 py-2">
                            {e.type === 'file' ? (
                              <input type="checkbox" disabled={!isMd} checked={!!selected[e.path]} onChange={() => toggle(e.path)} />
                            ) : null}
                          </td>
                          <td className="px-3 py-2">
                            {e.type === 'dir' ? (
                              <button className="hover:underline" type="button" onClick={() => refresh(e.path)}>
                                {e.name}
                              </button>
                            ) : (
                              <span className={!isMd ? 'text-gray-400' : ''}>{e.name}</span>
                            )}
                            <div className="text-xs text-gray-500">{e.path}</div>
                          </td>
                        </tr>
                      )
                    })}
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
              <div className="mt-2 text-xs text-gray-500">Only <span className="font-mono">.md</span> files are selectable.</div>
            </div>

            <div>
              <Field label="Main model (judge/editor)">
                {models.length ? (
                  <select className="w-full rounded-md border px-3 py-2 text-sm" value={mainModel} onChange={(e) => setMainModel(e.target.value)}>
                    <option value="">(choose)</option>
                    {models.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="w-full rounded-md border px-3 py-2 text-sm"
                    value={mainModel}
                    onChange={(e) => setMainModel(e.target.value)}
                    placeholder="e.g. doubao-seed-2-0-pro-260215"
                  />
                )}
              </Field>

              <Field label="Sub model (challenger)">
                {models.length ? (
                  <select className="w-full rounded-md border px-3 py-2 text-sm" value={subModel} onChange={(e) => setSubModel(e.target.value)}>
                    <option value="">(optional)</option>
                    {models.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="w-full rounded-md border px-3 py-2 text-sm"
                    value={subModel}
                    onChange={(e) => setSubModel(e.target.value)}
                    placeholder="optional"
                  />
                )}
              </Field>

              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input type="checkbox" checked={runCode} onChange={(e) => setRunCode(e.target.checked)} />
                run_code (execute python fenced blocks)
              </label>
              <label className="mt-2 flex items-center gap-2 text-sm text-gray-700">
                <input type="checkbox" checked={mock} onChange={(e) => setMock(e.target.checked)} />
                mock (validate mockpaper numbering / inline answers)
              </label>
              <label className="mt-2 flex items-center gap-2 text-sm text-gray-700">
                <input type="checkbox" checked={aiReview} disabled={!mock} onChange={(e) => setAiReview(e.target.checked)} />
                ai_review (main judges + sub challenges + consensus revision)
              </label>
            </div>
          </div>

          <div className="mt-4 flex items-center gap-3">
            <button
              className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-60"
              type="submit"
              disabled={busy}
            >
              {busy ? 'Submitting…' : 'Create job'}
            </button>
            {error && <div className="text-sm text-red-700">{error}</div>}
          </div>

          {jobId && (
            <div className="mt-4 flex items-center gap-3">
              <button type="button" className="rounded-md border px-3 py-1 text-sm hover:bg-gray-50" onClick={fetchOnce}>
                Snapshot result
              </button>
              <span className="text-sm text-gray-600">(captures current job JSON once)</span>
            </div>
          )}

          {lastResult?.job.result && (
            <pre className="mt-4 max-h-80 overflow-auto rounded-md bg-gray-50 p-3 text-xs">
              {JSON.stringify(lastResult.job.result, null, 2)}
            </pre>
          )}
        </form>

        <div className="space-y-4">
          {jobId ? <JobStatusCard jobId={jobId} onMissing={() => setJobId(null)} /> : <EmptyRightPanel />}
          {jobId ? (
            <div className="rounded-lg border bg-white shadow-sm">
              <div className="flex items-center justify-between border-b px-4 py-3">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="font-semibold">AI thinking (log)</div>
                    {logBusy ? <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-blue-500" /> : <span className="inline-block h-2 w-2 rounded-full bg-gray-300" />}
                  </div>
                  <div className="mt-1 text-xs text-gray-500">
                    {streamProgress?.stage ? `stage: ${String(streamProgress.stage)}` : logBusy ? 'Streaming…' : 'Idle'}
                    {streamProgress?.message ? ` (${String(streamProgress.message)})` : ''}
                  </div>
                </div>

                <div className="w-40">
                  <ProgressBar stage={String(streamProgress?.stage || lastResult?.job?.progress?.stage || '')} />
                </div>
              </div>
              <div className="max-h-[420px] overflow-auto p-4">
                {logMessages.length === 0 ? (
                  <div className="text-sm text-gray-500">No log yet.</div>
                ) : (
                  <div className="space-y-3">
                    {logMessages.map((m, idx) => (
                      <div key={idx} className={m.role === 'system' ? 'flex justify-center' : 'flex justify-start'}>
                        <div
                          className={
                            m.role === 'system'
                              ? 'rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700'
                              : 'max-w-[90%] rounded-2xl bg-gray-100 px-4 py-2 text-xs text-gray-900'
                          }
                        >
                          <div className="whitespace-pre-wrap break-words">{m.content}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {lastResult?.job?.result && typeof (lastResult.job.result as any).thinking_markdown === 'string' ? (
                <div className="border-t bg-gray-50 px-4 py-2 text-xs text-gray-700">
                  Saved markdown:{' '}
                  <a
                    className="text-blue-700 hover:underline"
                    href={`/view/md?path=${encodeURIComponent(String((lastResult.job.result as any).thinking_markdown))}`}
                  >
                    {String((lastResult.job.result as any).thinking_markdown)}
                  </a>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function ProgressBar(props: { stage: string }) {
  const stage = (props.stage || '').toLowerCase().trim()
  const pct =
    stage === 'starting'
      ? 5
      : stage === 'scan'
        ? 25
        : stage === 'mock_checks'
          ? 55
          : stage === 'llm_review'
            ? 85
            : stage === 'done'
              ? 100
              : stage
                ? 10
                : 0

  return (
    <div className="w-full">
      <div className="h-2 w-full rounded-full bg-gray-100">
        <div className="h-2 rounded-full bg-blue-600 transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 text-right text-[11px] text-gray-500">{pct}%</div>
    </div>
  )
}

function Field(props: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="text-sm font-medium text-gray-700">{props.label}</label>
      <div className="mt-1">{props.children}</div>
    </div>
  )
}

function EmptyRightPanel() {
  return (
    <div className="rounded-lg border bg-white p-4 text-sm text-gray-600 shadow-sm">
      Create a validate job to see status here.
    </div>
  )
}
