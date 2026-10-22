import { useMutation, useQuery } from '@tanstack/react-query'
import { BookText, Copy, KeyRound, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { toast } from 'sonner'
import { api, errorMessage } from '../../lib/api'
import { useInvalidate } from '../../lib/hooks'
import type { Artifact, Keyword } from '../../lib/types'
import { cn, timeAgo } from '../../lib/utils'
import { Markdown } from '../Markdown'
import { Badge, Card, EmptyState, Field, Modal, Spinner } from '../ui'
import { GenerateForm } from './GenerateForm'

export function useArtifacts<T>(kind: string) {
  return useQuery({ queryKey: ['artifacts', kind], queryFn: () => api<Artifact<T>[]>('/api/v1/tools/artifacts', { params: { kind } }) })
}

export function ArtifactList<T>({ kind, items, selected, onSelect, emptyTitle, emptyDescription, onNew, renderMeta }: { kind: string; items: Artifact<T>[] | undefined; selected: number | null; onSelect: (id: number) => void; emptyTitle: string; emptyDescription: string; onNew: () => void; renderMeta?: (a: Artifact<T>) => string }) {
  const invalidate = useInvalidate()
  const remove = useMutation({ mutationFn: (id: number) => api(`/api/v1/tools/artifacts/${id}`, { method: 'DELETE' }), onSuccess: () => invalidate('artifacts') })
  if (!items) return <Spinner label="Loading..." />
  if (!items.length) return <EmptyState icon={<BookText className="h-5 w-5" />} title={emptyTitle} description={emptyDescription} action={<button className="btn-primary" onClick={onNew}>Generate</button>} />
  return (
    <ul className="space-y-1.5">
      {items.map((a) => (
        <li key={a.id} className="group relative">
          <button onClick={() => onSelect(a.id)} className={cn('w-full rounded-xl border px-3 py-2.5 pr-9 text-left', selected === a.id ? 'border-brand-300 bg-brand-50' : 'border-slate-200 bg-white hover:bg-slate-50')}>
            <div className="truncate text-sm font-semibold text-ink-900">{a.title}</div>
            <div className="truncate text-xs text-slate-500">{renderMeta ? renderMeta(a) : `${a.topic ?? kind} · ${timeAgo(a.created_at)}`}</div>
          </button>
          <button className="absolute right-2 top-2.5 hidden rounded p-1 text-slate-400 hover:text-rose-600 group-hover:block" onClick={() => confirm('Delete?') && remove.mutate(a.id)} aria-label="Delete">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </li>
      ))}
    </ul>
  )
}

export function SourcesFooter({ sources }: { sources: Artifact['sources'] }) {
  if (!sources?.length) return null
  return (
    <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
      <span className="font-semibold">Sources: </span>
      {sources.map((s, i) => (
        <span key={`${s.chunk_id}-${i}`} className="mr-2 inline-flex items-center gap-1">
          <span className="cite-chip">{i + 1}</span>
          {s.document_title}
          {s.page_no ? ` p.${s.page_no}` : ''}
        </span>
      ))}
    </div>
  )
}

export function SummariesTab() {
  const invalidate = useInvalidate()
  const location = useLocation()
  const { data } = useArtifacts<{ markdown: string }>('summary')
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if ((location.state as { topic?: string } | null)?.topic) setOpen(true)
  }, [location.state])
  const [selected, setSelected] = useState<number | null>(null)
  const generate = useMutation({
    mutationFn: (v: { topic: string; document_ids: number[]; subject_id: number | '' }) =>
      api<Artifact<{ markdown: string }>>('/api/v1/tools/summary', { body: { topic: v.topic || null, document_ids: v.document_ids.length ? v.document_ids : null, subject_id: v.subject_id || null } }),
    onSuccess: (a) => {
      setOpen(false)
      setSelected(a.id)
      invalidate('artifacts', 'dashboard')
    },
    onError: (err) => toast.error(errorMessage(err)),
  })
  const active = data?.find((a) => a.id === selected) ?? data?.[0]
  return (
    <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
      <div className="space-y-3">
        <button className="btn-primary w-full" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> New summary
        </button>
        <ArtifactList kind="summary" items={data} selected={active?.id ?? null} onSelect={setSelected} emptyTitle="No summaries yet" emptyDescription="Exam-style revision summaries with definitions, formulas, keywords and common mistakes." onNew={() => setOpen(true)} />
      </div>
      <Card>
        {active ? (
          <>
            <div className="mb-3 flex items-center justify-between gap-2">
              <h3 className="text-lg font-bold text-ink-900">{active.title}</h3>
              <button className="btn-ghost btn-sm" onClick={() => navigator.clipboard.writeText(active.content.markdown).then(() => toast.success('Copied as Markdown'))}>
                <Copy className="h-3.5 w-3.5" /> Copy
              </button>
            </div>
            <Markdown>{active.content.markdown}</Markdown>
            <SourcesFooter sources={active.sources} />
          </>
        ) : (
          <p className="text-sm text-slate-500">Select or generate a summary.</p>
        )}
      </Card>
      <Modal open={open} onClose={() => !generate.isPending && setOpen(false)} title="Generate a revision summary">
        <GenerateForm onSubmit={(v) => generate.mutate(v)} busy={generate.isPending} submitLabel="Summarise" />
      </Modal>
    </div>
  )
}

