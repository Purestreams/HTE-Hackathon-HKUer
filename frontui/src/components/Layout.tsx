import { Link, NavLink, Outlet } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { apiFetch, apiBaseUrl, type Health } from '../lib/api'
import { SessionSelector } from './SessionSelector'

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/upload', label: 'Upload' },
  { to: '/ingest/pdf', label: 'PDF Ingest' },
  { to: '/mockpaper', label: 'Mockpaper' },
  { to: '/validate', label: 'Validate' },
  { to: '/library', label: 'Library' },
  { to: '/snapshots', label: 'Snapshots' },
  { to: '/jobs', label: 'Jobs' },
]

export function Layout() {
  const [health, setHealth] = useState<Health | null>(null)
  const [healthErr, setHealthErr] = useState<string | null>(null)

  useEffect(() => {
    ;(async () => {
      try {
        setHealthErr(null)
        const res = await apiFetch<Health>('/health')
        setHealth(res)
      } catch (e: any) {
        setHealthErr(String(e?.message ?? e))
      }
    })()
  }, [])

  return (
    <div className="flex h-full bg-gray-50">
      <aside className="w-64 shrink-0 border-r bg-white">
        <div className="border-b px-4 py-3">
          <Link to="/" className="text-lg font-semibold">
            HTE Learning Platform
          </Link>
          <div className="mt-1 text-xs text-gray-500">API: {apiBaseUrl}</div>
        </div>
        <nav className="p-2">
          {navItems.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              className={({ isActive }) =>
                [
                  'block rounded-md px-3 py-2 text-sm',
                  isActive ? 'bg-gray-100 font-medium text-gray-900' : 'text-gray-700 hover:bg-gray-50',
                ].join(' ')
              }
              end={it.to === '/'}
            >
              {it.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b bg-white px-6 py-3">
          <div className="text-sm text-gray-600">
            {health ? (
              <span>
                Backend healthy • <span className="font-mono">{health.time}</span>
              </span>
            ) : healthErr ? (
              <span className="text-red-700">Backend unreachable: {healthErr}</span>
            ) : (
              <span>Checking backend…</span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <SessionSelector />
          </div>
        </header>

        <div className="min-w-0 flex-1 p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
