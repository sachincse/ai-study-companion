import { useMutation, useQuery } from '@tanstack/react-query'
import { Layers, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { toast } from 'sonner'
import { api, errorMessage } from '../../lib/api'
import { useInvalidate } from '../../lib/hooks'
import type { Deck, Flashcard, FlashcardStats } from '../../lib/types'
import { cn, timeAgo } from '../../lib/utils'
import { Badge, Card, EmptyState, Field, Modal, ProgressBar, Spinner, StatTile } from '../ui'
import { GenerateForm } from './GenerateForm'

export function FlashcardsTab() {
  const invalidate = useInvalidate()
  const location = useLocation()
  const [open, setOpen] = useState(Boolean((location.state as { topic?: string } | null)?.topic))
  const [count, setCount] = useState(12)
  const [review, setReview] = useState<{ deckId: number | null } | null>(null)
  const [openDeck, setOpenDeck] = useState<number | null>(null)

  useEffect(() => {
    if ((location.state as { topic?: string } | null)?.topic) setOpen(true)
  }, [location.state])

  const stats = useQuery({ queryKey: ['flashcard-stats'], queryFn: () => api<FlashcardStats>('/api/v1/flashcards/stats') })
  const decks = useQuery({ queryKey: ['decks'], queryFn: () => api<Deck[]>('/api/v1/flashcards/decks') })

  const generate = useMutation({
    mutationFn: (v: { topic: string; document_ids: number[]; subject_id: number | '' }) =>
      api<Deck>('/api/v1/flashcards/generate', { body: { topic: v.topic || null, document_ids: v.document_ids.length ? v.document_ids : null, subject_id: v.subject_id || null, count } }),
    onSuccess: (deck) => {
      toast.success(`${deck.card_count} cards created`)
      setOpen(false)
      invalidate('decks', 'flashcard-stats', 'dashboard')
    },
    onError: (err) => toast.error(errorMessage(err)),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api(`/api/v1/flashcards/decks/${id}`, { method: 'DELETE' }),
    onSuccess: () => invalidate('decks', 'flashcard-stats', 'dashboard'),
  })

  if (review) return <ReviewSession deckId={review.deckId} onExit={() => { setReview(null); invalidate('decks', 'flashcard-stats', 'dashboard') }} />

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Due now" value={stats.data?.due ?? 0} tone="rose" icon={<Layers className="h-5 w-5" />} hint={`${stats.data?.due_next_7_days ?? 0} more due this week`} />
        <StatTile label="Reviewed today" value={stats.data?.reviewed_today ?? 0} tone="mint" icon={<Sparkles className="h-5 w-5" />} />
        <StatTile label="Mastered" value={stats.data?.mastered ?? 0} tone="brand" hint="interval of 3+ weeks" icon={<Layers className="h-5 w-5" />} />
        <StatTile label="Total cards" value={stats.data?.total ?? 0} tone="sky" icon={<Layers className="h-5 w-5" />} />
      </div>

      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" onClick={() => setReview({ deckId: null })} disabled={!stats.data?.due}>
          Review all due ({stats.data?.due ?? 0})
        </button>
        <button className="btn-secondary" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> New deck from notes
        </button>
      </div>

      {decks.isLoading ? (
        <Spinner label="Loading decks..." />
      ) : !decks.data?.length ? (
        <EmptyState icon={<Layers className="h-5 w-5" />} title="No flashcard decks yet" description="Generate a deck from a topic or your notes. Reviews are scheduled with SM-2 spaced repetition." action={<button className="btn-primary" onClick={() => setOpen(true)}>Create a deck</button>} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {decks.data.map((d) => (
            <Card key={d.id}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="truncate font-bold text-ink-900">{d.title}</h3>
                  <p className="truncate text-xs text-slate-500">{d.topic ?? 'From your notes'} · {timeAgo(d.created_at)}</p>
                </div>
                {d.due_count > 0 && <Badge tone="rose">{d.due_count} due</Badge>}
              </div>
              <div className="mt-3">
                <ProgressBar value={d.card_count ? (d.mastered_count / d.card_count) * 100 : 0} tone="mint" />
                <div className="mt-1 flex justify-between text-[11px] text-slate-500">
                  <span>{d.mastered_count} mastered</span>
                  <span>{d.card_count} cards · {d.new_count} new</span>
                </div>
              </div>
              <div className="mt-4 flex gap-2">
                <button className="btn-primary btn-sm flex-1" onClick={() => setReview({ deckId: d.id })} disabled={!d.due_count}>
                  Review
                </button>
                <button className="btn-secondary btn-sm" onClick={() => setOpenDeck(d.id)}>
                  Cards
                </button>
                <button className="btn-ghost btn-sm text-rose-600" onClick={() => confirm('Delete this deck?') && remove.mutate(d.id)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => !generate.isPending && setOpen(false)} title="Generate flashcards">
        <GenerateForm onSubmit={(v) => generate.mutate(v)} busy={generate.isPending} submitLabel="Create deck">
          <Field label="Number of cards">
            <select className="input" value={count} onChange={(e) => setCount(Number(e.target.value))}>
              {[8, 12, 16, 20, 30].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </Field>
        </GenerateForm>
      </Modal>

      {openDeck !== null && <DeckModal deckId={openDeck} onClose={() => setOpenDeck(null)} />}
    </div>
  )
}

function DeckModal({ deckId, onClose }: { deckId: number; onClose: () => void }) {
  const invalidate = useInvalidate()
  const deck = useQuery({ queryKey: ['deck', deckId], queryFn: () => api<Deck>(`/api/v1/flashcards/decks/${deckId}`) })
  const [front, setFront] = useState('')
  const [back, setBack] = useState('')
  const add = useMutation({
    mutationFn: () => api<Flashcard>(`/api/v1/flashcards/decks/${deckId}/cards`, { body: { front, back } }),
    onSuccess: () => {
      setFront('')
      setBack('')
      invalidate('deck', 'decks', 'flashcard-stats')
    },
    onError: (err) => toast.error(errorMessage(err)),
  })
  const del = useMutation({ mutationFn: (id: number) => api(`/api/v1/flashcards/cards/${id}`, { method: 'DELETE' }), onSuccess: () => invalidate('deck', 'decks', 'flashcard-stats') })
  return (
    <Modal open onClose={onClose} title={deck.data?.title ?? 'Deck'} wide>
      <div className="max-h-[50vh] space-y-2 overflow-y-auto pr-1">
        {deck.data?.cards?.map((c) => (
          <div key={c.id} className="flex items-start gap-3 rounded-xl border border-slate-200 p-3 text-sm">
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-ink-900">{c.front}</div>
              <div className="text-slate-600">{c.back}</div>
              <div className="mt-1 text-[11px] text-slate-400">
                interval {c.interval_days}d · ease {c.ease_factor.toFixed(2)} · {c.repetitions} reviews{c.lapses ? ` · ${c.lapses} lapses` : ''}
              </div>
            </div>
            <button className="text-slate-400 hover:text-rose-600" onClick={() => del.mutate(c.id)} aria-label="Delete card">
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
      <form
        className="mt-4 grid gap-2 border-t border-slate-100 pt-4 sm:grid-cols-[1fr_1fr_auto]"
        onSubmit={(e) => {
          e.preventDefault()
          if (front.trim() && back.trim()) add.mutate()
        }}
      >
        <input className="input" placeholder="Front (question)" value={front} onChange={(e) => setFront(e.target.value)} />
        <input className="input" placeholder="Back (answer)" value={back} onChange={(e) => setBack(e.target.value)} />
        <button className="btn-secondary" type="submit" disabled={add.isPending}>
          Add card
        </button>
      </form>
    </Modal>
  )
}

const RATINGS: { id: 'again' | 'hard' | 'good' | 'easy'; label: string; hint: string; cls: string }[] = [
  { id: 'again', label: 'Again', hint: '10 min', cls: 'bg-rose-50 text-rose-600 hover:bg-rose-100' },
  { id: 'hard', label: 'Hard', hint: 'shorter', cls: 'bg-amber-50 text-amber-600 hover:bg-amber-100' },
  { id: 'good', label: 'Good', hint: 'normal', cls: 'bg-mint-50 text-mint-600 hover:bg-mint-100' },
  { id: 'easy', label: 'Easy', hint: 'longer', cls: 'bg-brand-50 text-brand-700 hover:bg-brand-100' },
]

function ReviewSession({ deckId, onExit }: { deckId: number | null; onExit: () => void }) {
  const [queue, setQueue] = useState<Flashcard[] | null>(null)
  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [done, setDone] = useState<{ again: number; total: number }>({ again: 0, total: 0 })

  useEffect(() => {
    api<Flashcard[]>('/api/v1/flashcards/due', { params: { deck_id: deckId ?? undefined, limit: 40 } })
      .then(setQueue)
      .catch((err) => toast.error(errorMessage(err)))
  }, [deckId])

  const rate = useMutation({
    mutationFn: ({ id, rating }: { id: number; rating: string }) => api<Flashcard>(`/api/v1/flashcards/cards/${id}/review`, { body: { rating } }),
    onSuccess: (_c, vars) => {
      setDone((d) => ({ again: d.again + (vars.rating === 'again' ? 1 : 0), total: d.total + 1 }))
      setFlipped(false)
      setIndex((i) => i + 1)
    },
    onError: (err) => toast.error(errorMessage(err)),
  })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!queue || index >= queue.length) return
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        setFlipped((f) => !f)
      }
      const map: Record<string, string> = { '1': 'again', '2': 'hard', '3': 'good', '4': 'easy' }
      if (flipped && map[e.key] && !rate.isPending) rate.mutate({ id: queue[index].id, rating: map[e.key] })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [queue, index, flipped, rate])

  if (!queue) return <Spinner label="Loading cards..." />
  if (index >= queue.length) {
    return (
      <Card className="mx-auto max-w-lg text-center">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-mint-50 text-mint-600">
          <Sparkles className="h-7 w-7" />
        </div>
        <h3 className="mt-3 text-lg font-bold text-ink-900">{queue.length ? 'Session complete' : 'Nothing due right now'}</h3>
        <p className="mt-1 text-sm text-slate-500">
          {queue.length ? `${done.total} cards reviewed · ${done.total - done.again} remembered · ${done.again} to relearn in 10 minutes.` : 'Come back when cards are due, or create a new deck.'}
        </p>
        <button className="btn-primary mt-4" onClick={onExit}>
          Back to decks
        </button>
      </Card>
    )
  }
  const card = queue[index]
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div className="flex items-center justify-between text-sm text-slate-500">
        <button className="btn-ghost btn-sm" onClick={onExit}>
          Exit session
        </button>
        <span>
          Card {index + 1} of {queue.length}
        </span>
      </div>
      <ProgressBar value={(index / queue.length) * 100} />
      <div className="flip-card min-h-[260px] cursor-pointer select-none" onClick={() => setFlipped((f) => !f)}>
        <div className={cn('flip-inner relative min-h-[260px]', flipped && 'flipped')}>
          <div className="flip-face card absolute inset-0 flex flex-col items-center justify-center p-8 text-center">
            <span className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">{card.topic ?? 'Question'}</span>
            <p className="text-xl font-semibold text-ink-900">{card.front}</p>
            {card.hint && <p className="mt-3 text-sm text-slate-500">Hint: {card.hint}</p>}
            <p className="mt-6 text-xs text-slate-400">Click or press space to reveal</p>
          </div>
          <div className="flip-face flip-back card absolute inset-0 flex flex-col items-center justify-center bg-brand-50 p-8 text-center">
            <span className="mb-3 text-xs font-semibold uppercase tracking-wide text-brand-500">Answer</span>
            <p className="text-lg text-ink-900">{card.back}</p>
          </div>
        </div>
      </div>
      <div className={cn('grid grid-cols-4 gap-2 transition-opacity', !flipped && 'pointer-events-none opacity-40')}>
        {RATINGS.map((r, i) => (
          <button key={r.id} className={cn('btn flex-col gap-0 py-2', r.cls)} onClick={() => rate.mutate({ id: card.id, rating: r.id })} disabled={rate.isPending}>
            <span>{r.label}</span>
            <span className="text-[10px] font-normal opacity-70">
              {r.hint} · <span className="kbd">{i + 1}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
