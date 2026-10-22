import { useMutation } from '@tanstack/react-query'
import { CheckCircle2, ExternalLink, KeyRound, Loader2, RefreshCw, ShieldCheck, XCircle } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { Badge, Card, Field, PageHeader, Spinner } from '../components/ui'
import { api, errorMessage } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useInvalidate, useProviders } from '../lib/hooks'
import type { ResolvedLLM, User } from '../lib/types'
import { ANSWER_MODES, cn } from '../lib/utils'

type TestResult = { ok: boolean; provider: string; model: string; latency_ms: number | null; reply: string | null; error: string | null }

export function SettingsPage() {
  const { user, refresh } = useAuth()
  const invalidate = useInvalidate()
  const { data, isLoading } = useProviders()
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [test, setTest] = useState<TestResult | null>(null)

  useEffect(() => {
    if (data && !provider) {
      setProvider(data.current.provider)
      setModel(data.current.model)
      setBaseUrl(data.current.base_url ?? '')
    }
  }, [data, provider])

  const spec = data?.providers.find((p) => p.id === provider)
  const selectProvider = (id: string) => {
    const s = data?.providers.find((p) => p.id === id)
    setProvider(id)
    setModel(id === data?.current.provider ? data.current.model : (s?.default_model ?? ''))
    setBaseUrl(s?.base_url ?? '')
    setApiKey('')
    setModels([])
    setTest(null)
  }

  const save = useMutation({
    mutationFn: () => api<ResolvedLLM>('/api/v1/settings/llm', { method: 'PUT', body: { provider, model: model || null, api_key: apiKey || null, base_url: baseUrl } }),
    onSuccess: (r) => {
      toast.success(`Now using ${r.provider_name} · ${r.model}`)
      setApiKey('')
      invalidate('providers')
    },
    onError: (err) => toast.error(errorMessage(err)),
  })
  const runTest = useMutation({
    mutationFn: () => api<TestResult>('/api/v1/settings/llm/test', { body: { provider, model: model || null, api_key: apiKey || null, base_url: baseUrl || null } }),
    onSuccess: setTest,
    onError: (err) => toast.error(errorMessage(err)),
  })
  const loadModels = useMutation({
    mutationFn: () => api<{ models: string[] }>('/api/v1/settings/llm/models', { body: { provider, api_key: apiKey || null, base_url: baseUrl || null } }),
    onSuccess: (r) => {
      setModels(r.models)
      if (!r.models.length) toast.message('The provider returned no models')
    },
    onError: (err) => toast.error(errorMessage(err)),
  })

  if (isLoading || !data) return <Spinner label="Loading settings..." />
  const current = data.current

  return (
    <div className="space-y-6 animate-fade-up">
      <PageHeader title="Settings" subtitle="Bring your own model. Keys are stored encrypted on the server and never sent to the browser." />

      <Card title="Active model" subtitle="What the tutor, quizzes and revision tools currently use">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge tone="brand">{current.provider_name}</Badge>
          <span className="font-mono text-slate-700">{current.model}</span>
          <Badge tone={current.has_key ? 'mint' : 'rose'}>{current.has_key ? (current.key_source === 'user' ? 'your key' : current.key_source === 'env' ? 'server .env key' : 'no key needed') : 'no key configured'}</Badge>
          {current.key_masked && <span className="font-mono text-xs text-slate-400">{current.key_masked}</span>}
          <span className="ml-auto text-xs text-slate-500">
            embeddings: {data.embedding.model ?? data.embedding.provider} ({data.embedding.ready ? 'ready' : 'loading'}) · vectors: {data.vector_store}
          </span>
        </div>
      </Card>

      <Card title="Choose a provider" subtitle="Everything speaks the same chat protocol, so switching is one click">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {data.providers.map((p) => (
            <button key={p.id} onClick={() => selectProvider(p.id)} className={cn('rounded-xl border p-3 text-left transition-colors', provider === p.id ? 'border-brand-400 bg-brand-50' : 'border-slate-200 bg-white hover:border-brand-200')}>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-ink-900">{p.name}</span>
                {p.free_tier && <Badge tone="mint">free tier</Badge>}
                {p.local && <Badge tone="sky">local</Badge>}
                {p.env_key_configured && <Badge tone="amber">key in .env</Badge>}
              </div>
              <p className="mt-1 text-xs text-slate-500">{p.notes || `Default model: ${p.default_model}`}</p>
            </button>
          ))}
        </div>

        {spec && (
          <form
            className="mt-5 space-y-4 border-t border-slate-100 pt-5"
            onSubmit={(e: FormEvent) => {
              e.preventDefault()
              save.mutate()
            }}
          >
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Model" hint="Type a model id or load the live list from the provider">
                <div className="flex gap-2">
                  <input className="input" list="model-list" value={model} onChange={(e) => setModel(e.target.value)} placeholder={spec.default_model || 'model id'} />
                  <datalist id="model-list">
                    {models.map((m) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                  <button type="button" className="btn-secondary" onClick={() => loadModels.mutate()} disabled={loadModels.isPending} title="Load models">
                    {loadModels.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  </button>
                </div>
                {models.length > 0 && (
                  <div className="mt-2 flex max-h-28 flex-wrap gap-1 overflow-y-auto">
                    {models.slice(0, 60).map((m) => (
                      <button type="button" key={m} onClick={() => setModel(m)} className={cn('chip border', model === m ? 'border-brand-300 bg-brand-50 text-brand-700' : 'border-slate-200 bg-white text-slate-600')}>
                        {m}
                      </button>
                    ))}
                  </div>
                )}
              </Field>
              {spec.requires_key ? (
                <Field label="API key" hint={spec.env_key_configured ? 'A server-side key exists; paste your own to override it for your account.' : `Get one at ${spec.docs_url}`}>
                  <div className="relative">
                    <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <input className="input pl-9 font-mono" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={spec.key_hint || 'paste key'} autoComplete="off" />
                  </div>
                  <a href={spec.docs_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-brand-700">
                    Where to get a key <ExternalLink className="h-3 w-3" />
                  </a>
                </Field>
              ) : (
                <Field label="Base URL" hint={spec.id === 'ollama' ? 'Default Ollama endpoint. Pull a model first: ollama pull qwen2.5:7b' : 'Any OpenAI-compatible endpoint, e.g. http://localhost:1234/v1'}>
                  <input className="input font-mono" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://localhost:11434/v1" />
                </Field>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button type="submit" className="btn-primary" disabled={save.isPending}>
                {save.isPending ? 'Saving...' : 'Save as my model'}
              </button>
              <button type="button" className="btn-secondary" onClick={() => runTest.mutate()} disabled={runTest.isPending}>
                {runTest.isPending ? <Spinner label="Testing..." /> : 'Test connection'}
              </button>
              {test && (
                <span className={cn('inline-flex items-center gap-1.5 text-sm', test.ok ? 'text-mint-600' : 'text-rose-600')}>
                  {test.ok ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
                  {test.ok ? `${test.model} replied in ${((test.latency_ms ?? 0) / 1000).toFixed(1)}s: "${test.reply}"` : test.error}
                </span>
              )}
            </div>
          </form>
        )}
      </Card>

      <ProfileCard user={user} onSaved={refresh} />

      <Card title="Privacy" subtitle="How your data is handled">
        <ul className="space-y-2 text-sm text-slate-600">
          <li className="flex gap-2">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-mint-600" /> Notes, chats, quizzes and cards are scoped to your account; other students cannot search your documents.
          </li>
          <li className="flex gap-2">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-mint-600" /> Your API key is encrypted at rest with the server secret and only used for your requests.
          </li>
          <li className="flex gap-2">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-mint-600" /> Deleting a document also deletes its passages and vectors. Conversations are never used for training.
          </li>
        </ul>
      </Card>
    </div>
  )
}

function ProfileCard({ user, onSaved }: { user: User | null; onSaved: () => Promise<void> }) {
  const [name, setName] = useState(user?.name ?? '')
  const [semester, setSemester] = useState(user?.profile.semester ?? '')
  const [goal, setGoal] = useState(user?.profile.daily_goal_minutes ?? 60)
  const [mode, setMode] = useState(user?.profile.answer_mode ?? 'exam')
  const save = useMutation({
    mutationFn: () => api('/api/v1/auth/me', { method: 'PATCH', body: { name, semester: semester === '' ? null : Number(semester), daily_goal_minutes: goal, answer_mode: mode } }),
    onSuccess: async () => {
      toast.success('Profile saved')
      await onSaved()
    },
    onError: (err) => toast.error(errorMessage(err)),
  })
  return (
    <Card title="Profile" subtitle="Used to personalise recommendations and the tutor's default style">
      <form
        className="grid gap-4 md:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate()
        }}
      >
        <Field label="Name">
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} minLength={2} required />
        </Field>
        <Field label="Semester">
          <select className="input" value={semester} onChange={(e) => setSemester(e.target.value === '' ? '' : Number(e.target.value))}>
            <option value="">Not set</option>
            {[1, 2, 3, 4, 5, 6, 7, 8].map((s) => (
              <option key={s} value={s}>
                Semester {s}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Daily goal (min)">
          <input type="number" className="input" min={10} max={720} value={goal} onChange={(e) => setGoal(Number(e.target.value))} />
        </Field>
        <Field label="Default answer style">
          <select className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
            {ANSWER_MODES.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </Field>
        <div className="md:col-span-4">
          <button className="btn-secondary" type="submit" disabled={save.isPending}>
            Save profile
          </button>
        </div>
      </form>
    </Card>
  )
}
