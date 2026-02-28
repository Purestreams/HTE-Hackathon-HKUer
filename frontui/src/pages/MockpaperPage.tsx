import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { apiFetch, type JobCreateResponse } from '../lib/api'
import { JobStatusCard } from '../components/JobStatusCard'
import { saveJob } from '../lib/jobHistory'

export function MockpaperPage() {
  // Paths are relative to the ACTIVE SESSION sources root.
  // A legacy "sources/" prefix is accepted by the backend but is not required.
  const [sample, setSample] = useState('assignment')
  const [outDir, setOutDir] = useState('mockpaper')
  const [name, setName] = useState('mock_inline')
  const [numQuestions, setNumQuestions] = useState<number>(10)
  const [ratios, setRatios] = useState('mcq:0.3,short:0.4,code:0.3')
  const [language, setLanguage] = useState('auto')
  const [separate, setSeparate] = useState(false)

  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [maxPages, setMaxPages] = useState<string>('')
  const [temperature, setTemperature] = useState<string>('')
  const [topic, setTopic] = useState('')
  const [formatPrompt, setFormatPrompt] = useState('')

  const [jobId, setJobId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    ;(async () => {
      try {
        const res = await apiFetch<{ ok: true; models: string[]; text_models: string[]; main_model?: string }>('/api/models')
        const merged = Array.from(new Set([...(res.models || []), ...(res.text_models || [])]))
        setModels(merged)
        if (!model && res.main_model && merged.includes(res.main_model)) {
          setModel(res.main_model)
        }
      } catch {
        setModels([])
      }
    })()
  }, [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setJobId(null)

    try {
      const payload: any = {
        sample,
        out_dir: outDir,
        name,
        num_questions: numQuestions,
        ratios,
        language,
        separate,
        topic,
        format_prompt: formatPrompt,
      }
      if (model.trim()) payload.model = model.trim()
      if (maxPages.trim()) payload.max_pages = Number(maxPages)
      if (temperature.trim()) payload.temperature = Number(temperature)

      const res = await apiFetch<JobCreateResponse>('/api/mockpaper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      setJobId(res.job_id)
      saveJob({ id: res.job_id, type: 'mockpaper', createdAt: new Date().toISOString() })
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Mockpaper</h1>
        <p className="mt-1 text-sm text-gray-600">Generates a mock exam with step-by-step inline solutions (default), or separate paper+answers.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <form onSubmit={submit} className="rounded-lg border bg-white p-4 shadow-sm">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="sample">
              <input className="w-full rounded-md border px-3 py-2 text-sm" value={sample} onChange={(e) => setSample(e.target.value)} />
            </Field>
            <Field label="out_dir">
              <input className="w-full rounded-md border px-3 py-2 text-sm" value={outDir} onChange={(e) => setOutDir(e.target.value)} />
            </Field>
            <Field label="name">
              <input className="w-full rounded-md border px-3 py-2 text-sm" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="num_questions">
              <input className="w-full rounded-md border px-3 py-2 text-sm" type="number" value={numQuestions} onChange={(e) => setNumQuestions(Number(e.target.value))} />
            </Field>
            <div className="sm:col-span-2">
              <Field label="ratios">
                <input className="w-full rounded-md border px-3 py-2 text-sm" value={ratios} onChange={(e) => setRatios(e.target.value)} />
              </Field>
            </div>
            <Field label="language">
              <select className="w-full rounded-md border px-3 py-2 text-sm" value={language} onChange={(e) => setLanguage(e.target.value)}>
                <option value="auto">auto</option>
                <option value="en">en</option>
                <option value="zh">zh</option>
                <option value="mixed">mixed</option>
              </select>
            </Field>
            <Field label="output mode">
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input type="checkbox" checked={separate} onChange={(e) => setSeparate(e.target.checked)} />
                separate (paper + answer key)
              </label>
            </Field>
          </div>

          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-medium text-gray-700">Advanced</summary>
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <Field label="model (any)">
                {models.length ? (
                  <select className="w-full rounded-md border px-3 py-2 text-sm" value={model} onChange={(e) => setModel(e.target.value)}>
                    <option value="">(default)</option>
                    {models.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input className="w-full rounded-md border px-3 py-2 text-sm" value={model} onChange={(e) => setModel(e.target.value)} placeholder="defaults to MOCKPAPER_MODEL/ARK_MODEL" />
                )}
              </Field>
              <Field label="max_pages (optional)">
                <input className="w-full rounded-md border px-3 py-2 text-sm" value={maxPages} onChange={(e) => setMaxPages(e.target.value)} />
              </Field>
              <Field label="temperature (optional)">
                <input className="w-full rounded-md border px-3 py-2 text-sm" value={temperature} onChange={(e) => setTemperature(e.target.value)} />
              </Field>
              <Field label="topic (optional)">
                <input className="w-full rounded-md border px-3 py-2 text-sm" value={topic} onChange={(e) => setTopic(e.target.value)} />
              </Field>
              <div className="sm:col-span-2">
                <Field label="format_prompt (optional)">
                  <textarea className="h-24 w-full rounded-md border px-3 py-2 text-sm" value={formatPrompt} onChange={(e) => setFormatPrompt(e.target.value)} />
                </Field>
              </div>
            </div>
          </details>

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

          {jobId && <div className="mt-3 text-sm text-gray-700">Created job: <span className="font-mono">{jobId}</span></div>}
        </form>

        <div>{jobId ? <JobStatusCard jobId={jobId} onMissing={() => setJobId(null)} /> : <EmptyRightPanel />}</div>
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
      Create a mockpaper job to see status here.
    </div>
  )
}
