import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Layers, MessageSquare, RotateCcw, XCircle } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Badge, Card, ErrorState, ProgressBar, Spinner } from '../components/ui'
import { api, errorMessage } from '../lib/api'
import type { AttemptResult } from '../lib/types'
import { cn, formatDuration } from '../lib/utils'

const LETTERS = 'ABCDEF'

function ScoreRing({ percent }: { percent: number }) {
  const r = 52
  const c = 2 * Math.PI * r
  const tone = percent >= 80 ? '#19764d' : percent >= 60 ? '#9a5a08' : '#a42c62'
  return (
    <svg viewBox="0 0 120 120" className="h-32 w-32">
      <circle cx="60" cy="60" r={r} fill="none" stroke="#e2e8f0" strokeWidth="10" />
      <circle cx="60" cy="60" r={r} fill="none" stroke={tone} strokeWidth="10" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - percent / 100)} transform="rotate(-90 60 60)" />
      <text x="60" y="66" textAnchor="middle" className="fill-ink-900" style={{ fontSize: 24, fontWeight: 800 }}>
        {percent.toFixed(0)}%
      </text>
    </svg>
  )
}

export function QuizResultPage() {
  const { attemptId } = useParams()
  const navigate = useNavigate()
  const { data, isLoading, isError, error } = useQuery({ queryKey: ['attempt', attemptId], queryFn: () => api<AttemptResult>(`/api/v1/quizzes/attempts/${attemptId}`) })
  if (isError) return <ErrorState message={errorMessage(error)} />
  if (isLoading || !data) return <Spinner label="Loading results..." />
  const answerFor = (qid: number) => data.answers.find((a) => a.question_id === qid)
  const breakdown = Object.entries(data.topic_breakdown ?? {}).sort((a, b) => a[1].percent - b[1].percent)

  return (
    <div className="mx-auto max-w-4xl space-y-5 animate-fade-up">
      <Card>
        <div className="flex flex-wrap items-center gap-6">
          <ScoreRing percent={data.percent} />
          <div className="min-w-0 flex-1">
            <h2 className="text-xl font-bold text-ink-900">{data.quiz_title}</h2>
            <p className="mt-1 text-sm text-slate-600">{data.feedback}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <Badge>
                {data.score}/{data.max_score} marks
              </Badge>
              {data.time_taken_sec !== null && <Badge>{formatDuration(data.time_taken_sec)}</Badge>}
              {data.weak_topics?.map((t) => (
                <Badge key={t} tone="rose">
                  revise: {t}
                </Badge>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn-primary btn-sm" onClick={() => navigate(`/quizzes/${data.quiz_id}`)}>
                <RotateCcw className="h-3.5 w-3.5" /> Retake
              </button>
              {data.weak_topics && data.weak_topics.length > 0 && (
                <>
                  <button className="btn-secondary btn-sm" onClick={() => navigate('/tutor', { state: { topic: data.weak_topics![0] } })}>
                    <MessageSquare className="h-3.5 w-3.5" /> Ask tutor about {data.weak_topics[0]}
                  </button>
                  <button className="btn-secondary btn-sm" onClick={() => navigate('/revision?tab=flashcards', { state: { topic: data.weak_topics!.join(', ') } })}>
                    <Layers className="h-3.5 w-3.5" /> Flashcards for weak topics
                  </button>
                </>
              )}
              <Link to="/quizzes" className="btn-ghost btn-sm">
                All quizzes
              </Link>
            </div>
          </div>
        </div>
      </Card>

      {breakdown.length > 1 && (
        <Card title="Topic breakdown">
          <ul className="space-y-3">
            {breakdown.map(([topic, s]) => (
              <li key={topic} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 sm:grid-cols-[200px_minmax(0,1fr)_auto]">
                <span className="truncate text-sm font-medium text-slate-700">{topic}</span>
                <ProgressBar value={s.percent} className="hidden sm:block" tone={s.percent < 60 ? 'rose' : s.percent < 80 ? 'amber' : 'mint'} />
                <span className="font-mono text-xs text-slate-600">
                  {s.marks}/{s.max_marks}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="space-y-3">
        {data.questions.map((q, i) => {
          const a = answerFor(q.id)
          const correct = a?.is_correct
          const yourAnswer = a?.answer
          const render = (v: string | null | undefined) => {
            if (!v) return <span className="text-slate-400">not answered</span>
            if (q.qtype === 'mcq' && q.options) {
              const idx = LETTERS.indexOf(v.toUpperCase()[0])
              return idx >= 0 ? `${LETTERS[idx]}. ${q.options[idx]}` : v
            }
            return v
          }
          return (
            <Card key={q.id} className={cn('border-l-4', correct ? 'border-l-mint-600' : a?.marks_awarded ? 'border-l-amber-600' : 'border-l-rose-600')}>
              <div className="flex items-start gap-3">
                <div className="mt-0.5">{correct ? <CheckCircle2 className="h-5 w-5 text-mint-600" /> : <XCircle className="h-5 w-5 text-rose-600" />}</div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span className="font-semibold text-ink-900">Q{i + 1}</span>
                    {q.topic && <span>{q.topic}</span>}
                    <span className="ml-auto font-mono">
                      {a?.marks_awarded ?? 0}/{q.marks}
                    </span>
                  </div>
                  <p className="mt-1 text-sm font-medium text-ink-900">{q.prompt}</p>
                  <div className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
                    <div className={cn('rounded-lg px-3 py-2', correct ? 'bg-mint-50' : 'bg-rose-50')}>
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Your answer</div>
                      <div>{render(yourAnswer)}</div>
                    </div>
                    <div className="rounded-lg bg-slate-50 px-3 py-2">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{q.qtype === 'short_answer' ? 'Model answer' : 'Correct answer'}</div>
                      <div>{render(q.answer_key)}</div>
                    </div>
                  </div>
                  {a?.ai_feedback && <p className="mt-2 rounded-lg border border-amber-50 bg-amber-50/60 px-3 py-2 text-sm text-amber-600">{a.ai_feedback}</p>}
                  {q.explanation && <p className="mt-2 text-sm text-slate-600">{q.explanation}</p>}
                  {q.qtype === 'short_answer' && q.options && q.options.length > 0 && (
                    <p className="mt-1 text-xs text-slate-500">Rubric: {q.options.join(' · ')}</p>
                  )}
                </div>
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
