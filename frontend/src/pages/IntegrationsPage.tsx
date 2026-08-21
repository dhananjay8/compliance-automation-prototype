import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '../lib/api'
import { Play, RefreshCw, Activity } from 'lucide-react'

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<any[]>([])
  const [jobs, setJobs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = () => {
    apiGet('/v1/integrations').then(setIntegrations).catch((e) => setError(e.message))
  }

  useEffect(() => { load() }, [])

  const handleSync = async (id: string) => {
    setLoading(true)
    try {
      await apiPost(`/v1/integrations/${id}/sync`)
      load()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleTest = async (id: string) => {
    try {
      await apiPost(`/v1/integrations/${id}/test`)
      load()
    } catch (e: any) {
      setError(e.message)
    }
  }

  const loadJobs = async (id: string) => {
    try {
      const rows = await apiGet(`/v1/integrations/${id}/sync-jobs`)
      setJobs(rows)
    } catch (e: any) {
      setError(e.message)
    }
  }

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-semibold text-slate-800">Integrations</h2>
      {error && <p className="text-red-600">{error}</p>}
      {loading && <p className="text-slate-500">Syncing…</p>}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-100">
            <tr>
              <th className="p-3 text-left font-medium text-slate-600">Name</th>
              <th className="p-3 text-left font-medium text-slate-600">Connector</th>
              <th className="p-3 text-left font-medium text-slate-600">Status</th>
              <th className="p-3 text-left font-medium text-slate-600">Last Sync</th>
              <th className="p-3 text-left font-medium text-slate-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            {integrations.map((i) => (
              <tr key={i.id} className="border-b last:border-b-0">
                <td className="p-3">{i.name}</td>
                <td className="p-3 capitalize">{i.connector}</td>
                <td className="p-3 capitalize">{i.status}</td>
                <td className="p-3">{i.last_sync_at ? new Date(i.last_sync_at).toLocaleString() : '-'}</td>
                <td className="p-3 flex gap-2">
                  <Button icon={<RefreshCw size={16} />} onClick={() => handleTest(i.id)}>Test</Button>
                  <Button icon={<Play size={16} />} onClick={() => handleSync(i.id)}>Sync</Button>
                  <Button icon={<Activity size={16} />} onClick={() => loadJobs(i.id)}>Jobs</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {jobs.length > 0 && (
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-medium mb-2 text-slate-800">Sync Jobs</h3>
          <ul className="text-sm space-y-1">
            {jobs.map((j) => (
              <li key={j.id} className="text-slate-600">
                {j.status} — {j.watermark ?? '-'} resources — {new Date(j.started_at).toLocaleString()}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Button({ children, icon, onClick }: any) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1 px-2 py-1 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700"
    >
      {icon}
      {children}
    </button>
  )
}
