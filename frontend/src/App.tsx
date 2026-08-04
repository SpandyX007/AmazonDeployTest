import { useEffect, useRef, useState } from 'react'
import { Sidebar } from './components/Sidebar'
import { ModelPicker } from './components/ModelPicker'
import { ChatMessage, TypingMessage } from './components/ChatMessage'
import { Composer } from './components/Composer'
import { MoonIcon, SidebarIcon, SunIcon } from './components/Icons'
import { SUGGESTION_ICONS } from './components/suggestionIcons'
import { DEFAULT_MODEL_ID, SUGGESTIONS, getModel } from './data/models'
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
      const model = getModel(modelId)
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
            `the real reply will stream into this bubble.`,
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
      <Sidebar
        open={sidebarOpen}
        activeId={activeConversation}
        onSelect={setActiveConversation}
        onNewChat={newChat}
        onClose={() => setSidebarOpen(false)}
      />

      <div
        className="scrim"
        onClick={() => setSidebarOpen(false)}
        aria-hidden={!sidebarOpen}
      />

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
            <div className="welcome">
              <span className="welcome-glow" aria-hidden="true" />
              <h1 className="welcome-title">What can I help you build?</h1>
              <p className="welcome-sub">
                Pick a model above, then start the conversation. You can switch models
                at any point without losing the thread.
              </p>

              <div className="suggestions">
                {SUGGESTIONS.map((item) => {
                  const Icon = SUGGESTION_ICONS[item.icon]
                  return (
                    <button
                      type="button"
                      key={item.title}
                      className="suggestion"
                      onClick={() => send(item.body)}
                    >
                      <Icon className="suggestion-icon" />
                      <span className="suggestion-title">{item.title}</span>
                      <span className="suggestion-body">{item.body}</span>
                    </button>
                  )
                })}
              </div>
            </div>
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
