import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Sidebar } from './components/Sidebar'
import { ModelPicker } from './components/ModelPicker'
import { ChatMessage, TypingMessage } from './components/ChatMessage'
import { Composer } from './components/Composer'
import { ArrowIcon, MoonIcon, SidebarIcon, SunIcon } from './components/Icons'
import { DEFAULT_MODEL_ID, MODELS, SUGGESTIONS, getModel } from './data/models'
import type { Message } from './types'
import './App.css'

type Theme = 'light' | 'dark'

function preferredTheme(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

let messageCounter = 0
function nextId() {
  messageCounter += 1
  return `m${messageCounter}`
}

/** Splits a headline into per-word spans so it can rise in sequence. */
function KineticHeadline({ text }: { text: string }) {
  return (
    <h1 className="welcome-title">
      {text.split(' ').map((word, i) => (
        <span className="word" key={`${word}-${i}`} style={{ '--i': i } as CSSProperties}>
          {word}
        </span>
      ))}
    </h1>
  )
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(preferredTheme)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [activeConversation, setActiveConversation] = useState<string | null>(null)
  const [modelId, setModelId] = useState(DEFAULT_MODEL_ID)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)

  const threadRef = useRef<HTMLDivElement>(null)
  const replyTimer = useRef<number | undefined>(undefined)

  const model = getModel(modelId)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  // Keep the newest message in view.
  useEffect(() => {
    threadRef.current?.scrollTo({
      top: threadRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, isStreaming])

  useEffect(() => () => window.clearTimeout(replyTimer.current), [])

  function send(text: string) {
    const content = text.trim()
    if (!content || isStreaming) return

    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: 'user', content, createdAt: Date.now() },
    ])
    setDraft('')
    setIsStreaming(true)

    // UI-only placeholder. Swap this block for the /response API call later.
    replyTimer.current = window.setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: 'assistant',
          modelId,
          createdAt: Date.now(),
          content:
            `This is a preview of how ${model.name} by ${model.provider} will answer. ` +
            `The interface is not connected to the backend yet — once /response is wired up, ` +
            `the real reply will stream into this column.`,
        },
      ])
      setIsStreaming(false)
    }, 1400)
  }

  function stop() {
    window.clearTimeout(replyTimer.current)
    setIsStreaming(false)
  }

  function newChat() {
    stop()
    setMessages([])
    setDraft('')
    setActiveConversation(null)
  }

  const isEmpty = messages.length === 0

  return (
    <div className={`app ${sidebarOpen ? 'sidebar-open' : ''}`}>
      <div className="grain" aria-hidden="true" />

      <Sidebar
        open={sidebarOpen}
        activeId={activeConversation}
        onSelect={setActiveConversation}
        onNewChat={newChat}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="scrim" onClick={() => setSidebarOpen(false)} aria-hidden="true" />

      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="icon-btn sidebar-toggle"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open sidebar"
            >
              <SidebarIcon />
            </button>
            <ModelPicker selectedId={modelId} onSelect={setModelId} />
          </div>

          {/* Instrument rail — mono readout of the live session. */}
          <div className="readout" aria-hidden="true">
            <span className="readout-cell">
              <em>ctx</em>
              {model.context}
            </span>
            <span className="readout-cell">
              <em>turns</em>
              {String(messages.length).padStart(2, '0')}
            </span>
            <span className="readout-cell">
              <span className={`pulse ${isStreaming ? 'is-live' : ''}`} />
              {isStreaming ? 'generating' : 'ready'}
            </span>
          </div>

          <button
            type="button"
            className="icon-btn"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            aria-label="Toggle colour theme"
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
        </header>

        <div className="thread" ref={threadRef}>
          {isEmpty ? (
            <section className="welcome">
              <p className="label welcome-eyebrow">
                <span>AI Workspace</span>
                <span className="tick" />
                <span>{MODELS.length} models online</span>
              </p>

              <KineticHeadline text="Ask anything. Switch minds mid-thought." />

              <p className="welcome-sub">
                One thread, every model. Pick the mind that fits the question —
                the conversation carries over.
              </p>

              <div className="starters">
                <div className="starters-head label">
                  <span>Opening moves</span>
                  <span>Prompt</span>
                </div>
                {SUGGESTIONS.map((item, i) => (
                  <button
                    type="button"
                    key={item.title}
                    className="starter"
                    onClick={() => send(item.body)}
                  >
                    <span className="starter-index">{String(i + 1).padStart(2, '0')}</span>
                    <span className="starter-title">{item.title}</span>
                    <span className="starter-body">{item.body}</span>
                    <ArrowIcon className="starter-arrow" />
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <div className="messages">
              {messages.map((message) => (
                <ChatMessage key={message.id} message={message} />
              ))}
              {isStreaming && <TypingMessage modelId={modelId} />}
            </div>
          )}
        </div>

        <Composer
          value={draft}
          onChange={setDraft}
          onSubmit={() => send(draft)}
          onStop={stop}
          isStreaming={isStreaming}
          modelId={modelId}
        />
      </main>
    </div>
  )
}
