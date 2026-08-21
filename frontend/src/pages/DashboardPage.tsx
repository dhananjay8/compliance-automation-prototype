import { useEffect, useState } from 'react'
import { apiGet } from '../lib/api'
import { AlertCircle, CheckCircle, Shield } from 'lucide-react'

export default function DashboardPage() {
  const [posture, setPosture] = useState<any>(null)
  const [failures, setFailures] = useState<any[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    apiGet('/v1/dashboards/posture').then(setPosture).catch((e) => setError(e.message))
    apiGet('/v1/dashboards/failures').then(setFailures).catch((e) => setError(e.message))
  }, [])

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-semibold text-slate-800">Dashboard</h2>
      {error && <p className="text-red-600">{error}</p>}
      {posture && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card icon={<Shield />} label="Controls" value={posture.total_controls} />
          <Card icon={<CheckCircle />} label="Passing" value={posture.passing_controls} color="text-green-600" />
          <Card icon={<AlertCircle />} label="Failing" value={posture.failing_controls} color="text-red-600" />
          <Card icon={<CheckCircle />} label="With Evidence" value={posture.controls_with_evidence} />
        </div>
      )}
      <h3 className="text-lg font-medium text-slate-800">Latest Failures</h3>
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-100">
            <tr>
              <th className="p-3 text-left font-medium text-slate-600">Control</th>
              <th className="p-3 text-left font-medium text-slate-600">Reason</th>
              <th className="p-3 text-left font-medium text-slate-600">Status</th>
            </tr>
          </thead>
          <tbody>
            {failures.map((f) => (
              <tr key={f.id} className="border-b last:border-b-0">
                <td className="p-3">{f.control_code}</td>
                <td className="p-3">{f.reason}</td>
                <td className="p-3 text-red-600">{f.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Card({ icon, label, value, color }: any) {
  return (
    <div className="bg-white p-4 rounded-lg shadow flex items-center gap-4">
      <div className={color || 'text-indigo-600'}>{icon}</div>
      <div>
        <div className="text-2xl font-bold text-slate-800">{value ?? 0}</div>
        <div className="text-slate-500 text-sm">{label}</div>
      </div>
    </div>
  )
}
