import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import { cn } from '../lib/utils'

type Props = {
  children: string
  className?: string
  /** Called when a citation chip like [2] is clicked (1-based index). */
  onCite?: (index: number) => void
}

const CITATION = /\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\()/g
// fenced code, inline code and TeX math must be left alone (array indices, matrices...)
const PROTECTED = /(```[\s\S]*?```|`[^`\n]*`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$)/g

/** Turn bare [n] / [n, m] citations into links we can style as chips, outside code and math. */
function linkifyCitations(text: string) {
  return text
    .split(PROTECTED)
    .map((segment, i) =>
      i % 2 === 1
        ? segment
        : segment.replace(CITATION, (_m, group: string) =>
            group
              .split(',')
              .map((n) => n.trim())
              .map((n) => `[${n}](#cite-${n})`)
              .join(''),
          ),
    )
    .join('')
}

export function Markdown({ children, className, onCite }: Props) {
  return (
    <div className={cn('prose-chat text-[15px] leading-relaxed text-slate-800', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ href, children: linkChildren, ...rest }) => {
            if (href?.startsWith('#cite-')) {
              const n = Number(href.slice(6))
              return (
                <button type="button" className="cite-chip" onClick={() => onCite?.(n)} title={`Source ${n}`}>
                  {n}
                </button>
              )
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" className="text-brand-700 underline" {...rest}>
                {linkChildren}
              </a>
            )
          },
        }}
      >
        {linkifyCitations(children)}
      </ReactMarkdown>
    </div>
  )
}
