import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { loadJobs } from '../lib/jobHistory'

export function Dashboard() {
  const jobs = useMemo(() => loadJobs(), [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-600">Upload documents, ingest PDFs, generate mock papers, and validate outputs.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <QuickCard title="Upload" desc="Upload a PDF/MD/TXT into sources/<category>/" to="/upload" />
        <QuickCard title="PDF Ingest" desc="Auto-route: embedded text vs vision conversion" to="/ingest/pdf" />
        <QuickCard title="Mockpaper" desc="Generate mock exam with inline answers" to="/mockpaper" />
        <QuickCard title="Validate" desc="Run code sandbox + mock checks" to="/validate" />
      </div>

      <div className="rounded-lg border bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="font-semibold">Recent jobs</div>
          <Link className="text-sm text-blue-700 hover:underline" to="/jobs">
            Open Jobs
          </Link>
        </div>
        {jobs.length === 0 ? (
          <div className="mt-2 text-sm text-gray-600">No jobs yet.</div>
        ) : (
          <ul className="mt-3 divide-y">
            {jobs.slice(0, 8).map((j) => (
              <li key={j.id} className="py-2 text-sm">
                <span className="font-mono">{j.id}</span>
                {j.type ? <span className="ml-2 rounded bg-gray-100 px-2 py-0.5 text-xs">{j.type}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function QuickCard(props: { title: string; desc: string; to: string }) {
  return (
    <Link to={props.to} className="rounded-lg border bg-white p-4 shadow-sm hover:border-gray-300">
      <div className="text-lg font-semibold text-gray-900">{props.title}</div>
      <div className="mt-1 text-sm text-gray-600">{props.desc}</div>
    </Link>
  )
}
