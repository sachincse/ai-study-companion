import { useQuery } from '@tanstack/react-query'
import { ExternalLink, PlayCircle, Search, MonitorPlay } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { SubjectSelect } from '../components/pickers'
import { Badge, Card, EmptyState, PageHeader, Spinner } from '../components/ui'
import { api } from '../lib/api'
import type { VideoResponse } from '../lib/types'
import { formatDuration } from '../lib/utils'

export function LecturesPage() {
  const [params, setParams] = useSearchParams()
  const [subjectId, setSubjectId] = useState<number | ''>(params.get('subject_id') ? Number(params.get('subject_id')) : '')
  const [topic, setTopic] = useState(params.get('topic') ?? '')
  const [q, setQ] = useState(params.get('q') ?? '')

  const active = { subject_id: params.get('subject_id') ?? '', topic: params.get('topic') ?? '', q: params.get('q') ?? '' }
  const enabled = Boolean(active.q || active.topic || active.subject_id)
  const videos = useQuery({
    queryKey: ['videos', active],
    queryFn: () => api<VideoResponse>('/api/v1/resources/videos', { params: { subject_id: active.subject_id || undefined, topic: active.topic || undefined, q: active.q || undefined, max_results: 9 } }),
    enabled,
    staleTime: 6 * 3600_000,
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const next: Record<string, string> = {}
    if (subjectId) next.subject_id = String(subjectId)
    if (topic.trim()) next.topic = topic.trim()
    if (q.trim()) next.q = q.trim()
    setParams(next)
  }

  return (
    <div className="space-y-5 animate-fade-up">
      <PageHeader title="Lecture Finder" subtitle="YouTube lectures mapped to AKTU subjects and units, plus the channels students actually use for exams." />
      <Card>
        <form onSubmit={submit} className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_auto]">
          <SubjectSelect value={subjectId} onChange={setSubjectId} />
          <input className="input" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Topic or unit, e.g. Banker's algorithm" />
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="...or a free search" />
          <button className="btn-primary" type="submit">
            <Search className="h-4 w-4" /> Find
          </button>
        </form>
      </Card>

      {!enabled ? (
        <EmptyState icon={<MonitorPlay className="h-5 w-5" />} title="Search for a lecture" description="Pick a subject and a topic, or type any query. Works without a YouTube API key." />
      ) : videos.isLoading ? (
        <Spinner label="Searching YouTube..." />
      ) : videos.data ? (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span>
              Results for <span className="font-semibold text-ink-900">{videos.data.query}</span>
            </span>
            <Badge tone={videos.data.source === 'none' ? 'amber' : 'mint'}>{videos.data.source === 'youtube_api' ? 'YouTube Data API' : videos.data.source === 'ytdlp' ? 'live search' : 'live search unavailable'}</Badge>
          </div>
          {videos.data.videos.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {videos.data.videos.map((v) => (
                <a key={v.video_id} href={v.url} target="_blank" rel="noreferrer" className="card group overflow-hidden transition-colors hover:border-brand-300">
                  <div className="relative aspect-video bg-slate-100">
                    <img src={v.thumbnail} alt="" className="h-full w-full object-cover" loading="lazy" />
                    <div className="absolute inset-0 grid place-items-center bg-ink-950/0 transition-colors group-hover:bg-ink-950/30">
                      <PlayCircle className="h-10 w-10 text-white opacity-0 drop-shadow transition-opacity group-hover:opacity-100" />
                    </div>
                    {v.duration_sec && <span className="absolute bottom-1.5 right-1.5 rounded bg-ink-950/80 px-1.5 py-0.5 font-mono text-[11px] text-white">{formatDuration(v.duration_sec)}</span>}
                  </div>
                  <div className="p-3">
                    <h4 className="line-clamp-2 text-sm font-semibold text-ink-900">{v.title}</h4>
                    <p className="mt-1 text-xs text-slate-500">
                      {v.channel}
                      {v.view_count ? ` · ${Intl.NumberFormat('en', { notation: 'compact' }).format(v.view_count)} views` : ''}
                    </p>
                  </div>
                </a>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">Live search returned nothing this time. Use the curated channels below.</p>
          )}
          <Card title="Recommended channels" subtitle="Curated for this subject. Links open a YouTube search scoped to the channel's style.">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {videos.data.curated.channels.map((c) => (
                <div key={c.id} className="rounded-xl border border-slate-200 p-3">
                  <div className="flex items-center gap-2">
                    <MonitorPlay className="h-4 w-4 text-rose-600" />
                    <a href={c.url} target="_blank" rel="noreferrer" className="font-semibold text-ink-900 hover:text-brand-700">
                      {c.name}
                    </a>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{c.why}</p>
                  <a href={c.search_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-brand-700">
                    Search this topic <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              ))}
            </div>
            {videos.data.curated.tips.length > 0 && (
              <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-slate-600">
                {videos.data.curated.tips.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            )}
          </Card>
        </>
      ) : null}
    </div>
  )
}
