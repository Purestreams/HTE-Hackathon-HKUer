import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, apiFetch, type JobStatusResponse } from '../lib/api'
import { useInterval } from '../hooks/useInterval'

export function JobStatusCard(props: { jobId: string; onMissing?: () => void }) {
  const { jobId } = props
  const [data, setData] = useState<JobStatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [missing, setMissing] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const status = data?.job.status
  const shouldPoll = useMemo(() => {
    return status === undefined || status === 'queued' || status === 'running'
  }, [status])

  async function refresh(manual = false) {
    try {
      if (manual) setRefreshing(true)
      setError(null)
      setMissing(false)
      const res = await apiFetch<JobStatusResponse>(`/api/jobs/${jobId}`)
      setData(res)
    } catch (e: any) {
      const msg = String(e?.message ?? e)
      if (e instanceof ApiError && e.status === 404) {
        setMissing(true)
        setData(null)
        setError(null)
        props.onMissing?.()
        return
      }
      // Backward-compat: older apiFetch threw Error only.
      if (msg.toLowerCase().includes('job not found')) {
        setMissing(true)
        setData(null)
        setError(null)
        props.onMissing?.()
        return
      }
      setError(msg)
    } finally {
      if (manual) setRefreshing(false)
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId])

  useInterval(() => {
    if (shouldPoll) refresh()
  }, shouldPoll ? 1200 : null)

  if (missing) return null

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="font-semibold">Job</div>
        <button
          className="rounded-md border px-3 py-1 text-sm hover:bg-gray-50"
          onClick={() => refresh(true)}
          type="button"
          disabled={refreshing}
        >
          {refreshing ? 'Refreshing…' : 'Refresh'}
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
            {data.job.params?.model && (
              <div>
                <span className="text-gray-500">model:</span> {String(data.job.params.model)}
              </div>
            )}
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
              {(data.job.status === 'running' || data.job.status === 'queued') && (
                <span className="ml-2 inline-flex items-center gap-2 text-xs text-blue-600">
                  <span className="inline-block h-2.5 w-2.5 animate-bounce rounded-full bg-blue-500" />
                </span>
              )}
            </div>

            {data.job.progress && (data.job.status === 'queued' || data.job.status === 'running') && (
              <div className="mt-2 rounded-md bg-gray-50 p-2 text-xs text-gray-700">
                <div>
                  <span className="text-gray-500">stage:</span> {data.job.progress.stage ?? '-'}
                  {data.job.progress.message ? <span className="text-gray-500"> {' '}({data.job.progress.message})</span> : null}
                </div>
                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                  <span>
                    <span className="text-gray-500">elapsed:</span>{' '}
                    {typeof data.job.progress.elapsed_sec === 'number'
                      ? `${data.job.progress.elapsed_sec.toFixed(1)}s`
                      : '-'}
                  </span>
                  <span>
                    <span className="text-gray-500">tok/s:</span>{' '}
                    {typeof data.job.progress.tokens_per_sec === 'number'
                      ? data.job.progress.tokens_per_sec.toFixed(1)
                      : '-'}
                  </span>
                  <span>
                    <span className="text-gray-500">tokens:</span>{' '}
                    {typeof data.job.progress.tokens === 'number' ? data.job.progress.tokens : '-'}
                  </span>
                </div>
                {Array.isArray((data.job.progress as any).sample_files) && (data.job.progress as any).sample_files.length > 0 && (
                  <div className="mt-2">
                    <div className="text-gray-500">sample_files:</div>
                    <ul className="mt-1 list-disc pl-4">
                      {(data.job.progress as any).sample_files.map((p: string) => (
                        <li key={p} className="break-all">{p}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {data.job.error && <div className="mt-2 text-red-700">{data.job.error}</div>}
            {data.job.result && (
              <ResultLinks result={data.job.result} />
            )}
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

function ResultLinks(props: { result: Record<string, unknown> }) {
  const mdPath = (props.result['markdown_path'] ?? props.result['markdown']) as string | undefined
  if (!mdPath || typeof mdPath !== 'string') return null

  // Backend returns paths relative to the ACTIVE SESSION sources root.
  // Backward-compat: if the path contains '/sources/', strip prefix up to that.
  const idx = mdPath.indexOf('/sources/')
  const relToSources = idx >= 0 ? mdPath.slice(idx + '/sources/'.length) : mdPath

  return (
    <div className="mt-2 flex items-center gap-3 text-sm">
      <Link className="text-blue-700 hover:underline" to={`/view/md?path=${encodeURIComponent(relToSources)}`}>
        View Markdown
      </Link>
      <span className="text-xs text-gray-500">{relToSources}</span>
    </div>
  )
}
