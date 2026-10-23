import { useQuery } from '@tanstack/react-query'
import {
  BookOpen,
  Flame,
  GraduationCap,
  History,
  LayoutDashboard,
  Layers,
  ListChecks,
  LogOut,
  Menu,
  MessageSquare,
  Search,
  Settings,
  Sparkles,
  MonitorPlay,
  X,
} from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import type { Dashboard, Health, ProvidersResponse } from '../../lib/types'
import { cn, initials } from '../../lib/utils'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/tutor', label: 'AI Tutor', icon: MessageSquare },
  { to: '/notes', label: 'My Notes', icon: BookOpen },
  { to: '/quizzes', label: 'Quizzes', icon: ListChecks },
  { to: '/revision', label: 'Revision Studio', icon: Layers },
  { to: '/syllabus', label: 'AKTU Syllabus', icon: GraduationCap },
  { to: '/lectures', label: 'Lectures', icon: MonitorPlay },
  { to: '/history', label: 'Chat History', icon: History },
  { to: '/settings', label: 'Settings', icon: Settings },
]

const TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/tutor': 'AI Tutor',
  '/notes': 'My Notes',
  '/quizzes': 'Quizzes & Grading',
  '/revision': 'Revision Studio',
  '/syllabus': 'AKTU Syllabus',
  '/lectures': 'Lecture Finder',
  '/history': 'Chat History',
  '/settings': 'Settings',
}

function pageTitle(pathname: string) {
  if (TITLES[pathname]) return TITLES[pathname]
  const base = '/' + pathname.split('/')[1]
  return TITLES[base] ?? 'AI Study Companion'
}

export function AppShell() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')

  const health = useQuery({ queryKey: ['health'], queryFn: () => api<Health>('/api/v1/system/health'), refetchInterval: 30_000 })
  const providers = useQuery({ queryKey: ['providers'], queryFn: () => api<ProvidersResponse>('/api/v1/settings/providers') })
  const dashboard = useQuery({ queryKey: ['dashboard'], queryFn: () => api<Dashboard>('/api/v1/dashboard'), staleTime: 60_000 })

  // a new page starts at the top (the router keeps the previous page's scroll offset) with the mobile menu closed
  useEffect(() => {
    setOpen(false)
    window.scrollTo(0, 0)
  }, [location.pathname])

  const submitSearch = (e: FormEvent) => {
    e.preventDefault()
    if (q.trim()) navigate(`/notes?q=${encodeURIComponent(q.trim())}`)
  }

  const engineActive = health.data?.rag_engine === 'active'
  const streak = dashboard.data?.streak.current ?? 0

  const sidebar = (
    <aside className="flex h-full w-64 flex-col bg-ink-900 text-slate-300">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-brand-500/20 text-brand-300">
          <GraduationCap className="h-5 w-5" />
        </div>
        <div>
          <div className="text-[15px] font-bold text-white leading-tight">AI Study Companion</div>
          <div className="text-[11px] text-slate-400">RAG-powered exam prep</div>
        </div>
        <button className="ml-auto text-slate-400 lg:hidden" onClick={() => setOpen(false)} aria-label="Close menu">
          <X className="h-5 w-5" />
        </button>
      </div>
      <nav className="mt-2 flex-1 space-y-1 px-3">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors',
                isActive ? 'bg-brand-600 text-white shadow-pop' : 'text-slate-300 hover:bg-ink-700 hover:text-white',
              )
            }
          >
            <item.icon className="h-[18px] w-[18px]" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="space-y-3 px-4 pb-4">
        <div className="rounded-xl bg-ink-800 px-3 py-2.5 text-xs">
          <div className="flex items-center gap-2">
            <span className={cn('h-2 w-2 rounded-full', engineActive ? 'bg-emerald-400' : 'bg-amber-400 animate-pulse-dot')} />
            <span className="font-semibold text-slate-200">{engineActive ? 'RAG Engine Active' : 'RAG Engine warming up'}</span>
          </div>
          <div className="mt-1 truncate text-slate-400">
            {health.data ? `${health.data.vector_store.count ?? 0} chunks indexed · ${health.data.embedding.model ?? health.data.embedding.provider}` : 'Checking engine...'}
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-xl px-1 py-1">
          <div className="grid h-9 w-9 place-items-center rounded-full bg-brand-500 text-sm font-bold text-white">{initials(user?.name ?? '?')}</div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-white">{user?.name}</div>
            <div className="truncate text-[11px] text-slate-400">{user?.email}</div>
          </div>
          <button onClick={logout} className="rounded-lg p-2 text-slate-400 hover:bg-ink-700 hover:text-white" title="Sign out" aria-label="Sign out">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  )

  return (
    <div className="flex min-h-screen bg-slate-50">
      <div className="hidden lg:block lg:fixed lg:inset-y-0">{sidebar}</div>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink-950/60" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 shadow-pop">{sidebar}</div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur sm:px-6">
          <button className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu className="h-5 w-5" />
          </button>
          <h1 className="min-w-0 flex-1 truncate text-base font-bold text-ink-900 sm:flex-none sm:text-lg">{pageTitle(location.pathname)}</h1>
          <form onSubmit={submitSearch} className="ml-auto hidden w-full max-w-sm md:block">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search your notes..." className="input pl-9" aria-label="Search notes" />
            </div>
          </form>
          <div className="ml-auto flex shrink-0 items-center gap-2 md:ml-0">
            <div className="chip whitespace-nowrap bg-amber-50 text-amber-600" title="Study streak">
              <Flame className="h-3.5 w-3.5" /> {streak}
              <span className="hidden sm:inline"> day{streak === 1 ? '' : 's'}</span>
            </div>
            <button onClick={() => navigate('/settings')} className="chip hidden bg-brand-50 text-brand-700 hover:bg-brand-100 md:inline-flex" title="Active model (change in Settings)">
              <Sparkles className="h-3.5 w-3.5" />
              <span className="max-w-[160px] truncate">{providers.data?.current.model ?? 'model'}</span>
            </button>
          </div>
        </header>
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
