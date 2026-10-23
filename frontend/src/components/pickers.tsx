import { FileText } from 'lucide-react'
import { useReadyDocuments, useSubjects } from '../lib/hooks'
import { cn } from '../lib/utils'

export function DocumentPicker({ value, onChange, compact }: { value: number[]; onChange: (ids: number[]) => void; compact?: boolean }) {
  const { data: docs } = useReadyDocuments()
  if (!docs.length) return <p className="text-xs text-slate-500">No indexed notes yet. Upload some in My Notes to ground answers in them.</p>
  const toggle = (id: number) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id])
  return (
    <div className={cn('flex flex-wrap gap-2', compact && 'max-h-28 overflow-y-auto')}>
      {docs.map((d) => {
        const active = value.includes(d.id)
        return (
          <button
            key={d.id}
            type="button"
            onClick={() => toggle(d.id)}
            className={cn(
              'inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors',
              active ? 'border-brand-300 bg-brand-50 text-brand-700' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50',
            )}
            title={d.title}
          >
            <FileText className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{d.title}</span>
          </button>
        )
      })}
      {value.length > 0 && (
        <button type="button" onClick={() => onChange([])} className="text-xs text-slate-500 underline">
          clear ({value.length})
        </button>
      )}
    </div>
  )
}

export function SubjectSelect({ value, onChange, allowEmpty = true, className }: { value: number | ''; onChange: (id: number | '') => void; allowEmpty?: boolean; className?: string }) {
  const { data: subjects } = useSubjects()
  return (
    <select className={cn('input', className)} value={value} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')}>
      {allowEmpty && <option value="">Any subject</option>}
      {(subjects ?? []).map((s) => (
        <option key={s.id} value={s.id}>
          {`${s.code} · ${s.name} (Sem ${s.semester})`}
        </option>
      ))}
    </select>
  )
}
