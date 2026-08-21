import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '../lib/api'

export default function ControlsPage() {
  const [controls, setControls] = useState<any[]>([])
  const [frameworks, setFrameworks] = useState<any[]>([])
  const [selectedFw, setSelectedFw] = useState('SOC2')
  const [error, setError] = useState('')
  const [form, setForm] = useState({ code: '', statement: '', domain: '', framework: 'SOC2' })

  const load = () => {
    apiGet('/v1/controls').then(setControls).catch((e) => setError(e.message))
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    apiGet(`/v1/frameworks/${selectedFw}/controls`).then(setFrameworks).catch((e) => setError(e.message))
  }, [selectedFw])

  const create = async () => {
    try {
      const params = new URLSearchParams({
        code: form.code,
        statement: form.statement,
        owner_email: 'alice@example.com',
        domain: form.domain,
        framework_code: form.framework,
        requirement_text: `Mapped to ${form.framework}`,
      })
      await apiPost(`/v1/controls?${params.toString()}`)
      setForm({ code: '', statement: '', domain: '', framework: 'SOC2' })
      load()
    } catch (e: any) {
      setError(e.message)
    }
  }

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-semibold text-slate-800">Controls</h2>
      {error && <p className="text-red-600">{error}</p>}
      <div className="bg-white rounded-lg shadow p-4 space-y-3">
        <h3 className="font-medium text-slate-800">Create Custom Control</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
            placeholder="Code"
            className="border rounded px-3 py-2 text-sm"
          />
          <input
            value={form.statement}
            onChange={(e) => setForm({ ...form, statement: e.target.value })}
            placeholder="Statement"
            className="border rounded px-3 py-2 text-sm"
          />
          <input
            value={form.domain}
            onChange={(e) => setForm({ ...form, domain: e.target.value })}
            placeholder="Domain"
            className="border rounded px-3 py-2 text-sm"
          />
          <select
            value={form.framework}
            onChange={(e) => setForm({ ...form, framework: e.target.value })}
            className="border rounded px-3 py-2 text-sm"
          >
            <option>SOC2</option>
            <option>ISO27001</option>
            <option>GDPR</option>
            <option>HIPAA</option>
          </select>
        </div>
        <button onClick={create} className="px-4 py-2 bg-indigo-600 text-white rounded text-sm hover:bg-indigo-700">
          Create Control
        </button>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-medium mb-2 text-slate-800">All Controls</h3>
          <ul className="space-y-2 text-sm">
            {controls.map((c) => (
              <li key={c.id} className="border-b last:border-b-0 pb-2">
                <span className="font-semibold text-slate-800">{c.code}</span>{' '}
                <span className="text-slate-600">{c.statement}</span>{' '}
                <span className="text-slate-500">({c.status})</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="font-medium text-slate-800">Framework</h3>
            <select
              value={selectedFw}
              onChange={(e) => setSelectedFw(e.target.value)}
              className="border rounded px-2 py-1 text-sm"
            >
              <option>SOC2</option>
              <option>ISO27001</option>
              <option>GDPR</option>
              <option>HIPAA</option>
            </select>
          </div>
          <ul className="space-y-2 text-sm">
            {frameworks.map((f) => (
              <li key={f.mapping_id || f.id} className="border-b last:border-b-0 pb-2">
                <span className="font-semibold text-slate-800">{f.code}</span>{' '}
                <span className="text-slate-600">{f.requirement_text}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
