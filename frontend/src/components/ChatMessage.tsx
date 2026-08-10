import type { CSSProperties } from 'react'
import { Markdown } from './Markdown'
import { CopyIcon, RetryIcon } from './Icons'
import type { Message, ModelStamp } from '../types'

const UNKNOWN: ModelStamp = { name: 'Assistant', provider: '', initials: '··', hue: 0 }

/**
 * Two deliberately different shapes: the user speaks in an inverted block,
 * the model answers in an article column with a byline running down the gutter.
 */
export function ChatMessage({
  message,
  model = UNKNOWN,
  onCopy,
  onRetry,
}: {
  message: Message
  /** Resolved from the live catalog by the parent — see Chat.tsx. */
  model?: ModelStamp
  onCopy?: (message: Message) => void
  onRetry?: (message: Message) => void
}) {
  if (message.role === 'user') {
    return (
      <article className="msg msg-user">
        <span className="label msg-user-label">You</span>
        <div className="user-block">{message.content}</div>
      </article>
    )
  }

  return (
    <article className="msg msg-assistant" style={{ '--hue': model.hue } as CSSProperties}>
      <aside className="byline">
        <span className="byline-rule" />
        <span className="byline-name">{model.name}</span>
        <span className="label byline-provider">{model.provider}</span>
      </aside>

      <div className="msg-body">
        {/* A failure is a plain notice — never re-interpreted as markdown. */}
        {message.failed ? (
          <div className="msg-text is-error">{message.content}</div>
        ) : (
          <div className="msg-text">
            <Markdown content={message.content} />
          </div>
        )}
        <div className="msg-tools">
          <button
            type="button"
            className="tool-btn"
            aria-label="Copy response"
            onClick={() => onCopy?.(message)}
          >
            <CopyIcon />
          </button>
          <button
            type="button"
            className="tool-btn"
            aria-label="Regenerate response"
            onClick={() => onRetry?.(message)}
          >
            <RetryIcon />
          </button>
        </div>
      </div>
    </article>
  )
}

export function TypingMessage({ model }: { model: ModelStamp }) {
  return (
    <article className="msg msg-assistant" style={{ '--hue': model.hue } as CSSProperties}>
      <aside className="byline">
        <span className="byline-rule" />
        <span className="byline-name">{model.name}</span>
        <span className="label byline-provider">{model.provider}</span>
      </aside>

      <div className="msg-body">
        <div className="typing" role="status" aria-label={`${model.name} is responding`}>
          <span />
          <span />
          <span />
        </div>
      </div>
    </article>
  )
}
