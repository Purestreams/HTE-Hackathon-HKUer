import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { loadJobs } from '../lib/jobHistory'
import { useActiveSessionId } from '../hooks/useActiveSessionId'

export function Dashboard() {
  const jobs = useMemo(() => loadJobs(), [])
  const sessionId = useActiveSessionId()

  const sections: Array<{ title: string; items: FeatureItem[] }> = useMemo(
    () => [
      {
        title: 'Core workflow',
        items: [
          {
            title: 'Upload',
            desc: 'Upload one or many files (pdf / md / txt) into a category for this session.',
            to: '/upload',
          },
          {
            title: 'PDF Ingest',
            desc: 'Convert PDFs to Markdown (auto-routes between embedded text and vision conversion).',
            to: '/ingest/pdf',
          },
          {
            title: 'Mockpaper',
            desc: 'Generate a mock exam from your session sources with controllable question types.',
            to: '/mockpaper',
          },
          {
            title: 'Validate',
            desc: 'Run sandbox/code checks and a two-model consensus review; saves a Markdown report.',
            to: '/validate',
          },
        ],
      },
      {
        title: 'Browse & export',
        items: [
          {
            title: 'Library',
            desc: 'Browse session files, view Markdown/PDF, and generate “View PDF” for Markdown via pandoc.',
            to: '/library',
          },
          {
            title: 'Chat',
            desc: 'Ask questions across your session documents with streaming answers (Markdown + LaTeX).',
            to: '/chat',
          },
        ],
      },
      {
        title: 'Manage',
        items: [
          {
            title: 'Snapshots',
            desc: 'Save and restore session source snapshots so you can iterate safely.',
            to: '/snapshots',
          },
          {
            title: 'Jobs',
            desc: 'Inspect job history, progress logs, and results for long-running tasks.',
            to: '/jobs',
          },
        ],
      },
    ],
    [],
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-600">
          Upload documents, ingest PDFs, generate mock papers, validate outputs, and export/view your materials.
        </p>
        <div className="mt-2 text-xs text-gray-500">
          Active session: <span className="font-mono">{sessionId || 'repo'}</span>
        </div>
      </div>

      {sections.map((sec) => (
        <section key={sec.title} className="space-y-3">
          <div className="text-sm font-semibold text-gray-900">{sec.title}</div>
          <div className="grid gap-4 md:grid-cols-2">
            {sec.items.map((it) => (
              <FeatureCard key={it.to} title={it.title} desc={it.desc} to={it.to} />
            ))}
          </div>
        </section>
      ))}

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

type FeatureItem = { title: string; desc: string; to: string }

function FeatureCard(props: FeatureItem) {
  return (
    <Link to={props.to} className="rounded-lg border bg-white p-4 shadow-sm hover:border-gray-300">
      <div className="text-lg font-semibold text-gray-900">{props.title}</div>
      <div className="mt-1 text-sm text-gray-600">{props.desc}</div>
    </Link>
  )
}
