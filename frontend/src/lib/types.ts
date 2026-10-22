export type UserProfile = {
  answer_mode: string
  semester: number | null
  branch: string | null
  daily_goal_minutes: number
  llm_provider: string | null
  llm_model: string | null
}

export type User = {
  id: number
  email: string
  name: string
  created_at: string
  last_login_at: string | null
  profile: UserProfile
}

export type TokenResponse = { access_token: string; token_type: string; user: User }

export type DocumentStatus = 'uploaded' | 'processing' | 'ready' | 'failed'

export type Document = {
  id: number
  title: string
  filename: string
  mime_type: string
  size_bytes: number
  pages: number
  status: DocumentStatus
  error: string | null
  chunk_count: number
  char_count: number
  subject_id: number | null
  unit: number | null
  created_at: string
  processed_at: string | null
}

export type Chunk = {
  id: number
  document_id: number
  chunk_index: number
  page_no: number | null
  heading: string | null
  content: string
  token_estimate: number
}

export type SearchHit = {
  chunk_id: number
  document_id: number
  document_title: string
  page_no: number | null
  heading: string | null
  snippet: string
  content: string
  score: number
  keyword_score: number
  vector_score: number
  methods: string[]
}

export type SearchResponse = { query: string; mode: string; hits: SearchHit[] }

export type HistoryHit = {
  message_id: number
  session_id: number
  session_title: string
  role: string
  snippet: string
  content: string
  created_at: string
  bookmarked: boolean
}

export type Source = {
  id?: number | null
  chunk_id: number | null
  document_id: number | null
  document_title: string | null
  page_no: number | null
  rank: number
  score: number
  snippet: string
  heading?: string | null
  methods?: string[]
}

export type ChatMessage = {
  id: number
  session_id: number
  role: 'user' | 'assistant'
  content: string
  provider: string | null
  model: string | null
  follow_ups: string[] | null
  grounded: boolean
  bookmarked: boolean
  feedback: number | null
  latency_ms: number | null
  created_at: string
  sources: Source[]
  /** client-only: streaming in progress */
  pending?: boolean
}

export type ChatSession = {
  id: number
  title: string
  subject_id: number | null
  document_ids: number[] | null
  answer_mode: string
  pinned: boolean
  created_at: string
  updated_at: string
  message_count?: number
  preview?: string
}

export type ChatSessionDetail = ChatSession & { messages: ChatMessage[] }

export type QuestionType = 'mcq' | 'true_false' | 'short_answer'

export type Question = {
  id: number
  position: number
  qtype: QuestionType
  prompt: string
  options: string[] | null
  topic: string | null
  marks: number
  source_page: number | null
  answer_key?: string
  explanation?: string | null
}

export type Quiz = {
  id: number
  title: string
  subject_id: number | null
  topic: string | null
  document_ids: number[] | null
  difficulty: string
  question_count: number
  time_limit_sec: number | null
  provider: string | null
  model: string | null
  created_at: string
  questions: Question[]
}

export type QuizSummary = {
  id: number
  title: string
  topic: string | null
  subject_id: number | null
  difficulty: string
  question_count: number
  time_limit_sec: number | null
  created_at: string
  attempt_count: number
  best_percent: number | null
  last_percent: number | null
}

export type Attempt = { id: number; quiz_id: number; started_at: string; submitted_at: string | null; max_score: number }

export type AnswerResult = { question_id: number; answer: string | null; is_correct: boolean | null; marks_awarded: number; ai_feedback: string | null }

export type AttemptResult = {
  id: number
  quiz_id: number
  quiz_title: string
  started_at: string
  submitted_at: string | null
  score: number
  max_score: number
  percent: number
  time_taken_sec: number | null
  topic_breakdown: Record<string, { correct: number; total: number; marks: number; max_marks: number; percent: number }> | null
  weak_topics: string[] | null
  feedback: string | null
  answers: AnswerResult[]
  questions: Question[]
}

export type AttemptHistoryItem = { attempt_id: number; quiz_id: number; title: string; percent: number; score: number; max_score: number; submitted_at: string | null }

export type Flashcard = {
  id: number
  deck_id: number
  front: string
  back: string
  hint: string | null
  topic: string | null
  ease_factor: number
  interval_days: number
  repetitions: number
  lapses: number
  due_at: string
  last_reviewed_at: string | null
}

