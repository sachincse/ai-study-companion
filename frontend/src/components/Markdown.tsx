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
const FENCE = /^[ \t]*(`{3,}|~{3,})(.*)$/
const GLUED_CLOSE = /^([ \t]*)(`{3,}|~{3,})[ \t]*(\[\d.*)$/

/**
 * Models sometimes glue a citation onto the closing fence ("```[6]"). CommonMark does not accept that as a
 * closing fence, so the block never ends and the rest of the answer renders as raw code. Inside an open fence,
 * split such a line into the bare closing fence and the citation on the next line. Opening fences are untouched.
 */
function splitGluedFences(text: string) {
  const out: string[] = []
  let open = '' // marker of the fence we are inside (``` or ~~~, possibly longer), '' when outside
  for (const line of text.split(/\r?\n/)) {
    const fence = FENCE.exec(line)
    if (!open) {
      // a backtick fence's info string cannot contain backticks (that line is inline code instead)
      if (fence && !(fence[1][0] === '`' && fence[2].includes('`'))) open = fence[1]
    } else if (fence && fence[1][0] === open[0] && fence[1].length >= open.length) {
      const glued = GLUED_CLOSE.exec(line)
      if (glued) {
        out.push(glued[1] + glued[2], glued[1] + glued[3])
        open = ''
        continue
      }
      if (!fence[2].trim()) open = ''
    }
    out.push(line)
  }
  return out.join('\n')
}

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
        {linkifyCitations(splitGluedFences(children))}
      </ReactMarkdown>
    </div>
  )
}
