import { useMutation, useQuery } from '@tanstack/react-query'
import { Clock } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Badge, Card, ErrorState, Spinner } from '../components/ui'
import { api, errorMessage } from '../lib/api'
import { useInvalidate } from '../lib/hooks'
import type { Attempt, AttemptResult, Quiz } from '../lib/types'
import { cn, formatDuration } from '../lib/utils'

const LETTERS = 'ABCDEF'

export function QuizAttemptPage() {
  const { quizId } = useParams()
  const navigate = useNavigate()
  const invalidate = useInvalidate()
  const quiz = useQuery({ queryKey: ['quiz', quizId], queryFn: () => api<Quiz>(`/api/v1/quizzes/${quizId}`) })
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [current, setCurrent] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const startedRef = useRef(false)
  const autoSubmittedRef = useRef(false)

  const start = useMutation({
    mutationFn: () => api<Attempt>(`/api/v1/quizzes/${quizId}/attempts`, { method: 'POST' }),
    onSuccess: setAttempt,
    onError: (err) => toast.error(errorMessage(err)),
  })

  useEffect(() => {
    if (quiz.data && !startedRef.current) {
      startedRef.current = true
      start.mutate()
    }
  }, [quiz.data, start])

  useEffect(() => {
    if (!attempt) return
    const t = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [attempt])

  const submit = useMutation({
    mutationFn: () => api<AttemptResult>(`/api/v1/quizzes/attempts/${attempt!.id}/submit`, { body: { answers, time_taken_sec: elapsed } }),
    onSuccess: (result) => {
      invalidate('quizzes', 'attempts', 'dashboard')
      navigate(`/quizzes/attempts/${result.id}`, { replace: true })
    },
    onError: (err) => toast.error(errorMessage(err)),
  })

  const limit = quiz.data?.time_limit_sec ?? null
  const remaining = limit ? limit - elapsed : null
  useEffect(() => {
    if (remaining !== null && remaining <= 0 && attempt && !submit.isPending && !autoSubmittedRef.current) {
      autoSubmittedRef.current = true
      toast.message('Time is up - submitting your answers')
      submit.mutate()
    }
  }, [remaining, attempt, submit])

  if (quiz.isError) return <ErrorState message={errorMessage(quiz.error)} />
  if (start.isError) return <ErrorState message={errorMessage(start.error)} />
  if (quiz.isLoading || !quiz.data || !attempt) return <Spinner label="Preparing your quiz..." />
  const questions = quiz.data.questions
  const q = questions[current]
  const answered = questions.filter((x) => answers[x.id]?.trim()).length

  const confirmSubmit = () => {
    const missing = questions.length - answered
    if (missing > 0 && !confirm(`${missing} question${missing === 1 ? ' is' : 's are'} unanswered. Submit anyway?`)) return
    submit.mutate()
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 animate-fade-up">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-xl font-bold text-ink-900">{quiz.data.title}</h2>
          <p className="text-xs text-slate-500">
            {answered}/{questions.length} answered · {quiz.data.difficulty}
          </p>
        </div>
        <div className={cn('ml-auto inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 font-mono text-sm', remaining !== null && remaining < 60 ? 'border-rose-200 bg-rose-50 text-rose-600' : 'border-slate-200 bg-white text-slate-700')}>
          <Clock className="h-4 w-4" />
          {remaining !== null ? formatDuration(Math.max(0, remaining)) : formatDuration(elapsed)}
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {questions.map((x, i) => (
          <button
            key={x.id}
            onClick={() => setCurrent(i)}
            className={cn('h-8 w-8 rounded-lg text-xs font-semibold', i === current ? 'bg-brand-600 text-white' : answers[x.id]?.trim() ? 'bg-brand-50 text-brand-700' : 'bg-white text-slate-500 border border-slate-200')}
            aria-label={`Question ${i + 1}`}
          >
            {i + 1}
          </button>
        ))}
      </div>

      <Card>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <Badge tone="brand">Q{current + 1}</Badge>
          <Badge>{q.qtype === 'mcq' ? 'Multiple choice' : q.qtype === 'true_false' ? 'True / False' : 'Short answer'}</Badge>
          <Badge tone="amber">
            {q.marks} mark{q.marks === 1 ? '' : 's'}
          </Badge>
          {q.topic && <span className="text-slate-500">{q.topic}</span>}
        </div>
        <p className="text-base font-medium text-ink-900">{q.prompt}</p>
        <div className="mt-4 space-y-2">
          {q.qtype === 'short_answer' ? (
            <textarea className="input min-h-[120px]" value={answers[q.id] ?? ''} onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))} placeholder="Write your answer in 2-4 sentences. Key points earn partial marks." />
          ) : (
            (q.options ?? []).map((opt, i) => {
              const value = q.qtype === 'mcq' ? LETTERS[i] : opt
              const selected = answers[q.id] === value
              return (
                <button
                  key={opt}
                  type="button"
                  onClick={() => setAnswers((a) => ({ ...a, [q.id]: value }))}
                  className={cn('flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left text-sm transition-colors', selected ? 'border-brand-400 bg-brand-50 text-brand-800' : 'border-slate-200 bg-white hover:border-brand-200')}
                >
                  <span className={cn('grid h-6 w-6 shrink-0 place-items-center rounded-md text-xs font-bold', selected ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600')}>{q.qtype === 'mcq' ? LETTERS[i] : opt[0]}</span>
                  {opt}
                </button>
              )
            })
          )}
        </div>
        <div className="mt-5 flex items-center justify-between">
          <button className="btn-secondary" onClick={() => setCurrent((c) => Math.max(0, c - 1))} disabled={current === 0}>
            Previous
          </button>
          {current < questions.length - 1 ? (
            <button className="btn-primary" onClick={() => setCurrent((c) => c + 1)}>
              Next
            </button>
          ) : (
            <button className="btn-primary" onClick={confirmSubmit} disabled={submit.isPending}>
              {submit.isPending ? 'Grading...' : 'Submit quiz'}
            </button>
          )}
        </div>
      </Card>
      {current < questions.length - 1 && (
        <div className="text-right">
          <button className="text-xs font-semibold text-slate-500 hover:text-brand-700" onClick={confirmSubmit} disabled={submit.isPending}>
            Submit now
          </button>
        </div>
      )}
    </div>
  )
}
