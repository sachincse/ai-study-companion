import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Layers, ListChecks, MessageSquare, MonitorPlay } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Badge, Card, PageHeader, ProgressBar, Spinner } from '../components/ui'
import { api, errorMessage } from '../lib/api'
import { useInvalidate } from '../lib/hooks'
import type { SubjectDetail } from '../lib/types'

export function SubjectPage() {
  const { subjectId } = useParams()
  const navigate = useNavigate()
  const invalidate = useInvalidate()
  const { data, isLoading } = useQuery({ queryKey: ['subject', subjectId], queryFn: () => api<SubjectDetail>(`/api/v1/syllabus/subjects/${subjectId}`) })
  const toggle = useMutation({
    mutationFn: ({ id, completed }: { id: number; completed: boolean }) => api(`/api/v1/syllabus/topics/${id}/progress`, { body: { completed } }),
    onSuccess: () => invalidate('subject', 'subjects', 'dashboard'),
    onError: (err) => toast.error(errorMessage(err)),
  })
  if (isLoading || !data) return <Spinner label="Loading subject..." />
  const unitTopic = (u: { number: number; title: string }) => `${data.name} Unit ${u.number}: ${u.title}`

  return (
    <div className="space-y-5 animate-fade-up">
      <Link to="/syllabus" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-brand-700">
        <ArrowLeft className="h-4 w-4" /> All subjects
      </Link>
      <PageHeader title={`${data.code} ${data.name}`} subtitle={`Semester ${data.semester} · ${data.credits ?? '-'} credits · ${data.completed_count}/${data.topic_count} topics done`} />
      <ProgressBar value={data.percent} tone="mint" className="max-w-xl" />
      <div className="space-y-4">
        {data.units.map((u) => {
          const done = u.topics.filter((t) => t.completed).length
          return (
            <Card key={u.number}>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Badge tone="brand">Unit {u.number}</Badge>
                <h3 className="font-bold text-ink-900">{u.title}</h3>
                <span className="text-xs text-slate-500">
                  {done}/{u.topics.length}
                </span>
                <div className="ml-auto flex flex-wrap gap-1.5">
                  <button className="btn-secondary btn-sm" onClick={() => navigate('/tutor', { state: { topic: unitTopic(u) } })}>
                    <MessageSquare className="h-3.5 w-3.5" /> Ask
                  </button>
                  <button className="btn-secondary btn-sm" onClick={() => navigate('/quizzes', { state: { topic: unitTopic(u), subject_id: data.id } })}>
                    <ListChecks className="h-3.5 w-3.5" /> Quiz
                  </button>
                  <button className="btn-secondary btn-sm" onClick={() => navigate('/revision?tab=flashcards', { state: { topic: unitTopic(u), subject_id: data.id } })}>
                    <Layers className="h-3.5 w-3.5" /> Cards
                  </button>
                  <button className="btn-secondary btn-sm" onClick={() => navigate(`/lectures?subject_id=${data.id}&topic=${encodeURIComponent(u.title)}`)}>
                    <MonitorPlay className="h-3.5 w-3.5" /> Lectures
                  </button>
                </div>
              </div>
              <ul className="grid gap-1 sm:grid-cols-2">
                {u.topics.map((t) => (
                  <li key={t.id}>
                    <label className="flex cursor-pointer items-start gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-slate-50">
                      <input type="checkbox" className="mt-0.5 h-4 w-4 rounded border-slate-300" checked={t.completed} onChange={() => toggle.mutate({ id: t.id, completed: !t.completed })} />
                      <span className={t.completed ? 'text-slate-400 line-through' : 'text-slate-700'}>{t.name}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
