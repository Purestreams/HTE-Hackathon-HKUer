import { useEffect, useState, type FormEvent } from 'react'
import { apiFetch, type Categories, type UploadResponse } from '../lib/api'
import { JobStatusCard } from '../components/JobStatusCard'
import { saveJob } from '../lib/jobHistory'

type UploadItem = {
  fileName: string
  status: 'queued' | 'uploading' | 'ok' | 'error'
  response?: UploadResponse
  error?: string
}

export function UploadPage() {
  const [categories, setCategories] = useState<string[]>([])
  const [category, setCategory] = useState('lectureNote')
  const [files, setFiles] = useState<File[]>([])
  const [items, setItems] = useState<UploadItem[]>([])
  const [jobIds, setJobIds] = useState<string[]>([])
  const [submitNote, setSubmitNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    ;(async () => {
      try {
        const res = await apiFetch<Categories>('/api/categories')
        setCategories(res.categories)
        if (res.categories.includes(category) === false) {
          setCategory(res.categories[0] ?? 'lectureNote')
        }
      } catch (e: any) {
        setError(String(e?.message ?? e))
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!files.length) {
      setError('Pick at least one file first')
      return
    }

    setBusy(true)
    setError(null)
    setItems(files.map((f) => ({ fileName: f.name, status: 'queued' })))
    setJobIds([])
    setSubmitNote(null)

    const patchItem = (idx: number, patch: Partial<UploadItem>) => {
      setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)))
    }

    try {
      const createdJobs: string[] = []
      let okCount = 0
      for (let i = 0; i < files.length; i++) {
        const f = files[i]!
        setSubmitNote(`Uploading ${i + 1}/${files.length}: ${f.name}`)
        patchItem(i, { status: 'uploading', error: undefined, response: undefined })

        try {
          const fd = new FormData()
          fd.append('file', f)
          fd.append('category', category)

          const body = await apiFetch<UploadResponse>('/api/upload', { method: 'POST', body: fd as any })
          patchItem(i, { status: 'ok', response: body })
          okCount++

          if (body.job_id) {
            createdJobs.push(body.job_id)
            saveJob({ id: body.job_id, type: 'pdf_ingest', createdAt: new Date().toISOString() })
          }
        } catch (e: any) {
          patchItem(i, { status: 'error', error: String(e?.message ?? e) })
        }
      }

      setJobIds(createdJobs)
      setSubmitNote(`Uploaded ${okCount}/${files.length} file(s).`)
    } catch (e: any) {
      setError(String(e?.message ?? e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Upload</h1>
        <p className="mt-1 text-sm text-gray-600">Upload files into sources/&lt;category&gt;/ for ingestion and RAG.</p>
      </div>

      <form onSubmit={onSubmit} className="rounded-lg border bg-white p-4 shadow-sm">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="text-sm font-medium text-gray-700">Category</label>
            <select
              className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {categories.length ? (
                categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))
              ) : (
                <option value={category}>{category}</option>
              )}
            </select>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700">File</label>
            <input
              className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-sm"
              type="file"
              multiple
              onChange={(e) => setFiles(Array.from(e.target.files || []))}
            />
            <div className="mt-1 text-xs text-gray-500">Selected: {files.length} file(s)</div>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button
            className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-60"
            type="submit"
            disabled={busy}
          >
            {busy ? 'Uploading…' : files.length > 1 ? 'Upload files' : 'Upload'}
          </button>

          {error && <div className="text-sm text-red-700">{error}</div>}
        </div>

        {submitNote && <div className="mt-3 text-xs text-gray-600">{submitNote}</div>}

        {items.length > 0 && (
          <div className="mt-4 overflow-hidden rounded-md border">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-gray-700">
                <tr>
                  <th className="px-4 py-3 font-medium">File</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Saved path</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, idx) => (
                  <tr key={`${idx}-${it.fileName}`} className="border-t">
                    <td className="px-4 py-3 text-gray-900 break-all">{it.fileName}</td>
                    <td className="px-4 py-3">
                      {it.status === 'ok' ? (
                        <span className="text-green-700">ok</span>
                      ) : it.status === 'error' ? (
                        <span className="text-red-700">error</span>
                      ) : it.status === 'uploading' ? (
                        <span className="text-gray-700">uploading…</span>
                      ) : (
                        <span className="text-gray-700">queued</span>
                      )}
                      {it.error ? <div className="mt-1 text-xs text-red-700">{it.error}</div> : null}
                    </td>
                    <td className="px-4 py-3 text-gray-700 break-all">{it.response?.path ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {jobIds.length > 0 && (
          <div className="mt-4 space-y-3">
            {jobIds.map((id) => (
              <JobStatusCard key={id} jobId={id} onMissing={() => setJobIds((prev) => prev.filter((x) => x !== id))} />
            ))}
          </div>
        )}
      </form>

      <div className="text-xs text-gray-500">
        Tip: set <span className="font-mono">VITE_API_BASE_URL</span> in frontui/.env to point to your backend.
      </div>
    </div>
  )
}
