import { BookOpenCheck, GraduationCap, ListChecks, MessageSquareText, ShieldCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { errorMessage } from '../lib/api'
import { useAuth } from '../lib/auth'

const POINTS = [
  { icon: MessageSquareText, text: 'Ask questions and get answers cited from your own notes, page by page.' },
  { icon: ListChecks, text: 'Generate quizzes from any unit and get grounded, explained grading.' },
  { icon: BookOpenCheck, text: 'Flashcards with spaced repetition, summaries, keywords and concept maps.' },
  { icon: ShieldCheck, text: 'Bring your own model: Groq, Gemini, OpenAI, Claude, Grok or a local Ollama.' },
]

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      if (mode === 'login') await login(email, password)
      else await register(name, email, password)
      navigate(from, { replace: true })
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 lg:grid lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-ink-900 px-12 py-14 text-slate-200 lg:flex lg:flex-col">
        <div className="absolute -right-24 -top-24 h-80 w-80 rounded-full bg-brand-500/20 blur-3xl" />
        <div className="absolute -bottom-20 -left-10 h-72 w-72 rounded-full bg-teal-600/20 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-500/20 text-brand-300">
            <GraduationCap className="h-6 w-6" />
          </div>
          <div className="text-lg font-bold text-white">AI Study Companion</div>
        </div>
        <div className="relative mt-16 max-w-md">
          <p className="text-sm font-semibold uppercase tracking-widest text-brand-300">RAG-powered personal assistant</p>
          <h1 className="mt-3 text-4xl font-extrabold leading-tight text-white">Study from your notes, not from guesses.</h1>
          <p className="mt-4 text-slate-400">
            Upload PDFs and lecture notes, then chat, quiz, revise and track progress against the AKTU syllabus. Every answer is grounded in your material with citations.
          </p>
          <ul className="mt-10 space-y-4">
            {POINTS.map((p) => (
              <li key={p.text} className="flex items-start gap-3">
                <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-ink-700 text-brand-300">
                  <p.icon className="h-4 w-4" />
                </div>
                <span className="text-sm text-slate-300">{p.text}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="relative mt-auto text-xs text-slate-500">Open source. Runs on your laptop or a single container. Bring your own API key.</div>
      </div>

      <div className="flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-ink-900 text-brand-300">
              <GraduationCap className="h-6 w-6" />
            </div>
            <div className="text-lg font-bold text-ink-900">AI Study Companion</div>
          </div>
          <h2 className="text-2xl font-bold text-ink-900">{mode === 'login' ? 'Welcome back' : 'Create your study space'}</h2>
          <p className="mt-1 text-sm text-slate-500">
            {mode === 'login' ? 'Sign in to continue where you left off.' : 'Free, private, and your notes never leave your server.'}
          </p>
          <form onSubmit={submit} className="card mt-6 space-y-4 p-6">
            {mode === 'register' && (
              <label className="block">
                <span className="label">Full name</span>
                <input className="input" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} autoComplete="name" placeholder="Asha Verma" />
              </label>
            )}
            <label className="block">
              <span className="label">Email</span>
              <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" placeholder="you@college.edu" />
            </label>
            <label className="block">
              <span className="label">Password</span>
              <input
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                placeholder={mode === 'login' ? 'Your password' : 'At least 8 characters'}
              />
            </label>
            <button className="btn-primary w-full" disabled={busy}>
              {busy ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account'}
            </button>
          </form>
          <p className="mt-4 text-center text-sm text-slate-500">
            {mode === 'login' ? (
              <>
                New here? <Link to="/register" className="font-semibold text-brand-700">Create an account</Link>
              </>
            ) : (
              <>
                Already have an account? <Link to="/login" className="font-semibold text-brand-700">Sign in</Link>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  )
}
