import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '../lib/api'

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<any[]>([])
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [error, setError] = useState('')

  const load = () => apiGet('/v1/policies').then(setPolicies).catch((e) => setError(e.message))

  useEffect(() => { load() }, [])

  const create = async () => {
    try {
      const params = new URLSearchParams({
        title,
        content,
        version: '1.0',
      })
      await apiPost(`/v1/policies?${params.toString()}`)
      setTitle('')
      setContent('')
      load()
    } catch (e: any) {
      setError(e.message)
    }
  }

  const ack = async (id: string) => {
    try {
      await apiPost(`/v1/policies/${id}/acknowledge`)
      load()
    } catch (e: any) {
      setError(e.message)
    }
  }

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-semibold text-slate-800">Policies</h2>
      {error && <p className="text-red-600">{error}</p>}
      <div className="bg-white rounded-lg shadow p-4 space-y-3">
        <h3 className="font-medium text-slate-800">Create Policy</h3>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title"
          className="w-full border rounded px-3 py-2 text-sm"
        />
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Content"
          rows={3}
          className="w-full border rounded px-3 py-2 text-sm"
        />
        <button
          onClick={create}
          className="px-4 py-2 bg-indigo-600 text-white rounded text-sm hover:bg-indigo-700"
        >
          Create Policy
        </button>
      </div>
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-100">
            <tr>
              <th className="p-3 text-left font-medium text-slate-600">Title</th>
              <th className="p-3 text-left font-medium text-slate-600">Version</th>
              <th className="p-3 text-left font-medium text-slate-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((p) => (
              <tr key={p.id} className="border-b last:border-b-0">
                <td className="p-3">{p.title}</td>
                <td className="p-3">{p.version}</td>
                <td className="p-3">
                  <button
                    onClick={() => ack(p.id)}
                    className="px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700"
                  >
                    Acknowledge
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
