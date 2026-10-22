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

/** Turn bare [n] / [n, m] citations into links we can style as chips. */
function linkifyCitations(text: string) {
  return text.replace(/\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\()/g, (_m, group: string) =>
    group
      .split(',')
      .map((n) => n.trim())
      .map((n) => `[${n}](#cite-${n})`)
      .join(''),
  )
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
