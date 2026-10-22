import { BookOpen, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Card, PageHeader, ProgressBar, Spinner } from '../components/ui'
import { useSubjects } from '../lib/hooks'

export function SyllabusPage() {
  const { data, isLoading } = useSubjects()
  if (isLoading || !data) return <Spinner label="Loading syllabus..." />
  const semesters = [...new Set(data.map((s) => s.semester))].sort((a, b) => a - b)
  return (
    <div className="space-y-6 animate-fade-up">
      <PageHeader title="AKTU Syllabus" subtitle="B.Tech CSE core subjects with unit-wise topics. Tick topics as you cover them; quizzes, flashcards and lectures can target any unit." />
      {semesters.map((sem) => (
        <section key={sem}>
          <h3 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Semester {sem}</h3>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data
              .filter((s) => s.semester === sem)
              .map((s) => (
                <Link key={s.id} to={`/syllabus/${s.id}`} className="block">
                  <Card className="h-full transition-colors hover:border-brand-300">
                    <div className="flex items-start gap-3">
                      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600">
                        <BookOpen className="h-5 w-5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="font-mono text-xs text-slate-500">
                          {s.code} · {s.credits ?? '-'} credits
                        </div>
                        <h4 className="font-bold text-ink-900">{s.name}</h4>
                        <p className="mt-1 line-clamp-2 text-xs text-slate-500">{s.description}</p>
                      </div>
                      <ChevronRight className="h-4 w-4 text-slate-300" />
                    </div>
                    <div className="mt-4">
                      <ProgressBar value={s.percent} tone="mint" />
                      <div className="mt-1 flex justify-between text-[11px] text-slate-500">
                        <span>{s.completed_count} of {s.topic_count} topics</span>
                        <span>{s.percent.toFixed(0)}%</span>
                      </div>
                    </div>
                  </Card>
                </Link>
              ))}
          </div>
        </section>
      ))}
    </div>
  )
}
