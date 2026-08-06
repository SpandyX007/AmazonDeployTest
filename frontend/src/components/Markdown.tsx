import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Assistant prose. Raw HTML is not enabled, so model output can't inject
 * markup — react-markdown escapes it as text.
 *
 * Memoised on `content`: a streaming turn re-renders on every token, and
 * re-parsing is the expensive part.
 */
export const Markdown = memo(function Markdown({ content }: { content: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Model-supplied links open away from the app, without referrer.
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer nofollow">
              {children}
            </a>
          ),
          // Wide tables scroll on their own instead of stretching the column.
          table: ({ children, ...props }) => (
            <div className="md-table-scroll">
              <table {...props}>{children}</table>
            </div>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
})
