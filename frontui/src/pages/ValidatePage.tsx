import { useState, type FormEvent, type ReactNode } from 'react'
import { apiFetch, type JobCreateResponse, type JobStatusResponse } from '../lib/api'
import { JobStatusCard } from '../components/JobStatusCard'
import { saveJob } from '../lib/jobHistory'

export function ValidatePage() {
  const [sourcesDir, setSourcesDir] = useState('sources')
  const [runCode, setRunCode] = useState(true)
  const [mock, setMock] = useState(true)

  const [jobId, setJobId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [lastResult, setLastResult] = useState<JobStatusResponse | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setJobId(null)

    try {
      const payload = { sources_dir: sourcesDir, run_code: runCode, mock }
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
    const res = await apiFetch<JobStatusResponse>(`/api/jobs/${jobId}`)
    setLastResult(res)
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Validate</h1>
        <p className="mt-1 text-sm text-gray-600">Runs code-block sandbox checks and mockpaper sanity checks.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <form onSubmit={submit} className="rounded-lg border bg-white p-4 shadow-sm">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="sources_dir">
              <input className="w-full rounded-md border px-3 py-2 text-sm" value={sourcesDir} onChange={(e) => setSourcesDir(e.target.value)} />
            </Field>
            <div className="sm:col-span-2">
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input type="checkbox" checked={runCode} onChange={(e) => setRunCode(e.target.checked)} />
                run_code (execute python fenced blocks)
              </label>
              <label className="mt-2 flex items-center gap-2 text-sm text-gray-700">
                <input type="checkbox" checked={mock} onChange={(e) => setMock(e.target.checked)} />
                mock (validate mockpaper numbering / inline answers)
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

        <div>{jobId ? <JobStatusCard jobId={jobId} /> : <EmptyRightPanel />}</div>
      </div>
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
