import { useQuery } from '@tanstack/react-query'
import { Bookmark, History, Search } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Markdown } from '../components/Markdown'
import { Badge, Card, EmptyState, PageHeader, Spinner } from '../components/ui'
import { api } from '../lib/api'
import type { ChatMessage, HistoryHit } from '../lib/types'
import { formatDateTime, highlightSnippet, stripMarkdown } from '../lib/utils'

/** The first ~max characters of a saved answer, cut at a line break so no bold pair or link is left half open. */
function excerpt(markdown: string, max = 1200) {
  if (markdown.length <= max) return markdown
  const lineEnd = markdown.lastIndexOf('\n', max)
  const cut = lineEnd > max / 2 ? lineEnd : markdown.lastIndexOf(' ', max)
  let head = markdown.slice(0, cut > 0 ? cut : max).trimEnd()
  if ((head.match(/\*\*/g)?.length ?? 0) % 2) head = head.slice(0, head.lastIndexOf('**')).trimEnd() // the cut split a **bold** pair
  return `${head}\n\n...`
}

export function HistoryPage() {
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') ?? '')
  const active = params.get('q') ?? ''
  const hits = useQuery({ queryKey: ['history', active], queryFn: () => api<HistoryHit[]>('/api/v1/search/history', { params: { q: active } }), enabled: active.trim().length > 1 })
  const bookmarks = useQuery({ queryKey: ['bookmarks'], queryFn: () => api<ChatMessage[]>('/api/v1/chat/bookmarks') })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setParams(q.trim() ? { q: q.trim() } : {})
  }

  return (
    <div className="space-y-5 animate-fade-up">
      <PageHeader title="Chat History" subtitle="Every question and answer is indexed. Search old doubts instead of asking again." />
      <Card>
        <form onSubmit={submit} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-9" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search past conversations, e.g. 'normal forms'" />
          </div>
          <button className="btn-primary" type="submit">
            Search
          </button>
        </form>
        {hits.isFetching && <Spinner label="Searching..." className="mt-3" />}
        {hits.data && (
          <ul className="mt-4 divide-y divide-slate-100">
            {hits.data.length === 0 && <li className="py-3 text-sm text-slate-500">No matches.</li>}
            {hits.data.map((h) => (
              <li key={h.message_id} className="py-3">
                <div className="mb-1 flex flex-wrap items-center gap-2 text-xs">
                  <Link to={`/tutor/${h.session_id}`} className="font-semibold text-brand-700 hover:underline">
                    {h.session_title}
                  </Link>
                  <Badge tone={h.role === 'user' ? 'slate' : 'brand'}>{h.role === 'user' ? 'you' : 'tutor'}</Badge>
                  {h.bookmarked && <Badge tone="amber">bookmarked</Badge>}
                  <span className="ml-auto text-slate-400">{formatDateTime(h.created_at)}</span>
                </div>
                <p className="text-sm text-slate-700" dangerouslySetInnerHTML={{ __html: highlightSnippet(stripMarkdown(h.snippet)) }} />
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Bookmarked answers" subtitle="Saved explanations you want to come back to">
        {bookmarks.isLoading ? (
          <Spinner label="Loading bookmarks..." />
        ) : !bookmarks.data?.length ? (
          <EmptyState icon={<Bookmark className="h-5 w-5" />} title="No bookmarks yet" description="Use the bookmark icon under any tutor answer to save it here." />
        ) : (
          <div className="space-y-3">
            {bookmarks.data.map((m) => (
              <div key={m.id} className="rounded-xl border border-slate-200 p-4">
                <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
                  <History className="h-3.5 w-3.5" />
                  <Link to={`/tutor/${m.session_id}`} className="font-semibold text-brand-700 hover:underline">
                    Open conversation
                  </Link>
                  <span className="ml-auto">{formatDateTime(m.created_at)}</span>
                </div>
                <Markdown className="text-sm">{excerpt(m.content)}</Markdown>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
