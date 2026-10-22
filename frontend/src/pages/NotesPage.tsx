import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, FileText, Loader2, RefreshCw, Search, Trash2, UploadCloud } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useDropzone } from 'react-dropzone'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { SubjectSelect } from '../components/pickers'
import { Badge, Card, EmptyState, Modal, PageHeader, Spinner } from '../components/ui'
import { api, errorMessage } from '../lib/api'
import { useDocuments, useInvalidate, useSubjects } from '../lib/hooks'
import type { Chunk, Document, SearchResponse } from '../lib/types'
import { cn, formatBytes, highlightSnippet, timeAgo } from '../lib/utils'

const STATUS: Record<Document['status'], { label: string; tone: 'slate' | 'brand' | 'mint' | 'rose' }> = {
  uploaded: { label: 'Queued', tone: 'slate' },
  processing: { label: 'Indexing', tone: 'brand' },
  ready: { label: 'Ready', tone: 'mint' },
  failed: { label: 'Failed', tone: 'rose' },
}

export function NotesPage() {
  const [params, setParams] = useSearchParams()
  const invalidate = useInvalidate()
  const { data: docs, isLoading } = useDocuments(true)
  const { data: subjects } = useSubjects()
  const [title, setTitle] = useState('')
  const [subjectId, setSubjectId] = useState<number | ''>('')
  const [unit, setUnit] = useState('')
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [mode, setMode] = useState<'hybrid' | 'keyword' | 'semantic'>('hybrid')
  const [viewer, setViewer] = useState<{ doc: Document; page?: number | null } | null>(null)

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) {
        const form = new FormData()
        form.append('file', file)
        if (title.trim()) form.append('title', title.trim())
        if (subjectId) form.append('subject_id', String(subjectId))
        if (unit) form.append('unit', unit)
        await api<Document>('/api/v1/documents', { form })
      }
    },
    onSuccess: (_d, files) => {
      toast.success(`${files.length} file${files.length === 1 ? '' : 's'} uploaded. Indexing in the background...`)
      setTitle('')
      invalidate('documents', 'health', 'dashboard')
    },
    onError: (err) => toast.error(errorMessage(err)),
  })

  const onDrop = useCallback((accepted: File[]) => accepted.length && upload.mutate(accepted), [upload])
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'], 'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'], 'text/plain': ['.txt'], 'text/markdown': ['.md'] },
    multiple: true,
  })

  const remove = useMutation({
    mutationFn: (id: number) => api(`/api/v1/documents/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Document removed')
      invalidate('documents', 'health', 'dashboard', 'search', 'chunks')
    },
    onError: (err) => toast.error(errorMessage(err)),
  })
  const reindex = useMutation({
    mutationFn: (id: number) => api(`/api/v1/documents/${id}/reindex`, { method: 'POST' }),
    onSuccess: () => invalidate('documents', 'search', 'chunks'),
    onError: (err) => toast.error(errorMessage(err)),
  })

  const activeQuery = params.get('q') ?? ''
  const search = useQuery({
    queryKey: ['search', activeQuery, mode],
    queryFn: () => api<SearchResponse>('/api/v1/search', { params: { q: activeQuery, mode, top_k: 10 } }),
    enabled: activeQuery.trim().length > 1,
  })
  useEffect(() => setQuery(activeQuery), [activeQuery])

  const submitSearch = (e: FormEvent) => {
    e.preventDefault()
    const next = query.trim()
    if (next && next === activeQuery) void search.refetch()
    else setParams(next ? { q: next } : {})
  }

  const subjectName = (id: number | null) => subjects?.find((s) => s.id === id)?.code ?? ''

  return (
    <div className="space-y-6 animate-fade-up">
      <PageHeader title="My Notes" subtitle="Upload PDFs, Word files or text. They are parsed, chunked and indexed so the tutor can cite them." />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div
            {...getRootProps()}
            className={cn(
              'flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors',
              isDragActive ? 'border-brand-400 bg-brand-50' : 'border-slate-300 hover:border-brand-300 hover:bg-slate-50',
            )}
          >
            <input {...getInputProps()} data-testid="file-input" />
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-50 text-brand-600">
              {upload.isPending ? <Loader2 className="h-6 w-6 animate-spin" /> : <UploadCloud className="h-6 w-6" />}
            </div>
            <p className="mt-3 text-sm font-semibold text-ink-900">{isDragActive ? 'Drop to upload' : 'Drag notes here, or click to browse'}</p>
            <p className="mt-1 text-xs text-slate-500">PDF, DOCX, TXT, MD · up to 25 MB each · scanned PDFs need OCR first</p>
          </div>
        </Card>
        <Card title="Tag the upload" subtitle="Optional, helps filtering and syllabus mapping">
          <div className="space-y-3">
            <label className="block">
              <span className="label">Title</span>
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. OS Unit 4 - Memory management" />
            </label>
            <label className="block">
              <span className="label">Subject</span>
              <SubjectSelect value={subjectId} onChange={setSubjectId} />
            </label>
            <label className="block">
              <span className="label">Unit</span>
              <select className="input" value={unit} onChange={(e) => setUnit(e.target.value)}>
                <option value="">Not specified</option>
                {[1, 2, 3, 4, 5].map((u) => (
                  <option key={u} value={u}>
                    Unit {u}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </Card>
      </div>

      <Card
        title="Search your notes"
        subtitle="Hybrid search combines exact keyword matches (BM25) with semantic similarity"
        actions={
          <div className="flex gap-1 rounded-lg bg-slate-100 p-0.5 text-xs">
            {(['hybrid', 'keyword', 'semantic'] as const).map((m) => (
              <button key={m} onClick={() => setMode(m)} className={cn('rounded-md px-2 py-1 font-semibold capitalize', mode === m ? 'bg-white text-ink-900 shadow-card' : 'text-slate-500')}>
                {m}
              </button>
            ))}
          </div>
        }
      >
        <form onSubmit={submitSearch} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-9" value={query} onChange={(e) => setQuery(e.target.value)} placeholder='Try "page replacement algorithms" or "normal forms"' />
          </div>
          <button className="btn-primary" type="submit">
            Search
          </button>
        </form>
        {search.isFetching && <Spinner label="Searching..." className="mt-3" />}
        {search.data && (
          <ul className="mt-4 space-y-2">
            {search.data.hits.length === 0 && <li className="text-sm text-slate-500">No passages matched. Try different words or upload more notes.</li>}
            {search.data.hits.map((h) => (
              <li key={h.chunk_id} className="rounded-xl border border-slate-200 p-3 hover:border-brand-200">
                <div className="mb-1 flex flex-wrap items-center gap-2 text-xs">
                  <button
                    className="font-semibold text-brand-700 hover:underline"
                    onClick={() => {
                      const doc = docs?.find((d) => d.id === h.document_id)
                      if (doc) setViewer({ doc, page: h.page_no })
                      else void search.refetch()
                    }}
                  >
                    {h.document_title}
                  </button>
                  {h.page_no && <Badge>p. {h.page_no}</Badge>}
                  {h.heading && <span className="truncate text-slate-500">{h.heading}</span>}
                  <span className="ml-auto flex gap-1">
                    {h.methods.map((m) => (
                      <Badge key={m} tone={m === 'keyword' ? 'amber' : 'plum'}>
                        {m}
                      </Badge>
                    ))}
                  </span>
                </div>
                <p className="text-sm text-slate-700" dangerouslySetInnerHTML={{ __html: highlightSnippet(h.snippet) }} />
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Library" subtitle={docs ? `${docs.length} document${docs.length === 1 ? '' : 's'}` : undefined}>
        {isLoading ? (
          <Spinner label="Loading documents..." />
        ) : !docs?.length ? (
          <EmptyState icon={<FileText className="h-5 w-5" />} title="No notes yet" description="Upload your first PDF above. Need material to try? Run scripts/fetch_open_notes.py for open-licensed textbooks." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="pb-2 pr-3 font-semibold">Document</th>
                  <th className="pb-2 pr-3 font-semibold">Subject</th>
                  <th className="pb-2 pr-3 font-semibold">Pages</th>
                  <th className="pb-2 pr-3 font-semibold">Passages</th>
                  <th className="pb-2 pr-3 font-semibold">Status</th>
                  <th className="pb-2 pr-3 font-semibold">Added</th>
                  <th className="pb-2 font-semibold" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {docs.map((d) => {
                  const st = STATUS[d.status]
                  return (
                    <tr key={d.id} className="align-middle">
                      <td className="py-2.5 pr-3">
                        <button className="flex items-center gap-2 text-left font-medium text-ink-900 hover:text-brand-700" onClick={() => d.status === 'ready' && setViewer({ doc: d })}>
                          <FileText className="h-4 w-4 shrink-0 text-slate-400" />
                          <span className="truncate max-w-[280px]" title={d.filename}>
                            {d.title}
                          </span>
                        </button>
                        <div className="pl-6 text-xs text-slate-400">{formatBytes(d.size_bytes)}</div>
                      </td>
                      <td className="py-2.5 pr-3 text-slate-600">
                        {subjectName(d.subject_id)}
                        {d.unit ? ` · U${d.unit}` : ''}
                      </td>
                      <td className="py-2.5 pr-3 font-mono text-xs text-slate-600">{d.pages || '-'}</td>
                      <td className="py-2.5 pr-3 font-mono text-xs text-slate-600">{d.chunk_count || '-'}</td>
                      <td className="py-2.5 pr-3">
                        <Badge tone={st.tone}>
                          {d.status === 'processing' && <Loader2 className="h-3 w-3 animate-spin" />}
                          {d.status === 'ready' && <CheckCircle2 className="h-3 w-3" />}
                          {d.status === 'failed' && <AlertCircle className="h-3 w-3" />}
                          {st.label}
                        </Badge>
                        {d.error && <div className="mt-1 max-w-[220px] text-xs text-rose-600">{d.error}</div>}
                      </td>
                      <td className="py-2.5 pr-3 text-xs text-slate-500">{timeAgo(d.created_at)}</td>
                      <td className="py-2.5 text-right">
                        <div className="flex justify-end gap-1">
                          {d.status === 'ready' && (
                            <Link to={`/tutor?doc=${d.id}`} className="btn-ghost btn-sm" title="Ask about this document">
                              Ask
                            </Link>
                          )}
                          <button className="btn-ghost btn-sm" onClick={() => reindex.mutate(d.id)} title="Re-index">
                            <RefreshCw className="h-3.5 w-3.5" />
                          </button>
                          <button className="btn-ghost btn-sm text-rose-600" onClick={() => confirm(`Delete "${d.title}" and its index?`) && remove.mutate(d.id)} title="Delete">
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {viewer && <DocumentViewer doc={viewer.doc} page={viewer.page ?? undefined} onClose={() => setViewer(null)} />}
    </div>
  )
}

function DocumentViewer({ doc, page, onClose }: { doc: Document; page?: number; onClose: () => void }) {
  const chunks = useQuery({ queryKey: ['chunks', doc.id], queryFn: () => api<Chunk[]>(`/api/v1/documents/${doc.id}/chunks`) })
  useEffect(() => {
    if (!chunks.data || !page) return
    const el = document.getElementById(`chunk-page-${page}`)
    el?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [chunks.data, page])
  return (
    <Modal open onClose={onClose} title={doc.title} wide>
      <p className="mb-3 text-xs text-slate-500">
        {doc.filename} · {doc.pages} page{doc.pages === 1 ? '' : 's'} · {doc.chunk_count} passage{doc.chunk_count === 1 ? '' : 's'}
      </p>
      {chunks.isLoading ? (
        <Spinner label="Loading passages..." />
      ) : (
        <div className="max-h-[65vh] space-y-3 overflow-y-auto pr-1">
          {chunks.data?.map((c, i) => {
            const firstOnPage = i === 0 || chunks.data![i - 1].page_no !== c.page_no
            return (
              <div key={c.id} id={firstOnPage && c.page_no ? `chunk-page-${c.page_no}` : undefined} className={cn('rounded-xl border p-3', c.page_no === page ? 'border-brand-300 bg-brand-50/40' : 'border-slate-200')}>
                <div className="mb-1 flex items-center gap-2 text-xs text-slate-500">
                  <Badge>#{c.chunk_index + 1}</Badge>
                  {c.page_no && <span>page {c.page_no}</span>}
                  {c.heading && <span className="truncate">· {c.heading}</span>}
                </div>
                <p className="whitespace-pre-wrap text-sm text-slate-700">{c.content}</p>
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}
