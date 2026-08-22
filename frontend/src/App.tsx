import { useState, type ReactNode } from 'react'
import Sidebar from './components/Sidebar'
import DashboardPage from './pages/DashboardPage'
import IntegrationsPage from './pages/IntegrationsPage'
import ControlsPage from './pages/ControlsPage'
import EvidencePage from './pages/EvidencePage'
import PoliciesPage from './pages/PoliciesPage'
import WorkflowsPage from './pages/WorkflowsPage'

type Page = 'dashboard' | 'integrations' | 'controls' | 'evidence' | 'policies' | 'workflows'

const pages: Record<Page, () => ReactNode> = {
  dashboard: DashboardPage,
  integrations: IntegrationsPage,
  controls: ControlsPage,
  evidence: EvidencePage,
  policies: PoliciesPage,
  workflows: WorkflowsPage,
}

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const PageComponent = pages[page]
  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar page={page} onChange={(p) => setPage(p as Page)} />
      <main className="flex-1 overflow-auto">
        <PageComponent />
      </main>
    </div>
  )
}
