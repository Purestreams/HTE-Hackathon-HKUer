import { useEffect, useMemo, useState } from 'react'
import { JobStatusCard } from '../components/JobStatusCard'
import { loadJobs, type JobRef } from '../lib/jobHistory'

export function JobsPage() {
  const [jobs, setJobs] = useState<JobRef[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    const list = loadJobs()
    setJobs(list)
    setSelectedId(list[0]?.id ?? null)
  }, [])

  const selected = useMemo(() => jobs.find((j) => j.id === selectedId) ?? null, [jobs, selectedId])

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Jobs</h1>
        <p className="mt-1 text-sm text-gray-600">This list is client-side (localStorage) from jobs you created in the UI.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-lg border bg-white p-3 shadow-sm">
          <div className="mb-2 text-sm font-medium text-gray-800">Recent jobs</div>
          <div className="max-h-[28rem] space-y-1 overflow-auto">
            {jobs.map((j) => (
              <button
                key={j.id}
                className={
                  'w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-gray-50 ' +
                  (selectedId === j.id ? 'border-gray-900 bg-gray-50' : 'border-gray-200')
                }
                onClick={() => setSelectedId(j.id)}
                type="button"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-gray-800">{j.id}</span>
                  <span className="text-xs text-gray-500">{j.type ?? '-'}</span>
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  {j.createdAt ? new Date(j.createdAt).toLocaleString() : '-'}
                </div>
              </button>
            ))}
            {jobs.length === 0 && <div className="py-6 text-center text-sm text-gray-600">No jobs yet.</div>}
          </div>
        </div>

        <div className="lg:col-span-2">{selected ? <JobStatusCard jobId={selected.id} /> : <EmptyPanel />}</div>
      </div>
    </div>
  )
}

function EmptyPanel() {
  return (
    <div className="rounded-lg border bg-white p-4 text-sm text-gray-600 shadow-sm">
      Select a job to see status.
    </div>
  )
}
