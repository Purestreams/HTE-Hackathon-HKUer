import { useEffect, useState, type FormEvent } from 'react'
import { apiFetch, type Categories, type UploadResponse } from '../lib/api'
import { JobStatusCard } from '../components/JobStatusCard'
import { saveJob } from '../lib/jobHistory'

export function UploadPage() {
  const [categories, setCategories] = useState<string[]>([])
  const [category, setCategory] = useState('lectureNote')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<UploadResponse | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
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
    if (!file) {
      setError('Pick a file first')
      return
    }

    setBusy(true)
    setError(null)
    setResult(null)
    setJobId(null)

    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('category', category)

      const body = await apiFetch<UploadResponse>('/api/upload', { method: 'POST', body: fd as any })
      setResult(body)
      if (body.job_id) {
        setJobId(body.job_id)
        saveJob({ id: body.job_id, type: 'pdf_ingest', createdAt: new Date().toISOString() })
      }
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
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button
            className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-60"
            type="submit"
            disabled={busy}
          >
            {busy ? 'Uploading…' : 'Upload'}
          </button>

          {error && <div className="text-sm text-red-700">{error}</div>}
        </div>

        {result && (
          <pre className="mt-4 max-h-80 overflow-auto rounded-md bg-gray-50 p-3 text-xs">
            {JSON.stringify(result, null, 2)}
          </pre>
        )}

        {jobId && (
          <div className="mt-4">
            <JobStatusCard jobId={jobId} onMissing={() => setJobId(null)} />
          </div>
        )}
      </form>

      <div className="text-xs text-gray-500">
        Tip: set <span className="font-mono">VITE_API_BASE_URL</span> in frontui/.env to point to your backend.
      </div>
    </div>
  )
}
