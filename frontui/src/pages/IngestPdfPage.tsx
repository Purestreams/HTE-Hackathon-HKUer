import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { apiFetch, type UploadResponse } from '../lib/api'
import { JobStatusCard } from '../components/JobStatusCard'
import { saveJob } from '../lib/jobHistory'

export function IngestPdfPage() {
  const [file, setFile] = useState<File | null>(null)
  const [category, setCategory] = useState('assignment')
  const [mode, setMode] = useState<'auto' | 'text' | 'vision'>('auto')
  const [maxPages, setMaxPages] = useState<string>('')
  const [diagPages, setDiagPages] = useState<number>(3)
  const [dpi, setDpi] = useState<number>(300)
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState<string>('')
  const [allowImageHeavy, setAllowImageHeavy] = useState<boolean>(false)
  const [outName, setOutName] = useState<string>('')

  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    ;(async () => {
      try {
        const res = await apiFetch<{ ok: true; image_models: string[]; main_model?: string }>('/api/models')
        const list = res.image_models || []
        setModels(list)
        if (!model && res.main_model && list.includes(res.main_model)) {
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
      if (!file) {
        setError('Pick a PDF file first')
        return
      }

      const fd = new FormData()
      fd.append('file', file)
      fd.append('category', category)
      fd.append('ingest', '1')
      fd.append('mode', mode)
      fd.append('diag_pages', String(diagPages))
      fd.append('dpi', String(dpi))
      if (maxPages.trim()) fd.append('max_pages', String(Number(maxPages)))
      if (model.trim()) fd.append('model', model.trim())
      if (outName.trim()) fd.append('out_name', outName.trim())
      if (allowImageHeavy) fd.append('allow_image_heavy', '1')

      const res = await apiFetch<UploadResponse>('/api/upload', {
        method: 'POST',
        body: fd as any,
      })
      if (res.job_id) {
        setJobId(res.job_id)
        saveJob({ id: res.job_id, type: 'pdf_ingest', createdAt: new Date().toISOString() })
      } else {
        setError('Upload succeeded but no ingest job was created (non-PDF?)')
      }
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">PDF Ingest</h1>
        <p className="mt-1 text-sm text-gray-600">Smart routing: embedded text fast-path vs vision conversion to Markdown.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <form onSubmit={submit} className="rounded-lg border bg-white p-4 shadow-sm">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="PDF file">
              <input
                className="w-full rounded-md border bg-white px-3 py-2 text-sm"
                type="file"
                accept=".pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </Field>
            <Field label="category">
              <select className="w-full rounded-md border px-3 py-2 text-sm" value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="lectureNote">lectureNote</option>
                <option value="tutorialNote">tutorialNote</option>
                <option value="assignment">assignment</option>
                <option value="pastPaper">pastPaper</option>
              </select>
            </Field>
            <Field label="mode">
              <select className="w-full rounded-md border px-3 py-2 text-sm" value={mode} onChange={(e) => setMode(e.target.value as any)}>
                <option value="auto">auto</option>
                <option value="text">text</option>
                <option value="vision">vision</option>
              </select>
            </Field>
            <Field label="max_pages (optional)">
              <input className="w-full rounded-md border px-3 py-2 text-sm" value={maxPages} onChange={(e) => setMaxPages(e.target.value)} placeholder="e.g. 5" />
            </Field>
            <Field label="diag_pages">
              <input className="w-full rounded-md border px-3 py-2 text-sm" type="number" value={diagPages} onChange={(e) => setDiagPages(Number(e.target.value))} />
            </Field>
            <Field label="dpi">
              <input className="w-full rounded-md border px-3 py-2 text-sm" type="number" value={dpi} onChange={(e) => setDpi(Number(e.target.value))} />
            </Field>
            <Field label="model (vision only)">
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
            <Field label="out_name (optional)">
              <input className="w-full rounded-md border px-3 py-2 text-sm" value={outName} onChange={(e) => setOutName(e.target.value)} placeholder="e.g. Assignment1_ingested.md" />
            </Field>
          </div>

          <label className="mt-4 flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={allowImageHeavy} onChange={(e) => setAllowImageHeavy(e.target.checked)} />
            allow_image_heavy (disable refusal)
          </label>

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
      Create an ingest job to see status here.
    </div>
  )
}
