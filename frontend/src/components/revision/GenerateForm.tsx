import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { toast } from 'sonner'
import { DocumentPicker, SubjectSelect } from '../pickers'
import { Field, Spinner } from '../ui'

export type GenerateValues = { topic: string; document_ids: number[]; subject_id: number | '' }

export function GenerateForm({ onSubmit, busy, submitLabel, children, requireTopicOrDocs = true }: { onSubmit: (v: GenerateValues) => void; busy: boolean; submitLabel: string; children?: ReactNode; requireTopicOrDocs?: boolean }) {
  const location = useLocation()
  const state = (location.state as { topic?: string; document_ids?: number[]; subject_id?: number } | null) ?? null
  const [topic, setTopic] = useState(state?.topic ?? '')
  const [docIds, setDocIds] = useState<number[]>(state?.document_ids ?? [])
  const [subjectId, setSubjectId] = useState<number | ''>(state?.subject_id ?? '')

  useEffect(() => {
    if (state?.topic) setTopic(state.topic)
    if (state?.document_ids) setDocIds(state.document_ids)
  }, [state])

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (requireTopicOrDocs && !topic.trim() && !docIds.length) {
      toast.error('Give a topic or pick at least one document')
      return
    }
    onSubmit({ topic: topic.trim(), document_ids: docIds, subject_id: subjectId })
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Topic" hint="Leave empty to work across the selected documents">
        <input className="input" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. Deadlock avoidance and the Banker's algorithm" />
      </Field>
      <Field label="Subject (optional)">
        <SubjectSelect value={subjectId} onChange={setSubjectId} />
      </Field>
      <Field label="Ground in these notes">
        <DocumentPicker value={docIds} onChange={setDocIds} compact />
      </Field>
      {children}
      <div className="flex justify-end">
        <button className="btn-primary" type="submit" disabled={busy}>
          {busy ? <Spinner label="Generating..." className="text-white" /> : submitLabel}
        </button>
      </div>
    </form>
  )
}