export type Deck = {
  id: number
  title: string
  subject_id: number | null
  topic: string | null
  document_ids: number[] | null
  created_at: string
  card_count: number
  due_count: number
  mastered_count: number
  new_count: number
  cards?: Flashcard[]
}

export type FlashcardStats = { total: number; due: number; mastered: number; reviewed_today: number; due_next_7_days: number }

export type ArtifactKind = 'summary' | 'keywords' | 'concept_map' | 'study_plan'

export type ConceptNode = { id: string; label: string; type: string; description?: string }
export type ConceptEdge = { id: string; source: string; target: string; label?: string }
export type ConceptGraph = { title: string; nodes: ConceptNode[]; edges: ConceptEdge[]; style?: string }
export type Keyword = { term: string; definition: string; importance: 'high' | 'medium' | 'low'; source?: number | null }
export type PlanTask = { title: string; subject: string; type: string; minutes: number; done: boolean }
export type PlanDay = { date: string; focus: string; tasks: PlanTask[] }
export type StudyPlan = { exam_date: string; daily_minutes: number; subjects: { id: number; code: string; name: string }[]; days: PlanDay[]; tips: string[] }

export type Artifact<T = unknown> = {
  id: number
  kind: ArtifactKind
  title: string
  topic: string | null
  subject_id: number | null
  document_ids: number[] | null
  content: T
  sources: { chunk_id: number; document_id: number; document_title: string; page_no: number | null; snippet: string }[] | null
  provider: string | null
  model: string | null
  created_at: string
}

export type Subject = {
  id: number
  code: string
  name: string
  semester: number
  branch: string
  credits: number | null
  description: string | null
  topic_count: number
  completed_count: number
  percent: number
}

export type SubjectDetail = Subject & { units: { number: number; title: string; topics: { id: number; name: string; completed: boolean }[] }[] }

export type Dashboard = {
  documents: { total: number; ready: number; chunks: number }
  chats: { sessions: number; questions: number; bookmarks: number }
  flashcards: FlashcardStats
  quizzes: { attempts: number; average_percent: number | null; best_percent: number | null; recent: AttemptHistoryItem[] }
  topic_accuracy: { topic: string; questions: number; correct: number; percent: number }[]
  weak_topics: { topic: string; questions: number; correct: number; percent: number }[]
  strong_topics: { topic: string; questions: number; correct: number; percent: number }[]
  streak: { current: number; active_today: boolean; last_14_days: { date: string; count: number }[] }
  syllabus: { overall_percent: number; subjects: { subject_id: number; code: string; name: string; semester: number; topics: number; completed: number; percent: number }[] }
  recent_activity: { id: number; type: string; label: string; detail: string | null; topic: string | null; value: number | null; created_at: string }[]
  recommendations: { title: string; detail: string; action: string; params: Record<string, string> }[]
}

export type Video = {
  video_id: string
  title: string
  channel: string
  url: string
  thumbnail: string
  source: string
  duration_sec: number | null
  view_count: number | null
  published_at: string | null
}

export type VideoResponse = {
  query: string
  source: string
  videos: Video[]
  curated: { channels: { id: string; name: string; url: string; why: string; search_url: string }[]; playlists: unknown[]; tips: string[] }
}

export type ProviderInfo = {
  id: string
  name: string
  default_model: string
  docs_url: string
  key_hint: string
  requires_key: boolean
  free_tier: boolean
  local: boolean
  notes: string
  env_key_configured: boolean
  base_url: string | null
}

export type ResolvedLLM = { provider: string; provider_name: string; model: string; base_url: string | null; key_source: string; key_masked: string | null; has_key: boolean }

export type ProvidersResponse = {
  providers: ProviderInfo[]
  current: ResolvedLLM
  embedding: { provider: string; ready: boolean; model: string | null; dim: number | null; error: string | null }
  vector_store: string
}

export type Health = {
  status: string
  version: string
  app_env: string
  embedding: { provider: string; ready: boolean; model: string | null; dim: number | null; error: string | null }
  vector_store: { name: string; count?: number; error?: string }
  fts: boolean
  default_provider: string
  providers_ready: string[]
  rag_engine: 'active' | 'warming-up'
}
