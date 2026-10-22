import { useMutation, useQuery } from '@tanstack/react-query'
import { Bookmark, BookmarkCheck, ChevronDown, Copy, Filter, GraduationCap, Layers, ListChecks, MessageSquarePlus, Pin, Plus, Send, ThumbsDown, ThumbsUp, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Markdown } from '../components/Markdown'
import { DocumentPicker } from '../components/pickers'
import { Badge, Modal } from '../components/ui'
import { api, errorMessage, streamEvents } from '../lib/api'
import { useInvalidate, useReadyDocuments } from '../lib/hooks'
import type { ChatMessage, ChatSession, ChatSessionDetail, Source } from '../lib/types'
import { ANSWER_MODES, cn, highlightSnippet, timeAgo } from '../lib/utils'

const SUGGESTIONS = [
  'Explain the difference between paging and segmentation with an example',
  'What are the ACID properties? Give a 5-mark answer',
  'Derive the time complexity of merge sort step by step',
  'Give me 5 practice questions on normalization',
]

export function TutorPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const invalidate = useInvalidate()
  const { data: readyDocs } = useReadyDocuments()
  const [input, setInput] = useState('')
  const [mode, setMode] = useState('exam')
  const [docFilter, setDocFilter] = useState<number[]>(() => (params.get('doc') ? [Number(params.get('doc'))] : []))
  const [filterOpen, setFilterOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const [sourceView, setSourceView] = useState<{ sources: Source[]; index: number } | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const sessions = useQuery({ queryKey: ['sessions'], queryFn: () => api<ChatSession[]>('/api/v1/chat/sessions') })
  const session = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => api<ChatSessionDetail>(`/api/v1/chat/sessions/${sessionId}`),
    enabled: !!sessionId,
  })

  // Which session id the local message list currently reflects. Prevents a refetch of the
  // session (e.g. right after we created it and started streaming) from clobbering local state.
  const loadedFor = useRef<string | undefined>(undefined)
  useEffect(() => {
    if (!sessionId) {
      if (loadedFor.current !== undefined) setMessages([])
      loadedFor.current = undefined
      return
    }
    if (loadedFor.current === sessionId) return
    if (session.data && session.data.id === Number(sessionId)) {
      setMessages(session.data.messages)
      setMode(session.data.answer_mode)
      if (session.data.document_ids?.length) setDocFilter(session.data.document_ids)
      loadedFor.current = sessionId
    }
  }, [session.data, sessionId])

  useEffect(() => {
    const topic = (location.state as { topic?: string } | null)?.topic
    if (topic) setInput(`Explain ${topic}`)
  }, [location.state])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const createSession = useMutation({
    mutationFn: () => api<ChatSession>('/api/v1/chat/sessions', { body: { answer_mode: mode, document_ids: docFilter.length ? docFilter : null } }),
  })

  const send = async (text: string) => {
    const content = text.trim()
    if (!content || streaming) return
    setInput('')
    let sid = sessionId ? Number(sessionId) : null
    try {
      if (!sid) {
        const s = await createSession.mutateAsync()
        sid = s.id
        loadedFor.current = String(s.id) // keep the local (streaming) list when the route changes
        navigate(`/tutor/${s.id}`, { replace: true })
      }
    } catch (err) {
      toast.error(errorMessage(err))
      return
    }
    const tempUser: ChatMessage = { id: -Date.now(), session_id: sid, role: 'user', content, provider: null, model: null, follow_ups: null, grounded: false, bookmarked: false, feedback: null, latency_ms: null, created_at: new Date().toISOString(), sources: [] }
    const tempAssistant: ChatMessage = { ...tempUser, id: tempUser.id - 1, role: 'assistant', content: '', pending: true }
    setMessages((m) => [...m, tempUser, tempAssistant])
    setStreaming(true)
    abortRef.current = new AbortController()
    try {
      for await (const ev of streamEvents(`/api/v1/chat/sessions/${sid}/messages`, { content, answer_mode: mode, document_ids: docFilter.length ? docFilter : null }, abortRef.current.signal)) {
        if (ev.type === 'user_message') {
          const real = ev.message as ChatMessage
          setMessages((m) => m.map((x) => (x.id === tempUser.id ? real : x)))
        } else if (ev.type === 'sources') {
          const sources = ev.sources as Source[]
          setMessages((m) => m.map((x) => (x.id === tempAssistant.id ? { ...x, sources, grounded: Boolean(ev.grounded) } : x)))
        } else if (ev.type === 'token') {
          setMessages((m) => m.map((x) => (x.id === tempAssistant.id ? { ...x, content: x.content + (ev.text as string) } : x)))
        } else if (ev.type === 'done') {
          const real = ev.message as ChatMessage
          setMessages((m) => m.map((x) => (x.id === tempAssistant.id ? real : x)))
        } else if (ev.type === 'notice') {
          toast.message(String(ev.message))
        } else if (ev.type === 'error') {
          toast.error(String(ev.message))
          setMessages((m) => m.map((x) => (x.id === tempAssistant.id ? { ...x, pending: false, content: x.content || `_${String(ev.message)}_` } : x)))
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') toast.error(errorMessage(err))
    } finally {
      setStreaming(false)
      invalidate('sessions', 'dashboard', 'session')
    }
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    void send(input)
  }

  const bookmark = useMutation({
    mutationFn: ({ id, value }: { id: number; value: boolean }) => api<ChatMessage>(`/api/v1/chat/messages/${id}/bookmark`, { body: { bookmarked: value } }),
    onSuccess: (msg) => setMessages((m) => m.map((x) => (x.id === msg.id ? { ...x, bookmarked: msg.bookmarked } : x))),
  })
  const feedback = useMutation({
    mutationFn: ({ id, value }: { id: number; value: number | null }) => api<ChatMessage>(`/api/v1/chat/messages/${id}/feedback`, { body: { value } }),
    onSuccess: (msg) => setMessages((m) => m.map((x) => (x.id === msg.id ? { ...x, feedback: msg.feedback } : x))),
  })
  const deleteSession = useMutation({
    mutationFn: (id: number) => api(`/api/v1/chat/sessions/${id}`, { method: 'DELETE' }),
    onSuccess: (_d, id) => {
      invalidate('sessions')
      if (String(id) === sessionId) navigate('/tutor')
    },
  })
  const pinSession = useMutation({
    mutationFn: ({ id, pinned }: { id: number; pinned: boolean }) => api(`/api/v1/chat/sessions/${id}`, { method: 'PATCH', body: { pinned } }),
    onSuccess: () => invalidate('sessions'),
  })

  const lastTopic = useMemo(() => [...messages].reverse().find((m) => m.role === 'user')?.content ?? '', [messages])
  const filterLabel = docFilter.length ? `${docFilter.length} doc${docFilter.length === 1 ? '' : 's'}` : 'All notes'

  return (
    <div className="grid h-[calc(100vh-7.5rem)] gap-4 lg:grid-cols-[270px_minmax(0,1fr)]">
      <aside className="card hidden flex-col overflow-hidden lg:flex">
        <div className="flex items-center justify-between border-b border-slate-100 p-3">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Conversations</span>
          <Link to="/tutor" className="btn-ghost btn-sm" title="New chat">
            <Plus className="h-4 w-4" />
          </Link>
        </div>
        <ul className="flex-1 overflow-y-auto p-2">
          {(sessions.data ?? []).map((s) => (
            <li key={s.id} className="group relative">
              <Link to={`/tutor/${s.id}`} className={cn('block rounded-xl px-3 py-2 pr-14 hover:bg-slate-50', String(s.id) === sessionId && 'bg-brand-50 hover:bg-brand-50')}>
                <div className="flex items-center gap-1 truncate text-sm font-medium text-ink-900">
                  {s.pinned && <Pin className="h-3 w-3 text-brand-500" />}
                  {s.title}
                </div>
                <div className="truncate text-xs text-slate-500">{s.preview || 'No messages yet'}</div>
                <div className="text-[11px] text-slate-400">{timeAgo(s.updated_at)}</div>
              </Link>
              <div className="absolute right-2 top-2 hidden gap-0.5 group-hover:flex">
                <button className="rounded p-1 text-slate-400 hover:text-brand-600" onClick={() => pinSession.mutate({ id: s.id, pinned: !s.pinned })} title={s.pinned ? 'Unpin' : 'Pin'}>
                  <Pin className="h-3.5 w-3.5" />
                </button>
                <button className="rounded p-1 text-slate-400 hover:text-rose-600" onClick={() => confirm('Delete this conversation?') && deleteSession.mutate(s.id)} title="Delete">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </li>
          ))}
          {sessions.data?.length === 0 && <li className="px-3 py-6 text-center text-xs text-slate-500">No conversations yet.</li>}
        </ul>
      </aside>

      <section className="card flex min-h-0 flex-col overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-2.5">
          <div className="flex items-center gap-2 text-sm font-semibold text-ink-900">
            <GraduationCap className="h-4 w-4 text-brand-600" />
            {session.data?.title ?? 'New conversation'}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <select className="input w-auto py-1.5 text-xs" value={mode} onChange={(e) => setMode(e.target.value)} title="Answer style">
              {ANSWER_MODES.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
            <button className={cn('btn-secondary btn-sm', docFilter.length && 'border-brand-300 text-brand-700')} onClick={() => setFilterOpen(true)}>
              <Filter className="h-3.5 w-3.5" /> {filterLabel}
            </button>
            {lastTopic && (
              <QuickActions topic={lastTopic} docIds={docFilter} />
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4">
          {messages.length === 0 ? (
            <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center text-center">
              <div className="grid h-14 w-14 place-items-center rounded-2xl bg-brand-50 text-brand-600">
                <MessageSquarePlus className="h-7 w-7" />
              </div>
              <h3 className="mt-4 text-lg font-bold text-ink-900">Ask anything from your notes</h3>
              <p className="mt-1 text-sm text-slate-500">
                {readyDocs.length ? `Answers are grounded in your ${readyDocs.length} indexed document${readyDocs.length === 1 ? '' : 's'} and cited by page.` : 'Upload notes to get cited answers, or ask general questions right away.'}
              </p>
              <div className="mt-6 grid w-full gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => void send(s)} className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-left text-sm text-slate-700 hover:border-brand-300 hover:bg-brand-50/50">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-5">
              {messages.map((m) => (
                <MessageBubble
                  key={m.id}
                  message={m}
                  onCite={(i) => m.sources.length && setSourceView({ sources: m.sources, index: Math.min(Math.max(i, 1), m.sources.length) - 1 })}
                  onBookmark={() => m.id > 0 && bookmark.mutate({ id: m.id, value: !m.bookmarked })}
                  onFeedback={(v) => m.id > 0 && feedback.mutate({ id: m.id, value: m.feedback === v ? null : v })}
                  onFollowUp={(q) => void send(q)}
                  onOpenSources={() => m.sources.length && setSourceView({ sources: m.sources, index: 0 })}
                />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <form onSubmit={onSubmit} className="border-t border-slate-100 p-3">
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <textarea
              className="input min-h-[46px] max-h-40 resize-y"
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void send(input)
                }
              }}
              placeholder="Ask a question... (Enter to send, Shift+Enter for a new line)"
              disabled={streaming}
            />
            <button className="btn-primary h-[46px]" type="submit" disabled={streaming || !input.trim()}>
              <Send className="h-4 w-4" />
            </button>
          </div>
        </form>
      </section>

      <Modal open={filterOpen} onClose={() => setFilterOpen(false)} title="Limit answers to specific notes">
        <p className="mb-3 text-sm text-slate-500">Pick documents to search. Leave empty to search everything you uploaded.</p>
        <DocumentPicker value={docFilter} onChange={setDocFilter} />
        <div className="mt-4 flex justify-end">
          <button className="btn-primary" onClick={() => setFilterOpen(false)}>
            Done
          </button>
        </div>
      </Modal>

      {sourceView && <SourcesModal sources={sourceView.sources} index={sourceView.index} onClose={() => setSourceView(null)} />}
    </div>
  )
}

function MessageBubble({ message: m, onCite, onBookmark, onFeedback, onFollowUp, onOpenSources }: { message: ChatMessage; onCite: (i: number) => void; onBookmark: () => void; onFeedback: (v: number) => void; onFollowUp: (q: string) => void; onOpenSources: () => void }) {
  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-[15px] text-white shadow-card">{m.content}</div>
      </div>
    )
  }
  return (
    <div className="flex gap-3">
      <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-ink-900 text-brand-300">
        <GraduationCap className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 shadow-card">
          {m.content ? <Markdown onCite={onCite}>{m.content}</Markdown> : <span className="inline-flex gap-1 py-1"><Dot /><Dot delay="150ms" /><Dot delay="300ms" /></span>}
          {m.pending && m.content && <span className="ml-1 inline-block h-4 w-1.5 animate-pulse-dot bg-brand-400 align-middle" />}
        </div>
        {!m.pending && (
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
            {m.sources.length > 0 ? (
              <button className="chip bg-mint-50 text-mint-600 hover:bg-mint-50/70" onClick={onOpenSources}>
                {m.sources.length} source{m.sources.length === 1 ? '' : 's'} from your notes
              </button>
            ) : (
              <Badge tone="amber">general knowledge</Badge>
            )}
            {m.model && <span className="hidden sm:inline">{m.model}</span>}
            {m.latency_ms !== null && <span className="hidden sm:inline">· {(m.latency_ms / 1000).toFixed(1)}s</span>}
            <span className="ml-auto flex items-center gap-0.5">
              <button className="rounded p-1 hover:bg-slate-100" title="Copy" onClick={() => navigator.clipboard.writeText(m.content).then(() => toast.success('Copied'))}>
                <Copy className="h-3.5 w-3.5" />
              </button>
              <button className={cn('rounded p-1 hover:bg-slate-100', m.bookmarked && 'text-brand-600')} title="Bookmark" onClick={onBookmark}>
                {m.bookmarked ? <BookmarkCheck className="h-3.5 w-3.5" /> : <Bookmark className="h-3.5 w-3.5" />}
              </button>
              <button className={cn('rounded p-1 hover:bg-slate-100', m.feedback === 1 && 'text-mint-600')} title="Helpful" onClick={() => onFeedback(1)}>
                <ThumbsUp className="h-3.5 w-3.5" />
              </button>
              <button className={cn('rounded p-1 hover:bg-slate-100', m.feedback === -1 && 'text-rose-600')} title="Not helpful" onClick={() => onFeedback(-1)}>
                <ThumbsDown className="h-3.5 w-3.5" />
              </button>
            </span>
          </div>
        )}
        {!m.pending && m.follow_ups && m.follow_ups.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {m.follow_ups.map((q) => (
              <button key={q} onClick={() => onFollowUp(q)} className="rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 hover:bg-brand-100">
                {q}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function Dot({ delay = '0ms' }: { delay?: string }) {
  return <span className="h-2 w-2 rounded-full bg-slate-300 animate-pulse-dot" style={{ animationDelay: delay }} />
}

function SourcesModal({ sources, index, onClose }: { sources: Source[]; index: number; onClose: () => void }) {
  const [active, setActive] = useState(index)
  const s = sources[active]
  return (
    <Modal open onClose={onClose} title="Sources used in this answer" wide>
      <div className="grid gap-3 sm:grid-cols-[200px_minmax(0,1fr)]">
        <ul className="space-y-1">
          {sources.map((src, i) => (
            <li key={`${src.chunk_id}-${i}`}>
              <button onClick={() => setActive(i)} className={cn('w-full rounded-lg px-2.5 py-2 text-left text-xs', i === active ? 'bg-brand-50 text-brand-700' : 'hover:bg-slate-50')}>
                <span className="cite-chip mr-1">{i + 1}</span>
                <span className="font-medium">{src.document_title}</span>
                {src.page_no && <span className="text-slate-500"> · p. {src.page_no}</span>}
              </button>
            </li>
          ))}
        </ul>
        {s && (
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span className="font-semibold text-ink-900">{s.document_title}</span>
              {s.page_no && <Badge>page {s.page_no}</Badge>}
              <Badge tone="brand">relevance {(s.score * 100).toFixed(0)}%</Badge>
              {s.document_id && (
                <Link to={`/notes?q=${encodeURIComponent(s.snippet.replace(/\[\[|\]\]/g, '').slice(0, 60))}`} className="ml-auto text-brand-700 hover:underline">
                  open in notes
                </Link>
              )}
            </div>
            <p className="text-sm text-slate-700" dangerouslySetInnerHTML={{ __html: highlightSnippet(s.snippet) }} />
          </div>
        )}
      </div>
    </Modal>
  )
}

function QuickActions({ topic, docIds }: { topic: string; docIds: number[] }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const short = topic.length > 80 ? topic.slice(0, 80) : topic
  const go = (path: string) => {
    setOpen(false)
    navigate(path, { state: { topic: short, document_ids: docIds } })
  }
  return (
    <div className="relative">
      <button className="btn-secondary btn-sm" onClick={() => setOpen((o) => !o)}>
        Turn into <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-52 rounded-xl border border-slate-200 bg-white p-1 shadow-pop">
          <button className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => go('/quizzes')}>
            <ListChecks className="h-4 w-4 text-brand-600" /> Quiz on this topic
          </button>
          <button className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => go('/revision?tab=flashcards')}>
            <Layers className="h-4 w-4 text-brand-600" /> Flashcards
          </button>
          <button className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => go('/revision?tab=summaries')}>
            <GraduationCap className="h-4 w-4 text-brand-600" /> Summary
          </button>
        </div>
      )}
    </div>
  )
}
