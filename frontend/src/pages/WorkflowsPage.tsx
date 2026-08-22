import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '../lib/api'

type Tab = 'remediations' | 'access' | 'vendors' | 'audits' | 'webhooks'

export default function WorkflowsPage() {
  const [tab, setTab] = useState<Tab>('remediations')
  const tabs: { id: Tab; label: string }[] = [
    { id: 'remediations', label: 'Remediations' },
    { id: 'access', label: 'Access Reviews' },
    { id: 'vendors', label: 'Vendors' },
    { id: 'audits', label: 'Audits' },
    { id: 'webhooks', label: 'Webhooks' },
  ]
  return (
    <div className="p-6 space-y-4">
      <h2 className="text-2xl font-semibold text-slate-800">Workflows & Audit Portal</h2>
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
      {tab === 'remediations' && <Remediations />}
      {tab === 'access' && <AccessReviews />}
      {tab === 'vendors' && <Vendors />}
      {tab === 'audits' && <Audits />}
      {tab === 'webhooks' && <Webhooks />}
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

function Remediations() {
  const { items, error, load } = useList<any>('/v1/remediations')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [ticket, setTicket] = useState('')

  const create = async () => {
    const params = new URLSearchParams({ title, description })
    await apiPost(`/v1/remediations?${params.toString()}`)
    setTitle('')
    setDescription('')
    load()
  }

  const setStatus = async (id: string, status: string) => {
    await apiPost(`/v1/remediations/${id}/status?status=${status}`)
    load()
  }

  const attachTicket = async (id: string) => {
    if (!ticket) return
    await apiPost(`/v1/remediations/${id}/ticket?ticket_id=${encodeURIComponent(ticket)}`)
    setTicket('')
    load()
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-red-600">{error}</p>}
      <div className="bg-white rounded-lg shadow p-4 space-y-2">
        <h3 className="font-medium text-slate-800">Create Remediation</h3>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" className="w-full border rounded px-3 py-2 text-sm" />
        <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" className="w-full border rounded px-3 py-2 text-sm" />
        <button onClick={create} className="px-3 py-1 bg-indigo-600 text-white rounded text-sm">Create</button>
      </div>
      <table className="w-full text-sm bg-white rounded-lg shadow overflow-hidden">
        <thead className="bg-slate-100">
          <tr><th className="p-3 text-left">Title</th><th className="p-3 text-left">Status</th><th className="p-3 text-left">Actions</th></tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.id} className="border-b last:border-b-0">
              <td className="p-3">{r.title}</td>
              <td className="p-3">{r.status}</td>
              <td className="p-3 space-x-1">
                <button onClick={() => setStatus(r.id, 'in_progress')} className="px-2 py-1 text-xs bg-blue-600 text-white rounded">Start</button>
                <button onClick={() => setStatus(r.id, 'resolved')} className="px-2 py-1 text-xs bg-green-600 text-white rounded">Resolve</button>
                <input onChange={(e) => setTicket(e.target.value)} placeholder="Ticket ID" className="border rounded px-2 py-1 text-xs w-24" />
                <button onClick={() => attachTicket(r.id)} className="px-2 py-1 text-xs bg-slate-600 text-white rounded">Attach</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AccessReviews() {
  const { items, error, load } = useList<any>('/v1/access-reviews')
  const [name, setName] = useState('')
  const [selected, setSelected] = useState<any>(null)
  const [userEmail, setUserEmail] = useState('')
  const [system, setSystem] = useState('')

  const create = async () => {
    await apiPost(`/v1/access-reviews?name=${encodeURIComponent(name)}`)
    setName('')
    load()
  }

  const loadItems = async (ar: any) => {
    const rows = await apiGet(`/v1/access-reviews/${ar.id}/items`)
    setSelected({ ...ar, items: rows || [] })
  }

  const addItem = async () => {
    if (!selected) return
    const params = new URLSearchParams({ user_email: userEmail, system })
    await apiPost(`/v1/access-reviews/${selected.id}/items?${params.toString()}`)
    setUserEmail('')
    setSystem('')
    loadItems(selected)
  }

  const decide = async (itemId: string, decision: string) => {
    if (!selected) return
    await apiPost(`/v1/access-reviews/${selected.id}/items/${itemId}/decide?decision=${decision}`)
    loadItems(selected)
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-red-600">{error}</p>}
      <div className="bg-white rounded-lg shadow p-4 space-y-2">
        <h3 className="font-medium text-slate-800">Create Access Review</h3>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="w-full border rounded px-3 py-2 text-sm" />
        <button onClick={create} className="px-3 py-1 bg-indigo-600 text-white rounded text-sm">Create</button>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-medium text-slate-800 mb-2">Campaigns</h3>
          <ul className="space-y-2 text-sm">
            {items.map((ar) => (
              <li key={ar.id} className="border-b last:border-b-0 pb-2 flex justify-between">
                <span>{ar.name} — {ar.status}</span>
                <button onClick={() => loadItems(ar)} className="text-indigo-600 text-xs">View</button>
              </li>
            ))}
          </ul>
        </div>
        {selected && (
          <div className="bg-white rounded-lg shadow p-4 space-y-2">
            <h3 className="font-medium text-slate-800">Items: {selected.name}</h3>
            <div className="flex gap-2">
              <input value={userEmail} onChange={(e) => setUserEmail(e.target.value)} placeholder="User email" className="border rounded px-2 py-1 text-sm flex-1" />
              <input value={system} onChange={(e) => setSystem(e.target.value)} placeholder="System" className="border rounded px-2 py-1 text-sm flex-1" />
              <button onClick={addItem} className="px-2 py-1 bg-indigo-600 text-white rounded text-xs">Add</button>
            </div>
            <ul className="space-y-2 text-sm">
              {(selected.items || []).map((item: any) => (
                <li key={item.id} className="border-b last:border-b-0 pb-2 flex justify-between items-center">
                  <span>{item.user_email || item.user_id} — {item.system} — {item.decision}</span>
                  <div className="space-x-1">
                    <button onClick={() => decide(item.id, 'approved')} className="px-2 py-1 text-xs bg-green-600 text-white rounded">Approve</button>
                    <button onClick={() => decide(item.id, 'revoked')} className="px-2 py-1 text-xs bg-red-600 text-white rounded">Revoke</button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

function Vendors() {
  const { items, error, load } = useList<any>('/v1/vendors')
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [risk, setRisk] = useState('medium')
  const [selected, setSelected] = useState<any>(null)
  const [questionnaire, setQuestionnaire] = useState('{"q1":""}')
  const [responses, setResponses] = useState('{"q1":""}')

  const create = async () => {
    const params = new URLSearchParams({ name, category, risk_level: risk })
    await apiPost(`/v1/vendors?${params.toString()}`)
    setName('')
    setCategory('')
    load()
  }

  const loadAssessments = async (v: any) => {
    const rows = await apiGet(`/v1/vendors/${v.id}/assessments`)
    setSelected({ ...v, assessments: rows || [] })
  }

  const createAssessment = async () => {
    if (!selected) return
    const params = new URLSearchParams({ questionnaire: JSON.stringify(JSON.parse(questionnaire)) })
    await apiPost(`/v1/vendors/${selected.id}/assessments?${params.toString()}`)
    loadAssessments(selected)
  }

  const respond = async (assessmentId: string) => {
    if (!selected) return
    const params = new URLSearchParams({ responses: JSON.stringify(JSON.parse(responses)) })
    await apiPost(`/v1/vendors/${selected.id}/assessments/${assessmentId}/respond?${params.toString()}`)
    loadAssessments(selected)
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-red-600">{error}</p>}
      <div className="bg-white rounded-lg shadow p-4 space-y-2">
        <h3 className="font-medium text-slate-800">Create Vendor</h3>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="w-full border rounded px-3 py-2 text-sm" />
        <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Category" className="w-full border rounded px-3 py-2 text-sm" />
        <select value={risk} onChange={(e) => setRisk(e.target.value)} className="border rounded px-3 py-2 text-sm">
          <option>low</option><option>medium</option><option>high</option><option>critical</option>
        </select>
        <button onClick={create} className="px-3 py-1 bg-indigo-600 text-white rounded text-sm">Create</button>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-medium text-slate-800 mb-2">Vendors</h3>
          <ul className="space-y-2 text-sm">
            {items.map((v) => (
              <li key={v.id} className="border-b last:border-b-0 pb-2 flex justify-between">
                <span>{v.name} — {v.risk_level}</span>
                <button onClick={() => loadAssessments(v)} className="text-indigo-600 text-xs">Assess</button>
              </li>
            ))}
          </ul>
        </div>
        {selected && (
          <div className="bg-white rounded-lg shadow p-4 space-y-2">
            <h3 className="font-medium text-slate-800">Assessments: {selected.name}</h3>
            <textarea value={questionnaire} onChange={(e) => setQuestionnaire(e.target.value)} rows={2} className="w-full border rounded px-3 py-2 text-sm" />
            <button onClick={createAssessment} className="px-2 py-1 bg-indigo-600 text-white rounded text-xs">Create Assessment</button>
            <ul className="space-y-2 text-sm">
              {(selected.assessments || []).map((a: any) => (
                <li key={a.id} className="border-b last:border-b-0 pb-2">
                  <div className="flex justify-between"><span>{a.status}</span></div>
                  {a.status === 'pending' && (
                    <div className="flex gap-2 mt-1">
                      <textarea value={responses} onChange={(e) => setResponses(e.target.value)} rows={1} className="flex-1 border rounded px-2 py-1 text-xs" />
                      <button onClick={() => respond(a.id)} className="px-2 py-1 bg-green-600 text-white rounded text-xs">Respond</button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

function Audits() {
  const { items, error, load } = useList<any>('/v1/audits')
  const [framework, setFramework] = useState('SOC2')
  const [selected, setSelected] = useState<any>(null)
  const [requestText, setRequestText] = useState('')
  const [responseText, setResponseText] = useState('')

  const create = async () => {
    const params = new URLSearchParams({ framework_code: framework })
    await apiPost(`/v1/audits?${params.toString()}`)
    load()
  }

  const loadRequests = async (a: any) => {
    const rows = await apiGet(`/v1/audits/${a.id}/requests`)
    setSelected({ ...a, requests: rows || [] })
  }

  const createRequest = async () => {
    if (!selected) return
    const params = new URLSearchParams({ request_text: requestText })
    await apiPost(`/v1/audits/${selected.id}/requests?${params.toString()}`)
    setRequestText('')
    loadRequests(selected)
  }

  const respond = async (reqId: string) => {
    if (!selected) return
    const params = new URLSearchParams({ response_text: responseText })
    await apiPost(`/v1/audits/${selected.id}/requests/${reqId}/respond?${params.toString()}`)
    setResponseText('')
    loadRequests(selected)
  }

  const setStatus = async (reqId: string, status: string) => {
    if (!selected) return
    await apiPost(`/v1/audits/${selected.id}/requests/${reqId}/status?status=${status}`)
    loadRequests(selected)
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-red-600">{error}</p>}
      <div className="bg-white rounded-lg shadow p-4 space-y-2">
        <h3 className="font-medium text-slate-800">Create Audit</h3>
        <select value={framework} onChange={(e) => setFramework(e.target.value)} className="border rounded px-3 py-2 text-sm">
          <option>SOC2</option><option>ISO27001</option><option>GDPR</option><option>HIPAA</option>
        </select>
        <button onClick={create} className="px-3 py-1 bg-indigo-600 text-white rounded text-sm">Create</button>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-medium text-slate-800 mb-2">Audits</h3>
          <ul className="space-y-2 text-sm">
            {items.map((a) => (
              <li key={a.id} className="border-b last:border-b-0 pb-2 flex justify-between">
                <span>{a.framework_code} — {a.status}</span>
                <button onClick={() => loadRequests(a)} className="text-indigo-600 text-xs">Requests</button>
              </li>
            ))}
          </ul>
        </div>
        {selected && (
          <div className="bg-white rounded-lg shadow p-4 space-y-2">
            <h3 className="font-medium text-slate-800">Requests: {selected.framework_code}</h3>
            <div className="flex gap-2">
              <input value={requestText} onChange={(e) => setRequestText(e.target.value)} placeholder="Request text" className="flex-1 border rounded px-2 py-1 text-sm" />
              <button onClick={createRequest} className="px-2 py-1 bg-indigo-600 text-white rounded text-xs">Add</button>
            </div>
            <ul className="space-y-2 text-sm">
              {(selected.requests || []).map((req: any) => (
                <li key={req.id} className="border-b last:border-b-0 pb-2">
                  <div className="flex justify-between"><span>{req.request_text} — {req.status}</span></div>
                  {req.status === 'open' && (
                    <div className="flex gap-2 mt-1">
                      <input value={responseText} onChange={(e) => setResponseText(e.target.value)} placeholder="Response" className="flex-1 border rounded px-2 py-1 text-xs" />
                      <button onClick={() => respond(req.id)} className="px-2 py-1 bg-green-600 text-white rounded text-xs">Respond</button>
                    </div>
                  )}
                  {req.status === 'responded' && (
                    <div className="space-x-1 mt-1">
                      <button onClick={() => setStatus(req.id, 'accepted')} className="px-2 py-1 text-xs bg-green-600 text-white rounded">Accept</button>
                      <button onClick={() => setStatus(req.id, 'flagged')} className="px-2 py-1 text-xs bg-red-600 text-white rounded">Flag</button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

function Webhooks() {
  const { items, error, load } = useList<any>('/v1/webhooks')
  const [url, setUrl] = useState('')
  const [events, setEvents] = useState('')
  const [selected, setSelected] = useState<any>(null)

  const create = async () => {
    const params = new URLSearchParams({ url, events })
    await apiPost(`/v1/webhooks?${params.toString()}`)
    setUrl('')
    setEvents('')
    load()
  }

  const loadDeliveries = async (h: any) => {
    const rows = await apiGet(`/v1/webhooks/${h.id}/deliveries`)
    setSelected({ ...h, deliveries: rows || [] })
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-red-600">{error}</p>}
      <div className="bg-white rounded-lg shadow p-4 space-y-2">
        <h3 className="font-medium text-slate-800">Create Webhook</h3>
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="URL" className="w-full border rounded px-3 py-2 text-sm" />
        <input value={events} onChange={(e) => setEvents(e.target.value)} placeholder="Events (comma separated)" className="w-full border rounded px-3 py-2 text-sm" />
        <button onClick={create} className="px-3 py-1 bg-indigo-600 text-white rounded text-sm">Create</button>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-medium text-slate-800 mb-2">Subscriptions</h3>
          <ul className="space-y-2 text-sm">
            {items.map((h) => (
              <li key={h.id} className="border-b last:border-b-0 pb-2 flex justify-between">
                <span>{h.url}</span>
                <button onClick={() => loadDeliveries(h)} className="text-indigo-600 text-xs">Deliveries</button>
              </li>
            ))}
          </ul>
        </div>
        {selected && (
          <div className="bg-white rounded-lg shadow p-4">
            <h3 className="font-medium text-slate-800 mb-2">Deliveries: {selected.url}</h3>
            <ul className="space-y-2 text-sm max-h-64 overflow-auto">
              {(selected.deliveries || []).map((d: any) => (
                <li key={d.id} className="border-b last:border-b-0 pb-2">
                  {d.event} — {d.status} {d.response_status ? `(${d.response_status})` : ''}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
