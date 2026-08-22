import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '../lib/api'

type Tab = 'drift' | 'freshness' | 'scheduler' | 'analytics' | 'ai'

export default function IntelligencePage() {
  const [tab, setTab] = useState<Tab>('drift')
  const tabs: { id: Tab; label: string }[] = [
    { id: 'drift', label: 'Drift' },
    { id: 'freshness', label: 'Freshness' },
    { id: 'scheduler', label: 'Scheduler' },
    { id: 'analytics', label: 'Analytics' },
    { id: 'ai', label: 'AI Suggest' },
  ]
  return (
    <div className="p-6 space-y-4">
      <h2 className="text-2xl font-semibold text-slate-800">Scale & Intelligence</h2>
      <div className="flex gap-2 border-b pb-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-1 text-sm capitalize ${
              tab === t.id
                ? 'border-b-2 border-indigo-600 font-medium text-slate-800'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'drift' && <Drift />}
      {tab === 'freshness' && <Freshness />}
      {tab === 'scheduler' && <Scheduler />}
      {tab === 'analytics' && <Analytics />}
      {tab === 'ai' && <AiSuggest />}
    </div>
  )
}

function useList<T>(path: string, deps: unknown[] = []) {
  const [items, setItems] = useState<T[]>([])
  const [error, setError] = useState('')
  const load = () =>
    apiGet(path)
      .then((data) => setItems(data || []))
      .catch((e) => setError(e.message))
  useEffect(() => {
    load()
  }, deps)
  return { items, error, load }
}

