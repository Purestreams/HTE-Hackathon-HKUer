import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { apiFetch, type UploadResponse } from '../lib/api'
import { JobStatusCard } from '../components/JobStatusCard'
import { saveJob } from '../lib/jobHistory'

export function IngestPdfPage() {
  const [files, setFiles] = useState<File[]>([])
  const [category, setCategory] = useState('assignment')
  const [mode, setMode] = useState<'auto' | 'text' | 'vision'>('auto')
  const [maxPages, setMaxPages] = useState<string>('')
  const [diagPages, setDiagPages] = useState<number>(3)
  const [dpi, setDpi] = useState<number>(300)
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState<string>('')
  const [allowImageHeavy, setAllowImageHeavy] = useState<boolean>(false)
  const [outName, setOutName] = useState<string>('')

  const [jobIds, setJobIds] = useState<string[]>([])
  const [submitNote, setSubmitNote] = useState<string | null>(null)
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
    setJobIds([])
    setSubmitNote(null)

    try {
      if (!files.length) {
        setError('Pick at least one PDF file first')
        return
      }

      if (files.length > 1 && outName.trim()) {
        setSubmitNote('Note: out_name is ignored when ingesting multiple PDFs (each PDF will be saved as <pdf_stem>.md).')
      }

      const created: string[] = []
      for (let i = 0; i < files.length; i++) {
        const f = files[i]!
        setSubmitNote(`Uploading ${i + 1}/${files.length}: ${f.name}`)

        const fd = new FormData()
        fd.append('file', f)
        fd.append('category', category)
        fd.append('ingest', '1')
        fd.append('mode', mode)
        fd.append('diag_pages', String(diagPages))
        fd.append('dpi', String(dpi))
        if (maxPages.trim()) fd.append('max_pages', String(Number(maxPages)))
        if (model.trim()) fd.append('model', model.trim())
        if (files.length === 1 && outName.trim()) fd.append('out_name', outName.trim())
        if (allowImageHeavy) fd.append('allow_image_heavy', '1')

        const res = await apiFetch<UploadResponse>('/api/upload', {
          method: 'POST',
          body: fd as any,
        })

        if (res.job_id) {
          created.push(res.job_id)
          saveJob({ id: res.job_id, type: 'pdf_ingest', createdAt: new Date().toISOString() })
        } else {
          throw new Error(`Upload succeeded but no ingest job was created for ${f.name}`)
        }
      }

      setJobIds(created)
      setSubmitNote(`Created ${created.length} ingest job(s).`)
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
                multiple
                onChange={(e) => setFiles(Array.from(e.target.files || []))}
              />
            </Field>
            <div className="text-xs text-gray-500 sm:col-span-2">
              Selected: {files.length} file(s)
              {files.length > 0 ? (
                <ul className="mt-1 list-disc pl-4">
                  {files.slice(0, 6).map((f) => (
                    <li key={f.name} className="break-all">
                      {f.name}
                    </li>
                  ))}
                  {files.length > 6 ? <li>…and {files.length - 6} more</li> : null}
                </ul>
              ) : null}
            </div>
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
              <input
                className="w-full rounded-md border px-3 py-2 text-sm disabled:bg-gray-100"
                value={outName}
                onChange={(e) => setOutName(e.target.value)}
                placeholder={files.length > 1 ? 'Disabled for multi-file ingest' : 'e.g. Assignment1_ingested.md'}
                disabled={files.length > 1}
              />
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
              {busy ? 'Submitting…' : files.length > 1 ? 'Create jobs' : 'Create job'}
            </button>
            {error && <div className="text-sm text-red-700">{error}</div>}
          </div>

          {submitNote && <div className="mt-3 text-xs text-gray-600">{submitNote}</div>}
          {jobIds.length > 0 && (
            <div className="mt-3 text-sm text-gray-700">
              Created {jobIds.length} job(s)
            </div>
          )}
        </form>

        <div>
          {jobIds.length ? (
            <div className="space-y-3">
              {jobIds.map((id) => (
                <JobStatusCard key={id} jobId={id} onMissing={() => setJobIds((prev) => prev.filter((x) => x !== id))} />
              ))}
            </div>
          ) : (
            <EmptyRightPanel />
          )}
        </div>
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
