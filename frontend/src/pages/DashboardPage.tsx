import { ArrowRight, BookOpen, Flame, Layers, ListChecks, MessageSquare, Sparkles, Target } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, EmptyState, ProgressBar, Skeleton, StatTile } from '../components/ui'
import { useAuth } from '../lib/auth'
import { useDashboard } from '../lib/hooks'
import { cn, formatDate, pct, timeAgo } from '../lib/utils'

const ACTION_ROUTES: Record<string, string> = { notes: '/notes', quiz: '/quizzes', flashcards: '/revision?tab=flashcards', chat: '/tutor' }

export function DashboardPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { data, isLoading } = useDashboard()

  if (isLoading || !data) {
    return (
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
    )
  }

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  const recent = data.quizzes.recent.map((a) => ({ name: formatDate(a.submitted_at), percent: a.percent, title: a.title }))
  const maxActivity = Math.max(1, ...data.streak.last_14_days.map((d) => d.count))

  return (
    <div className="space-y-6 animate-fade-up">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-ink-900">
            {greeting}, {user?.name.split(' ')[0]}
          </h2>
          <p className="text-sm text-slate-500">{data.streak.active_today ? 'You have already studied today. Keep the momentum going.' : 'Nothing logged yet today. One question or a few cards keeps the streak alive.'}</p>
        </div>
        <div className="flex gap-2">
          <Link to="/tutor" className="btn-primary">
            <MessageSquare className="h-4 w-4" /> Ask the tutor
          </Link>
          <Link to="/quizzes" className="btn-secondary">
            <ListChecks className="h-4 w-4" /> Take a quiz
          </Link>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Notes indexed" value={data.documents.ready} hint={`${data.documents.chunks} searchable passages`} icon={<BookOpen className="h-5 w-5" />} tone="sky" />
        <StatTile label="Quiz accuracy" value={pct(data.quizzes.average_percent)} hint={`${data.quizzes.attempts} attempt${data.quizzes.attempts === 1 ? '' : 's'} · best ${pct(data.quizzes.best_percent)}`} icon={<Target className="h-5 w-5" />} tone="mint" />
        <StatTile label="Cards due" value={data.flashcards.due} hint={`${data.flashcards.mastered} mastered · ${data.flashcards.reviewed_today} reviewed today`} icon={<Layers className="h-5 w-5" />} tone="plum" />
        <StatTile label="Study streak" value={`${data.streak.current} day${data.streak.current === 1 ? '' : 's'}`} hint={`${data.chats.questions} questions asked in total`} icon={<Flame className="h-5 w-5" />} tone="amber" />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Accuracy by topic" subtitle="From your graded quiz attempts (last 60 days)" className="xl:col-span-2">
          {data.topic_accuracy.length === 0 ? (
            <EmptyState icon={<Target className="h-5 w-5" />} title="No quiz data yet" description="Take a quiz and your strong and weak topics will show up here." action={<Link to="/quizzes" className="btn-primary btn-sm">Generate a quiz</Link>} />
          ) : (
            <ul className="space-y-3">
              {data.topic_accuracy.map((t) => (
                <li key={t.topic} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 sm:grid-cols-[180px_minmax(0,1fr)_auto]">
                  <span className="truncate text-sm font-medium text-slate-700" title={t.topic}>
                    {t.topic}
                  </span>
                  <ProgressBar value={t.percent} className="hidden sm:block" tone={t.percent < 60 ? 'rose' : t.percent < 80 ? 'amber' : 'mint'} />
                  <span className="text-right font-mono text-xs text-slate-600">
                    {t.percent.toFixed(0)}% <span className="text-slate-400">({t.correct}/{t.questions})</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Recommended next" subtitle="Based on your recent activity">
          <ul className="space-y-3">
            {data.recommendations.map((r) => (
              <li key={r.title}>
                <button
                  onClick={() => navigate(ACTION_ROUTES[r.action] ?? '/', { state: r.params })}
                  className="group flex w-full items-start gap-3 rounded-xl border border-slate-200 p-3 text-left transition-colors hover:border-brand-300 hover:bg-brand-50/50"
                >
                  <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-600">
                    <Sparkles className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-ink-900">{r.title}</div>
                    <div className="text-xs text-slate-500">{r.detail}</div>
                  </div>
                  <ArrowRight className="mt-1 h-4 w-4 text-slate-300 group-hover:text-brand-500" />
                </button>
              </li>
            ))}
            {data.recommendations.length === 0 && <li className="text-sm text-slate-500">You are all caught up.</li>}
          </ul>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Recent quiz scores" subtitle="Percentage per attempt, oldest to newest">
          {recent.length < 2 ? (
            <p className="text-sm text-slate-500">Complete two or more quizzes to see your trend.</p>
          ) : (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={recent} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
                  <CartesianGrid stroke="#eef2f7" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: '#64748b' }} axisLine={false} tickLine={false} />
                  <Tooltip
                    cursor={{ stroke: '#cbd5e1', strokeWidth: 1 }}
                    contentStyle={{ borderRadius: 12, border: '1px solid #e2e8f0', fontSize: 12 }}
                    formatter={(v) => [`${Number(v).toFixed(0)}%`, 'Score']}
                    labelFormatter={(_l, payload) => (payload?.[0]?.payload as { title?: string })?.title ?? ''}
                  />
                  <Line type="monotone" dataKey="percent" stroke="#5b5bd6" strokeWidth={2} dot={{ r: 4, fill: '#5b5bd6', strokeWidth: 2, stroke: '#fff' }} activeDot={{ r: 6 }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card title="Last 14 days" subtitle="Study actions per day">
          <div className="flex h-40 items-end gap-1.5">
            {data.streak.last_14_days.map((d) => (
              <div key={d.date} className="group relative flex h-full flex-1 flex-col items-center justify-end" title={`${formatDate(d.date)}: ${d.count} action${d.count === 1 ? '' : 's'}`}>
                <div className={cn('w-full rounded-t-[4px] transition-all', d.count ? 'bg-brand-500' : 'bg-slate-100')} style={{ height: `${Math.max(6, (d.count / maxActivity) * 100)}%` }} />
              </div>
            ))}
          </div>
          <div className="mt-2 flex justify-between text-[11px] text-slate-400">
            <span>{formatDate(data.streak.last_14_days[0]?.date)}</span>
            <span>today</span>
          </div>
        </Card>

        <Card title="Syllabus progress" subtitle={`${data.syllabus.overall_percent.toFixed(0)}% of tracked topics completed`} actions={<Link to="/syllabus" className="text-xs font-semibold text-brand-700">Open syllabus</Link>}>
          {data.syllabus.subjects.length === 0 ? (
            <p className="text-sm text-slate-500">Mark topics as done in the AKTU Syllabus page to track coverage here.</p>
          ) : (
            <ul className="space-y-3">
              {data.syllabus.subjects.map((s) => (
                <li key={s.subject_id}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="font-semibold text-slate-700">
                      {s.code} <span className="font-normal text-slate-500">{s.name}</span>
                    </span>
                    <span className="font-mono text-slate-500">{s.completed}/{s.topics}</span>
                  </div>
                  <ProgressBar value={s.percent} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Recent activity">
        {data.recent_activity.length === 0 ? (
          <p className="text-sm text-slate-500">Your uploads, chats, quizzes and reviews will appear here.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.recent_activity.map((a) => (
              <li key={a.id} className="flex items-center gap-3 py-2.5 text-sm">
                <span className="h-2 w-2 rounded-full bg-brand-400" />
                <span className="font-medium text-slate-700">{a.label}</span>
                <span className="truncate text-slate-500">{a.detail ?? a.topic ?? ''}</span>
                {a.value !== null && a.type === 'quiz' && <span className="chip bg-mint-50 text-mint-600">{a.value.toFixed(0)}%</span>}
                <span className="ml-auto shrink-0 text-xs text-slate-400">{timeAgo(a.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
