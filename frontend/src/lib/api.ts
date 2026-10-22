/**
 * Thin fetch wrapper for the backend API, plus a Server-Sent-Events reader used
 * by the tutor chat. Tokens live in localStorage under `asc_token`.
 */
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''
const TOKEN_KEY = 'asc_token'

export class ApiError extends Error {
  status: number
  detail: string
  kind?: string

  constructor(status: number, detail: string, kind?: string) {
    super(detail)
    this.status = status
    this.detail = detail
    this.kind = kind
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable */
  }
}

type Options = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  form?: FormData
  params?: Record<string, string | number | boolean | undefined | null>
  signal?: AbortSignal
}

function buildUrl(path: string, params?: Options['params']) {
  const url = new URL(API_BASE + path, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v))
    }
  }
  return url.toString()
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = res.statusText || 'Request failed'
  let kind: string | undefined
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') detail = data.detail
    else if (Array.isArray(data?.detail)) detail = data.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ')
    kind = data?.kind
  } catch {
    /* non-json */
  }
  return new ApiError(res.status, detail, kind)
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  const res = await fetch(buildUrl(path, opts.params), { method: opts.method ?? (body ? 'POST' : 'GET'), headers, body, signal: opts.signal })
  if (res.status === 401 && token) {
    setToken(null)
    window.dispatchEvent(new CustomEvent('asc:unauthorized'))
  }
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export type SSEEvent = { type: string; [key: string]: unknown }

/** POST a JSON body and yield parsed `data:` events as they stream in. */
export async function* streamEvents(path: string, body: unknown, signal?: AbortSignal): AsyncGenerator<SSEEvent> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'text/event-stream' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(buildUrl(path), { method: 'POST', headers, body: JSON.stringify(body), signal })
  if (!res.ok || !res.body) throw await parseError(res)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      for (const line of raw.split('\n')) {
        if (line.startsWith('data: ')) {
          try {
            yield JSON.parse(line.slice(6)) as SSEEvent
          } catch {
            /* ignore malformed frame */
          }
        }
      }
    }
  }
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail
  if (err instanceof Error) return err.message
  return 'Something went wrong'
}