export function KeywordsTab() {
  const invalidate = useInvalidate()
  const { data } = useArtifacts<{ keywords: Keyword[] }>('keywords')
  const [open, setOpen] = useState(false)
  const [count, setCount] = useState(15)
  const [selected, setSelected] = useState<number | null>(null)
  const generate = useMutation({
    mutationFn: (v: { topic: string; document_ids: number[]; subject_id: number | '' }) =>
      api<Artifact<{ keywords: Keyword[] }>>('/api/v1/tools/keywords', { body: { topic: v.topic || null, document_ids: v.document_ids.length ? v.document_ids : null, subject_id: v.subject_id || null, count } }),
    onSuccess: (a) => {
      setOpen(false)
      setSelected(a.id)
      invalidate('artifacts', 'dashboard')
    },
    onError: (err) => toast.error(errorMessage(err)),
  })
  const active = data?.find((a) => a.id === selected) ?? data?.[0]
  const tone = (imp: string) => (imp === 'high' ? 'rose' : imp === 'medium' ? 'amber' : 'slate')
  return (
    <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
      <div className="space-y-3">
        <button className="btn-primary w-full" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> Extract keywords
        </button>
        <ArtifactList kind="keywords" items={data} selected={active?.id ?? null} onSelect={setSelected} emptyTitle="No keyword sheets yet" emptyDescription="Pull the exam-relevant terms out of a topic with one-line definitions." onNew={() => setOpen(true)} />
      </div>
      <Card>
        {active ? (
          <>
            <h3 className="mb-3 text-lg font-bold text-ink-900">{active.title}</h3>
            <div className="divide-y divide-slate-100">
              {[...active.content.keywords].sort((a, b) => ['high', 'medium', 'low'].indexOf(a.importance) - ['high', 'medium', 'low'].indexOf(b.importance)).map((k) => (
                <div key={k.term} className="flex items-start gap-3 py-2.5">
                  <KeyRound className="mt-1 h-4 w-4 shrink-0 text-brand-500" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-ink-900">{k.term}</span>
                      <Badge tone={tone(k.importance)}>{k.importance}</Badge>
                    </div>
                    <p className="text-sm text-slate-600">{k.definition}</p>
                  </div>
                </div>
              ))}
            </div>
            <SourcesFooter sources={active.sources} />
          </>
        ) : (
          <p className="text-sm text-slate-500">Select or generate a keyword sheet.</p>
        )}
      </Card>
      <Modal open={open} onClose={() => !generate.isPending && setOpen(false)} title="Extract exam keywords">
        <GenerateForm onSubmit={(v) => generate.mutate(v)} busy={generate.isPending} submitLabel="Extract">
          <Field label="How many">
            <select className="input" value={count} onChange={(e) => setCount(Number(e.target.value))}>
              {[10, 15, 20, 30].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </Field>
        </GenerateForm>
      </Modal>
    </div>
  )
}
