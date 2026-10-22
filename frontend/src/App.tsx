import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { useAuth } from './lib/auth'
import { AuthPage } from './pages/AuthPage'
import { DashboardPage } from './pages/DashboardPage'
import { HistoryPage } from './pages/HistoryPage'
import { LecturesPage } from './pages/LecturesPage'
import { NotesPage } from './pages/NotesPage'
import { QuizAttemptPage } from './pages/QuizAttemptPage'
import { QuizResultPage } from './pages/QuizResultPage'
import { QuizzesPage } from './pages/QuizzesPage'
import { RevisionPage } from './pages/RevisionPage'
import { SettingsPage } from './pages/SettingsPage'
import { SubjectPage } from './pages/SubjectPage'
import { SyllabusPage } from './pages/SyllabusPage'
import { TutorPage } from './pages/TutorPage'

function FullScreenSpinner() {
  return (
    <div className="min-h-screen grid place-items-center bg-slate-50">
      <div className="flex items-center gap-3 text-slate-500">
        <span className="h-3 w-3 rounded-full bg-brand-500 animate-pulse-dot" />
        <span className="text-sm font-medium">Loading your study space...</span>
      </div>
    </div>
  )
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <FullScreenSpinner />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <>{children}</>
}

function PublicOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <FullScreenSpinner />
  if (user) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><AuthPage mode="login" /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><AuthPage mode="register" /></PublicOnly>} />
      <Route element={<RequireAuth><AppShell /></RequireAuth>}>
        <Route index element={<DashboardPage />} />
        <Route path="/tutor" element={<TutorPage />} />
        <Route path="/tutor/:sessionId" element={<TutorPage />} />
        <Route path="/notes" element={<NotesPage />} />
        <Route path="/quizzes" element={<QuizzesPage />} />
        <Route path="/quizzes/:quizId" element={<QuizAttemptPage />} />
        <Route path="/quizzes/attempts/:attemptId" element={<QuizResultPage />} />
        <Route path="/revision" element={<RevisionPage />} />
        <Route path="/syllabus" element={<SyllabusPage />} />
        <Route path="/syllabus/:subjectId" element={<SubjectPage />} />
        <Route path="/lectures" element={<LecturesPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
