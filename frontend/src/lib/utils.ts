import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' }) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(undefined, opts)
}

export function formatDateTime(iso: string | null | undefined) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function timeAgo(iso: string | null | undefined) {
  if (!iso) return ''
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`
  return formatDate(iso)
}

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function formatDuration(sec: number | null | undefined) {
  if (!sec && sec !== 0) return ''
  const m = Math.floor(sec / 60)
  const s = sec % 60
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`
  return m ? `${m}m ${s.toString().padStart(2, '0')}s` : `${s}s`
}

export function pct(n: number | null | undefined, digits = 0) {
  if (n === null || n === undefined) return '-'
  return `${n.toFixed(digits)}%`
}

/** Convert FTS `[[term]]` markers into <mark> while escaping everything else. */
export function highlightSnippet(snippet: string) {
  const escaped = snippet.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return escaped.replace(/\[\[(.+?)\]\]/g, '<mark>$1</mark>')
}

// [text](url) and ![alt](src); the label may hold FTS [[term]] markers
const MD_LINK = /!?\[((?:\[\[[^\]\n]*\]\]|[^[\]\n])*)\]\(([^)\s]*)\)/g

/** Unwrap **bold**, __bold__, *italic* and _italic_ in text whose inline code has been parked. */
function unwrapEmphasis(text: string) {
  return text
    .replace(/\*\*(?=[^\s*])([\s\S]*?[^\s*])\*\*/g, '$1')
    .replace(/(^|[^\w_])__(?=[^\s_])([\s\S]*?[^\s_])__(?![\w_])/g, '$1$2')
    .replace(/(^|[^\w*])\*(?=[^\s*])([^*\n]*?[^\s*])\*(?![\w*])/g, '$1$2')
    .replace(/(^|[^\w_])_(?=[^\s_])([^_\n]*?[^\s_])_(?![\w_])/g, '$1$2')
    .replace(/\*\*(?=\S)|(?<=\S)\*\*/g, '') // the other half of the pair was cut off by the snippet window
}

/**
 * Flatten a Markdown answer into one line of plain text for previews (history search hits, the conversation
 * list). FTS `[[term]]` markers are kept, so the result can still go through highlightSnippet.
 */
export function stripMarkdown(text: string) {
  const codes: string[] = []
  const flat = text
    .replace(/^[ \t]*(?:`{3,}|~{3,})[ \t]*(.*)$/gm, (_m, info: string) => (info.includes('[[') ? info : '')) // code fence lines, keeping a search hit in the info string
    .replace(/^[ \t]*(?:[-*_][ \t]*){3,}$/gm, '') // horizontal rules
    .replace(/^(?=[^\n]*\|)(?=[^\n]*---)[ \t|:-]+$/gm, '') // table separator rows (linear: no nested quantifiers)
    .replace(/^(?:[^\n|]*(?<!\|)\|(?!\|)){2,}[^\n|]*$/gm, (row) => row.split('|').map((cell) => cell.trim()).filter(Boolean).join(' · ')) // table rows
    .replace(/^[ \t]*(?:>[ \t]?)+/gm, '') // blockquote markers
    .replace(/^[ \t]*(?:#{1,6}|[-*+])[ \t]+/gm, '') // heading and bullet markers
    .replace(MD_LINK, (_m, label: string, href: string) => (href.startsWith('#cite-') ? `[${label}]` : label))
    .replace(/(`+)([^`]*?)\1/g, (_m, _ticks: string, code: string) => `\u0000${codes.push(code) - 1}\u0000`) // park inline code
  return unwrapEmphasis(flat)
    .replace(/`/g, '') // a code span cut off by the snippet window
    .replace(/\u0000(\d+)\u0000/g, (_m, i: string) => codes[Number(i)]) // inline code comes back verbatim
    .replace(/\s+/g, ' ')
    .trim()
}

/** YYYY-MM-DD in the browser's local calendar (toISOString would give the UTC date). */
export function localDateKey(d = new Date()) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function initials(name: string) {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')
}

export const ANSWER_MODES: { id: string; label: string; hint: string }[] = [
  { id: 'exam', label: 'Exam answer', hint: 'Structured, full-marks style' },
  { id: 'beginner', label: 'Explain simply', hint: 'Plain language and analogies' },
  { id: 'detailed', label: 'Detailed', hint: 'Examples, edge cases, comparisons' },
  { id: 'short', label: 'Short', hint: 'Definition in a few sentences' },
  { id: 'steps', label: 'Step by step', hint: 'Numericals and derivations' },
  { id: 'practice', label: 'Practice questions', hint: 'Generate questions + model answers' },
]
