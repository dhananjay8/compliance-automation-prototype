import { useEffect, useRef, useState } from 'react'
import { apiGet } from '../lib/api'

export default function EvidencePage() {
  const [evidence, setEvidence] = useState<any[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const ref = useRef<HTMLInputElement>(null)

  const load = () => apiGet('/v1/evidence').then(setEvidence).catch((e) => setError(e.message))

  useEffect(() => { load() }, [])

  const upload = async () => {
    if (!file) return
    const form = new FormData()
    form.append('uploaded', file)
    const res = await fetch('/api/v1/evidence/upload', {
      method: 'POST',
      headers: {
        'X-Tenant-Id': import.meta.env.VITE_TENANT_ID || '00000000-0000-0000-0000-000000000001',
        'X-User-Id': import.meta.env.VITE_USER_ID || 'alice',
      },
      body: form,
    })
    if (!res.ok) {
      setError(`${res.status} ${res.statusText}`)
    } else {
      setFile(null)
      if (ref.current) ref.current.value = ''
      load()
    }
  }

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-semibold text-slate-800">Evidence</h2>
      {error && <p className="text-red-600">{error}</p>}
      <div className="bg-white rounded-lg shadow p-4 flex flex-col sm:flex-row items-center gap-4">
        <input
          ref={ref}
          type="file"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="text-sm"
        />
        <button
          onClick={upload}
          className="px-4 py-2 bg-indigo-600 text-white rounded text-sm hover:bg-indigo-700"
        >
          Upload File
        </button>
      </div>
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-100">
            <tr>
              <th className="p-3 text-left font-medium text-slate-600">Test</th>
              <th className="p-3 text-left font-medium text-slate-600">Type</th>
              <th className="p-3 text-left font-medium text-slate-600">Description</th>
              <th className="p-3 text-left font-medium text-slate-600">Status</th>
            </tr>
          </thead>
          <tbody>
            {evidence.map((e) => (
              <tr key={e.id} className="border-b last:border-b-0">
                <td className="p-3">{e.test_name}</td>
                <td className="p-3">{e.evidence_type}</td>
                <td className="p-3">{e.description}</td>
                <td className="p-3">{e.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
