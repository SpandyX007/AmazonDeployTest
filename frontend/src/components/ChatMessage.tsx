import type { CSSProperties } from 'react'
import { getModel } from '../data/models'
import { CopyIcon, RetryIcon } from './Icons'
import type { Message } from '../types'

export function ChatMessage({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <article className="msg msg-user">
        <div className="bubble">{message.content}</div>
      </article>
    )
  }

  const model = getModel(message.modelId ?? '')

  return (
    <article className="msg msg-assistant">
      <span
        className="avatar avatar-model"
        style={{ '--hue': model.hue } as CSSProperties}
        aria-hidden="true"
      >
        {model.initials}
      </span>
      <div className="msg-body">
        <div className="msg-meta">
          <span className="msg-model">{model.name}</span>
          <span className="msg-provider">{model.provider}</span>
        </div>
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
    <article className="msg msg-assistant">
      <span
        className="avatar avatar-model"
        style={{ '--hue': model.hue } as CSSProperties}
        aria-hidden="true"
      >
        {model.initials}
      </span>
      <div className="msg-body">
        <div className="msg-meta">
          <span className="msg-model">{model.name}</span>
        </div>
        <div className="typing" role="status" aria-label={`${model.name} is responding`}>
          <span />
          <span />
          <span />
        </div>
      </div>
    </article>
  )
}
