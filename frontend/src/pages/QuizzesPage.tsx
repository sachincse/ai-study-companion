import { useMutation, useQuery } from '@tanstack/react-query'
import { Clock, ListChecks, Play, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { DocumentPicker, SubjectSelect } from '../components/pickers'
import { Badge, Card, EmptyState, Field, Modal, PageHeader, Spinner } from '../components/ui'
import { api, errorMessage } from '../lib/api'
import { useInvalidate } from '../lib/hooks'
import type { AttemptHistoryItem, Quiz, QuizSummary } from '../lib/types'
import { formatDateTime, pct, timeAgo } from '../lib/utils'

const TYPE_LABELS: Record<string, string> = { mcq: 'Multiple choice', true_false: 'True / false', short_answer: 'Short answer (AI graded)' }

export function QuizzesPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const invalidate = useInvalidate()
  const state = (location.state as { topic?: string; document_ids?: number[]; subject_id?: number } | null) ?? null
  const [open, setOpen] = useState(Boolean(state?.topic))
  const [topic, setTopic] = useState(state?.topic ?? '')
  const [docIds, setDocIds] = useState<number[]>(state?.document_ids ?? [])
  const [subjectId, setSubjectId] = useState<number | ''>(state?.subject_id ?? '')
  const [count, setCount] = useState(8)
  const [difficulty, setDifficulty] = useState('medium')
  const [types, setTypes] = useState<string[]>(['mcq', 'true_false', 'short_answer'])
  const [timeLimit, setTimeLimit] = useState('0')

  useEffect(() => {
    if (state?.topic) {
      setTopic(state.topic)
      setOpen(true)
    }
  }, [state])

  const quizzes = useQuery({ queryKey: ['quizzes'], queryFn: () => api<QuizSummary[]>('/api/v1/quizzes') })
  const attempts = useQuery({ queryKey: ['attempts'], queryFn: () => api<AttemptHistoryItem[]>('/api/v1/quizzes/attempts') })

  const generate = useMutation({
    mutationFn: () =>
      api<Quiz>('/api/v1/quizzes/generate', {
        body: { topic: topic.trim() || null, document_ids: docIds.length ? docIds : null, subject_id: subjectId || null, count, difficulty, types, time_limit_sec: Number(timeLimit) || null },
      }),
    onSuccess: (quiz) => {
      invalidate('quizzes', 'dashboard')
      setOpen(false)
      toast.success(`Quiz ready: ${quiz.question_count} questions`)
      navigate(`/quizzes/${quiz.id}`)
    },
    onError: (err) => toast.error(errorMessage(err)),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api(`/api/v1/quizzes/${id}`, { method: 'DELETE' }),
    onSuccess: () => invalidate('quizzes', 'attempts', 'dashboard'),
    onError: (err) => toast.error(errorMessage(err)),
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!topic.trim() && !docIds.length) {
      toast.error('Give a topic or pick at least one document')
      return
    }
    generate.mutate()
  }

  return (
    <div className="space-y-6 animate-fade-up">
      <PageHeader
        title="Quizzes & Grading"
        subtitle="Generate practice tests from your notes or any syllabus topic. Objective questions are auto-graded; descriptive answers are graded against a rubric."
        actions={
          <button className="btn-primary" onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" /> New quiz
          </button>
        }
      />

      {quizzes.isLoading ? (
        <Spinner label="Loading quizzes..." />
      ) : !quizzes.data?.length ? (
        <EmptyState icon={<ListChecks className="h-5 w-5" />} title="No quizzes yet" description="Create your first quiz from a topic or from the notes you uploaded." action={<button className="btn-primary" onClick={() => setOpen(true)}>Generate a quiz</button>} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {quizzes.data.map((q) => (
            <Card key={q.id} className="flex flex-col">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="truncate font-bold text-ink-900" title={q.title}>
                    {q.title}
                  </h3>
                  <p className="truncate text-xs text-slate-500">{q.topic ?? 'From your notes'}</p>
                </div>
                <Badge tone={q.difficulty === 'hard' ? 'rose' : q.difficulty === 'easy' ? 'mint' : 'amber'}>{q.difficulty}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                <span>{q.question_count} questions</span>
                {q.time_limit_sec && (
                  <span className="inline-flex items-center gap-1">
                    <Clock className="h-3 w-3" /> {Math.round(q.time_limit_sec / 60)} min
                  </span>
                )}
                <span>· {timeAgo(q.created_at)}</span>
              </div>
              <div className="mt-3 flex items-center gap-3 text-sm">
                <span className="text-slate-500">{q.attempt_count} attempt{q.attempt_count === 1 ? '' : 's'}</span>
                {q.best_percent !== null && <Badge tone={q.best_percent >= 80 ? 'mint' : q.best_percent >= 60 ? 'amber' : 'rose'}>best {pct(q.best_percent)}</Badge>}
              </div>
              <div className="mt-4 flex gap-2">
                <Link to={`/quizzes/${q.id}`} className="btn-primary btn-sm flex-1">
                  {q.attempt_count ? <RotateCcw className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />} {q.attempt_count ? 'Retake' : 'Start'}
                </Link>
                <button className="btn-ghost btn-sm text-rose-600" onClick={() => confirm('Delete this quiz and its attempts?') && remove.mutate(q.id)} title="Delete">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {attempts.data && attempts.data.length > 0 && (
        <Card title="Attempt history" subtitle="Open any attempt to review explanations">
          <ul className="divide-y divide-slate-100">
            {attempts.data.map((a) => (
              <li key={a.attempt_id} className="flex items-center gap-3 py-2.5 text-sm">
                <Link to={`/quizzes/attempts/${a.attempt_id}`} className="font-medium text-ink-900 hover:text-brand-700">
                  {a.title}
                </Link>
                <span className="text-xs text-slate-400">{formatDateTime(a.submitted_at)}</span>
                <span className="ml-auto font-mono text-xs text-slate-600">
                  {a.score}/{a.max_score}
                </span>
                <Badge tone={a.percent >= 80 ? 'mint' : a.percent >= 60 ? 'amber' : 'rose'}>{pct(a.percent)}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Modal open={open} onClose={() => !generate.isPending && setOpen(false)} title="Generate a quiz">
        <form onSubmit={submit} className="space-y-4">
          <Field label="Topic" hint="Leave empty to quiz across the selected documents">
            <input className="input" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. CPU scheduling algorithms" />
          </Field>
          <Field label="Subject (optional)">
            <SubjectSelect value={subjectId} onChange={setSubjectId} />
          </Field>
          <Field label="Ground in these notes">
            <DocumentPicker value={docIds} onChange={setDocIds} compact />
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Questions">
              <select className="input" value={count} onChange={(e) => setCount(Number(e.target.value))}>
                {[5, 8, 10, 15, 20].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Difficulty">
              <select className="input" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </Field>
            <Field label="Timer">
              <select className="input" value={timeLimit} onChange={(e) => setTimeLimit(e.target.value)}>
                <option value="0">None</option>
                <option value="300">5 min</option>
                <option value="600">10 min</option>
                <option value="900">15 min</option>
                <option value="1800">30 min</option>
              </select>
            </Field>
          </div>
          <Field label="Question types">
            <div className="flex flex-wrap gap-2">
              {Object.entries(TYPE_LABELS).map(([id, label]) => {
                const on = types.includes(id)
                return (
                  <button type="button" key={id} onClick={() => setTypes((t) => (on ? t.filter((x) => x !== id) : [...t, id]))} className={on ? 'chip bg-brand-50 text-brand-700 border border-brand-200' : 'chip bg-white text-slate-500 border border-slate-200'}>
                    {label}
                  </button>
                )
              })}
            </div>
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)} disabled={generate.isPending}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={generate.isPending || types.length === 0}>
              {generate.isPending ? <Spinner label="Generating..." className="text-white" /> : 'Generate quiz'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
