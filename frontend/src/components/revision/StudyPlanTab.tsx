import { useMutation } from '@tanstack/react-query'
import { CalendarDays, Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { api, errorMessage } from '../../lib/api'
import { useInvalidate, useSubjects } from '../../lib/hooks'
import type { Artifact, StudyPlan } from '../../lib/types'
import { cn, formatDate, localDateKey } from '../../lib/utils'
import { Badge, Card, Field, Modal, ProgressBar, Spinner } from '../ui'
import { ArtifactList, useArtifacts } from './ArtifactTabs'

const TYPE_TONE: Record<string, 'brand' | 'mint' | 'amber' | 'plum' | 'sky'> = { read: 'sky', quiz: 'amber', flashcards: 'plum', practice: 'brand', revise: 'mint' }

export function StudyPlanTab() {
  const invalidate = useInvalidate()
  const { data } = useArtifacts<StudyPlan>('study_plan')
  const { data: subjects } = useSubjects()
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)
  const [examDate, setExamDate] = useState('')
  const [subjectIds, setSubjectIds] = useState<number[]>([])
  const [minutes, setMinutes] = useState(120)
  const [focus, setFocus] = useState('')

  const generate = useMutation({
    mutationFn: () => api<Artifact<StudyPlan>>('/api/v1/tools/study-plan', { body: { exam_date: examDate, subject_ids: subjectIds, daily_minutes: minutes, focus: focus || null } }),
    onSuccess: (a) => {
      setOpen(false)
      setSelected(a.id)
      invalidate('artifacts', 'dashboard')
    },
    onError: (err) => toast.error(errorMessage(err)),
  })
  const update = useMutation({
    mutationFn: ({ id, content }: { id: number; content: StudyPlan }) => api<Artifact<StudyPlan>>(`/api/v1/tools/artifacts/${id}`, { method: 'PATCH', body: { content } }),
    onSuccess: () => invalidate('artifacts'),
  })

  const active = data?.find((a) => a.id === selected) ?? data?.[0]
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!examDate || !subjectIds.length) {
      toast.error('Pick an exam date and at least one subject')
      return
    }
    generate.mutate()
  }
  const toggleTask = (dayIdx: number, taskIdx: number) => {
    if (!active) return
    const content: StudyPlan = { ...active.content, days: active.content.days.map((d, i) => (i === dayIdx ? { ...d, tasks: d.tasks.map((t, j) => (j === taskIdx ? { ...t, done: !t.done } : t)) } : d)) }
    update.mutate({ id: active.id, content })
  }
  const total = active?.content.days.reduce((n, d) => n + d.tasks.length, 0) ?? 0
  const done = active?.content.days.reduce((n, d) => n + d.tasks.filter((t) => t.done).length, 0) ?? 0
  const today = localDateKey()

  return (
    <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
      <div className="space-y-3">
        <button className="btn-primary w-full" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> New study plan
        </button>
        <ArtifactList kind="study_plan" items={data} selected={active?.id ?? null} onSelect={setSelected} emptyTitle="No study plan yet" emptyDescription="A day-by-day revision schedule built from the AKTU syllabus, your weak topics and the time you have." onNew={() => setOpen(true)} renderMeta={(a) => `Exam ${formatDate(a.content.exam_date)} · ${a.content.days.length} days`} />
      </div>
      <Card>
        {active ? (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-50 text-brand-600">
                <CalendarDays className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="text-lg font-bold text-ink-900">{active.title}</h3>
                <p className="text-xs text-slate-500">
                  Exam on {formatDate(active.content.exam_date, { day: 'numeric', month: 'long' })} · {active.content.daily_minutes} min/day · {active.content.subjects.map((s) => s.code).join(', ')}
                </p>
              </div>
              <div className="w-40">
                <ProgressBar value={total ? (done / total) * 100 : 0} tone="mint" />
                <div className="mt-1 text-right text-[11px] text-slate-500">
                  {done}/{total} tasks done
                </div>
              </div>
            </div>
            <div className="space-y-3">
              {active.content.days.map((d, di) => (
                <div key={d.date + di} className={cn('rounded-xl border p-3', d.date === today ? 'border-brand-300 bg-brand-50/40' : 'border-slate-200')}>
                  <div className="mb-2 flex items-center gap-2 text-sm">
                    <span className="font-bold text-ink-900">{formatDate(d.date, { weekday: 'short', day: 'numeric', month: 'short' })}</span>
                    {d.date === today && <Badge tone="brand">today</Badge>}
                    <span className="truncate text-slate-500">{d.focus}</span>
                  </div>
                  <ul className="space-y-1.5">
                    {d.tasks.map((t, ti) => (
                      <li key={ti}>
                        <label className="flex cursor-pointer items-center gap-2 text-sm">
                          <input type="checkbox" checked={t.done} onChange={() => toggleTask(di, ti)} className="h-4 w-4 rounded border-slate-300 text-brand-600" />
                          <span className={cn(t.done && 'text-slate-400 line-through')}>{t.title}</span>
                          <Badge tone={TYPE_TONE[t.type] ?? 'slate'}>{t.type}</Badge>
                          {t.subject && <span className="text-xs text-slate-400">{t.subject}</span>}
                          <span className="ml-auto text-xs text-slate-400">{t.minutes} min</span>
                        </label>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
            {active.content.tips.length > 0 && (
              <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-slate-600">
                {active.content.tips.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p className="text-sm text-slate-500">Select or generate a study plan.</p>
        )}
      </Card>
      <Modal open={open} onClose={() => !generate.isPending && setOpen(false)} title="Plan my revision">
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Exam date">
              <input type="date" className="input" value={examDate} min={today} onChange={(e) => setExamDate(e.target.value)} required />
            </Field>
            <Field label="Minutes per day">
              <input type="number" className="input" min={30} max={720} step={15} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} />
            </Field>
          </div>
          <Field label="Subjects">
            <div className="max-h-48 space-y-1 overflow-y-auto rounded-xl border border-slate-200 p-2">
              {(subjects ?? []).map((s) => (
                <label key={s.id} className="flex items-center gap-2 rounded-lg px-2 py-1 text-sm hover:bg-slate-50">
                  <input type="checkbox" checked={subjectIds.includes(s.id)} onChange={() => setSubjectIds((ids) => (ids.includes(s.id) ? ids.filter((x) => x !== s.id) : [...ids, s.id]))} className="h-4 w-4 rounded border-slate-300" />
                  <span className="font-mono text-xs text-slate-500">{s.code}</span> {s.name}
                </label>
              ))}
            </div>
          </Field>
          <Field label="Extra focus (optional)">
            <input className="input" value={focus} onChange={(e) => setFocus(e.target.value)} placeholder="e.g. numericals in COA, previous-year questions" />
          </Field>
          <div className="flex justify-end">
            <button className="btn-primary" type="submit" disabled={generate.isPending}>
              {generate.isPending ? <Spinner label="Planning..." className="text-white" /> : 'Create plan'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
