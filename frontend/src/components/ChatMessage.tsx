import type { CSSProperties } from 'react'
import { getModel } from '../data/models'
import { CopyIcon, RetryIcon } from './Icons'
import type { Message } from '../types'

/**
 * Two deliberately different shapes: the user speaks in an inverted block,
 * the model answers in an article column with a byline running down the gutter.
 */
export function ChatMessage({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <article className="msg msg-user">
        <span className="label msg-user-label">You</span>
        <div className="user-block">{message.content}</div>
      </article>
    )
  }

  const model = getModel(message.modelId ?? '')

  return (
    <article
      className="msg msg-assistant"
      style={{ '--hue': model.hue } as CSSProperties}
    >
      <aside className="byline">
        <span className="byline-rule" />
        <span className="byline-name">{model.name}</span>
        <span className="label byline-provider">{model.provider}</span>
      </aside>

      <div className="msg-body">
        <div className="msg-text">{message.content}</div>
        <div className="msg-tools">
          <button type="button" className="tool-btn" aria-label="Copy response">
            <CopyIcon />
          </button>
          <button type="button" className="tool-btn" aria-label="Regenerate response">
            <RetryIcon />
          </button>
        </div>
      </div>
    </article>
  )
}

export function TypingMessage({ modelId }: { modelId: string }) {
  const model = getModel(modelId)

  return (
    <article
      className="msg msg-assistant"
      style={{ '--hue': model.hue } as CSSProperties}
    >
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