function Drift() {
  const { items, error, load } = useList<any>('/v1/drift')
  const [integrations, setIntegrations] = useState<any[]>([])
  const [selected, setSelected] = useState('')
  const [running, setRunning] = useState(false)

  useEffect(() => {
    apiGet('/v1/integrations').then(setIntegrations).catch(() => {})
  }, [])

  const detect = async () => {
    if (!selected) return
    setRunning(true)
    await apiPost(`/v1/drift/detect?integration_id=${encodeURIComponent(selected)}`)
    setRunning(false)
    load()
  }

  const ack = async (id: string) => {
    await apiPost(`/v1/drift/${id}/acknowledge`)
    load()
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-red-600">{error}</p>}
      <div className="bg-white rounded-lg shadow p-4 space-y-2">
        <h3 className="font-medium text-slate-800">Run Drift Detection</h3>
        <select value={selected} onChange={(e) => setSelected(e.target.value)} className="border rounded px-3 py-2 text-sm w-full">
          <option value="">Select integration</option>
          {integrations.map((i) => (
            <option key={i.id} value={i.id}>{i.name} ({i.connector})</option>
          ))}
        </select>
        <button onClick={detect} disabled={running || !selected} className="px-3 py-1 bg-indigo-600 text-white rounded text-sm disabled:opacity-50">Run</button>
      </div>
      <table className="w-full text-sm bg-white rounded-lg shadow overflow-hidden">
        <thead className="bg-slate-100">
          <tr><th className="p-3 text-left">Type</th><th className="p-3 text-left">Resource</th><th className="p-3 text-left">Severity</th><th className="p-3 text-left">Ack</th></tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.id} className="border-b last:border-b-0">
              <td className="p-3 capitalize">{d.drift_type}</td>
              <td className="p-3">{d.resource_type} — {d.external_id}</td>
              <td className="p-3">{d.severity}</td>
              <td className="p-3">
                {d.acknowledged ? 'Yes' : <button onClick={() => ack(d.id)} className="text-indigo-600 text-xs">Ack</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Freshness() {
  const { items, error, load } = useList<any>('/v1/evidence/stale/list')
  const [hours, setHours] = useState('48')

  const recollectTest = async (testId: string) => {
    await apiPost(`/v1/evidence/recollect?test_id=${encodeURIComponent(testId)}`)
    load()
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-red-600">{error}</p>}
      <div className="bg-white rounded-lg shadow p-4 flex gap-2 items-center">
        <label className="text-sm text-slate-600">Stale threshold (hours)</label>
        <input value={hours} onChange={(e) => setHours(e.target.value)} className="border rounded px-2 py-1 text-sm w-20" />
        <button onClick={() => load()} className="px-3 py-1 bg-indigo-600 text-white rounded text-sm">Refresh</button>
      </div>
      <table className="w-full text-sm bg-white rounded-lg shadow overflow-hidden">
        <thead className="bg-slate-100">
          <tr><th className="p-3 text-left">Test</th><th className="p-3 text-left">Type</th><th className="p-3 text-left">Collected</th><th className="p-3 text-left">Action</th></tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.id} className="border-b last:border-b-0">
              <td className="p-3">{e.test_name || '-'}</td>
              <td className="p-3">{e.evidence_type}</td>
              <td className="p-3">{e.collected_at ? new Date(e.collected_at).toLocaleString() : '-'}</td>
              <td className="p-3">
                <button onClick={() => recollectTest(e.test_name ? 'any' : '')} className="text-indigo-600 text-xs">Recollect</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Scheduler() {
  const [jobs, setJobs] = useState<{ integrations: any[]; tests: any[] }>({ integrations: [], tests: [] })
  const [error, setError] = useState('')
  const load = () => apiGet('/v1/scheduler/jobs').then(setJobs).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const trigger = async (type: string, id: string) => {
    await apiPost(`/v1/scheduler/trigger/${type}/${id}`)
    load()
  }

  const tick = async () => {
    await apiPost('/v1/scheduler/tick')
    load()
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-red-600">{error}</p>}
      <div className="bg-white rounded-lg shadow p-4">
        <button onClick={tick} className="px-3 py-1 bg-indigo-600 text-white rounded text-sm">Run Due Jobs Now</button>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-medium text-slate-800 mb-2">Integrations</h3>
          <ul className="space-y-2 text-sm">
            {jobs.integrations.map((j) => (
              <li key={j.id} className="border-b last:border-b-0 pb-2 flex justify-between items-center">
                <span>{j.name} — next: {j.next_run_at ? new Date(j.next_run_at).toLocaleString() : '-'}</span>
                <button onClick={() => trigger('integration', j.id)} className="px-2 py-1 text-xs bg-slate-600 text-white rounded">Run</button>
              </li>
            ))}
          </ul>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-medium text-slate-800 mb-2">Tests</h3>
          <ul className="space-y-2 text-sm">
            {jobs.tests.map((j) => (
              <li key={j.id} className="border-b last:border-b-0 pb-2 flex justify-between items-center">
                <span>{j.name} ({j.resource_type}) — next: {j.next_run_at ? new Date(j.next_run_at).toLocaleString() : '-'}</span>
                <button onClick={() => trigger('test', j.id)} className="px-2 py-1 text-xs bg-slate-600 text-white rounded">Run</button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

function Analytics() {
  const [history, setHistory] = useState<any[]>([])
  const [trend, setTrend] = useState<any[]>([])
  const [snapshot, setSnapshot] = useState<any>(null)
  const [error, setError] = useState('')

  const load = () => {
    apiGet('/v1/analytics/posture').then(setHistory).catch((e) => setError(e.message))
    apiGet('/v1/analytics/trend').then((d) => setTrend(d.trend || [])).catch(() => {})
  }
  useEffect(() => { load() }, [])

  const takeSnapshot = async () => {
    const data = await apiPost('/v1/analytics/posture')
    setSnapshot(data)
    load()
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-red-600">{error}</p>}
      <div className="bg-white rounded-lg shadow p-4 space-y-2">
        <button onClick={takeSnapshot} className="px-3 py-1 bg-indigo-600 text-white rounded text-sm">Snapshot Posture</button>
        {snapshot && (
          <p className="text-sm text-slate-600">Readiness: {snapshot.overall_readiness_pct}% ({snapshot.overall_ok}/{snapshot.overall_controls})</p>
        )}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-medium text-slate-800 mb-2">Posture History</h3>
          <ul className="space-y-2 text-sm max-h-64 overflow-auto">
            {history.map((h) => (
              <li key={h.id} className="border-b last:border-b-0 pb-2">
                {new Date(h.recorded_at).toLocaleDateString()} — {h.readiness_pct}% OK ({h.ok_controls}/{h.total_controls})
              </li>
            ))}
          </ul>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-medium text-slate-800 mb-2">Control Trend</h3>
          <ul className="space-y-2 text-sm max-h-64 overflow-auto">
            {trend.map((t, i) => (
              <li key={i} className="border-b last:border-b-0 pb-2">
                {new Date(t.day).toLocaleDateString()} — {t.status}: {t.count}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

function AiSuggest() {
  const [finding, setFinding] = useState('')
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const ask = async () => {
    if (!finding) return
    setLoading(true)
    const data = await apiPost(`/v1/ai/suggest-remediation?finding=${encodeURIComponent(finding)}`)
    setResult(data)
    setLoading(false)
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-lg shadow p-4 space-y-2">
        <textarea value={finding} onChange={(e) => setFinding(e.target.value)} rows={3} placeholder="Describe the finding..." className="w-full border rounded px-3 py-2 text-sm" />
        <button onClick={ask} disabled={loading} className="px-3 py-1 bg-indigo-600 text-white rounded text-sm disabled:opacity-50">Suggest</button>
      </div>
      {result && (
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-medium text-slate-800 mb-2">Suggestions ({result.model})</h3>
          <ul className="list-disc pl-5 space-y-1 text-sm text-slate-700">
            {result.suggestions.map((s: string, i: number) => (<li key={i}>{s}</li>))}
          </ul>
        </div>
      )}
    </div>
  )
}
