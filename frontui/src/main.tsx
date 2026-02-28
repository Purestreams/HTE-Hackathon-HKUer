import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'
import './index.css'

import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { UploadPage } from './pages/UploadPage'
import { IngestPdfPage } from './pages/IngestPdfPage'
import { MockpaperPage } from './pages/MockpaperPage'
import { ValidatePage } from './pages/ValidatePage'
import { SnapshotsPage } from './pages/SnapshotsPage'
import { JobsPage } from './pages/JobsPage'
import { LibraryPage } from './pages/LibraryPage'
import { ViewMarkdownPage } from './pages/ViewMarkdownPage'
import { ViewPdfPage } from './pages/ViewPdfPage'

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'upload', element: <UploadPage /> },
      { path: 'ingest/pdf', element: <IngestPdfPage /> },
      { path: 'mockpaper', element: <MockpaperPage /> },
      { path: 'validate', element: <ValidatePage /> },
      { path: 'snapshots', element: <SnapshotsPage /> },
      { path: 'jobs', element: <JobsPage /> },
      { path: 'library', element: <LibraryPage /> },
      { path: 'view/md', element: <ViewMarkdownPage /> },
      { path: 'view/pdf', element: <ViewPdfPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
