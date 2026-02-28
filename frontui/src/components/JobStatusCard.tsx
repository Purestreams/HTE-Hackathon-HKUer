import { useEffect, useMemo, useState } from 'react'
import { apiFetch, type JobStatusResponse } from '../lib/api'
import { useInterval } from '../hooks/useInterval'

export function JobStatusCard(props: { jobId: string }) {
  const { jobId } = props
  const [data, setData] = useState<JobStatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const status = data?.job.status
  const shouldPoll = useMemo(() => {
    return status === undefined || status === 'queued' || status === 'running'
  }, [status])

  async function refresh() {
    try {
      setError(null)
      const res = await apiFetch<JobStatusResponse>(`/api/jobs/${jobId}`)
      setData(res)
    } catch (e: any) {
      setError(String(e?.message ?? e))
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId])

  useInterval(() => {
    if (shouldPoll) refresh()
  }, shouldPoll ? 1200 : null)

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="font-semibold">Job</div>
        <button
          className="rounded-md border px-3 py-1 text-sm hover:bg-gray-50"
          onClick={() => refresh()}
          type="button"
        >
          Refresh
        </button>
      </div>

      <div className="mt-2 text-sm text-gray-700">
        <div>
          <span className="text-gray-500">id:</span> <span className="font-mono">{jobId}</span>
        </div>
        {error && <div className="mt-2 text-red-600">Error: {error}</div>}
        {data && (
          <>
            <div>
              <span className="text-gray-500">type:</span> {data.job.type}
            </div>
            <div>
              <span className="text-gray-500">status:</span>{' '}
              <span
                className={
                  data.job.status === 'done'
                    ? 'text-green-700'
                    : data.job.status === 'error'
                      ? 'text-red-700'
                      : 'text-blue-700'
                }
              >
                {data.job.status}
              </span>
            </div>
            {data.job.error && <div className="mt-2 text-red-700">{data.job.error}</div>}
            {data.job.result && (
              <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-gray-50 p-3 text-xs">
                {JSON.stringify(data.job.result, null, 2)}
              </pre>
            )}
          </>
        )}
      </div>
    </div>
  )
}
