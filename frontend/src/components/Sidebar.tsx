import { LayoutDashboard, Plug, ShieldCheck, FileText, BookOpen, Workflow, BarChart3 } from 'lucide-react'

type Props = { page: string; onChange: (page: string) => void }

const items = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'integrations', label: 'Integrations', icon: Plug },
  { id: 'controls', label: 'Controls', icon: ShieldCheck },
  { id: 'evidence', label: 'Evidence', icon: FileText },
  { id: 'policies', label: 'Policies', icon: BookOpen },
  { id: 'workflows', label: 'Workflows', icon: Workflow },
  { id: 'intelligence', label: 'Intelligence', icon: BarChart3 },
]

export default function Sidebar({ page, onChange }: Props) {
  return (
    <aside className="w-64 min-h-screen bg-slate-900 text-white p-4 flex flex-col">
      <h1 className="text-xl font-semibold mb-8">Compliance</h1>
      <nav className="space-y-2">
        {items.map((item) => {
          const Icon = item.icon
          const active = page === item.id
          return (
            <button
              key={item.id}
              onClick={() => onChange(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-md transition text-left ${
                active ? 'bg-indigo-600' : 'hover:bg-slate-800'
              }`}
            >
              <Icon size={18} />
              {item.label}
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
