import { useEffect, useRef } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { getModel } from '../data/models'
import { AttachIcon, SendIcon, StopIcon } from './Icons'

interface Props {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  onStop: () => void
  isStreaming: boolean
  modelId: string
}

const MAX_HEIGHT = 200

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  isStreaming,
  modelId,
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const model = getModel(modelId)

  // Grow the textarea with its content, up to a cap.
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`
  }, [value])

  const canSend = value.trim().length > 0 && !isStreaming

  function handleKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (canSend) onSubmit()
    }
  }

  return (
    <div className="composer-wrap">
      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault()
          if (canSend) onSubmit()
        }}
      >
        <button type="button" className="icon-btn composer-attach" aria-label="Attach a file">
          <AttachIcon />
        </button>

        <textarea
          ref={textareaRef}
          className="composer-input"
          rows={1}
          value={value}
          placeholder={`Ask ${model.name}`}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
        />

        {isStreaming ? (
          <button
            type="button"
            className="send-btn is-stop"
            onClick={onStop}
            aria-label="Stop generating"
          >
            <StopIcon />
          </button>
        ) : (
          <button type="submit" className="send-btn" disabled={!canSend} aria-label="Send message">
            <SendIcon />
          </button>
        )}
      </form>

      <p className="label composer-hint">
        <span>
          <kbd>Enter</kbd> send
        </span>
        <span>
          <kbd>Shift</kbd>
          <kbd>Enter</kbd> new line
        </span>
        <span className="composer-count">{value.length} chars</span>
      </p>
    </div>
  )
}
