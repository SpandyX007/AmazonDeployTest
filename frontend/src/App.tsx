import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Sidebar } from './components/Sidebar'
import { ProviderPicker } from './components/ProviderPicker'
import { ModelPicker } from './components/ModelPicker'
import { ChatMessage, TypingMessage } from './components/ChatMessage'
import { Composer } from './components/Composer'
import { MoonIcon, RetryIcon, SidebarIcon, SunIcon } from './components/Icons'
import { fetchCatalog, streamChat } from './lib/api'
import type { Message, ModelStamp, Provider, Selection } from './types'
import './App.css'

type Theme = 'light' | 'dark'

const SELECTION_KEY = 'nexus.selection'

function preferredTheme(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function storedSelection(): Selection | null {
  try {
    const raw = localStorage.getItem(SELECTION_KEY)
    return raw ? (JSON.parse(raw) as Selection) : null
  } catch {
    return null
  }
}

/** Keeps the choice only if the catalog still offers it — models come and go. */
function reconcile(providers: Provider[], wanted: Selection | null): Selection | null {
  const usable = providers.filter((p) => p.available && p.models.length > 0)
  if (usable.length === 0) return null

  const provider = usable.find((p) => p.id === wanted?.provider)
  if (provider) {
    const model = provider.models.find((m) => m.id === wanted?.model) ?? provider.models[0]
    return { provider: provider.id, model: model.id }
  }

  return { provider: usable[0].id, model: usable[0].models[0].id }
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

  const [providers, setProviders] = useState<Provider[]>([])
  const [selection, setSelection] = useState<Selection | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [loadingCatalog, setLoadingCatalog] = useState(true)

  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingId, setStreamingId] = useState<string | null>(null)

  const threadRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const provider = useMemo(
    () => providers.find((p) => p.id === selection?.provider) ?? null,
    [providers, selection],
  )
  const model = useMemo(
    () => provider?.models.find((m) => m.id === selection?.model) ?? null,
    [provider, selection],
  )

  const stamp: ModelStamp = useMemo(
    () => ({
      name: model?.name ?? 'Assistant',
      provider: provider?.label ?? '',
      initials: provider?.initials ?? '··',
      hue: provider?.hue ?? 0,
    }),
    [model, provider],
  )

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

  const loadCatalog = useCallback(async (signal?: AbortSignal) => {
    try {
      const catalog = await fetchCatalog(signal)
      setProviders(catalog.providers)
      setSelection((current) => reconcile(catalog.providers, current ?? storedSelection()))
      setCatalogError(
        catalog.providers.some((p) => p.available)
          ? null
          : 'No provider is configured. Add an API key to backend/.env, or start Ollama.',
      )
    } catch (error) {
      if ((error as Error).name === 'AbortError') return
      setCatalogError(`Could not reach the backend — ${(error as Error).message}`)
    } finally {
      setLoadingCatalog(false)
    }
  }, [])

  /** Manual refresh — picks up an Ollama daemon or a key added after boot. */
  const refreshCatalog = useCallback(() => {
    setLoadingCatalog(true)
    void loadCatalog()
  }, [loadCatalog])

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      await loadCatalog(controller.signal)
    })()
    return () => controller.abort()
  }, [loadCatalog])

  // Remember the choice across reloads.
  useEffect(() => {
    if (selection) localStorage.setItem(SELECTION_KEY, JSON.stringify(selection))
  }, [selection])

  // Abort any in-flight turn when the app unmounts.
  useEffect(() => () => abortRef.current?.abort(), [])

  /** Runs one assistant turn against `history` and streams it into the thread. */
  const runTurn = useCallback(
    async (history: Message[], activeSelection: Selection, activeStamp: ModelStamp) => {
      const assistantId = nextId()
      const controller = new AbortController()
      abortRef.current = controller

      setIsStreaming(true)
      setStreamingId(assistantId)

      // Absolute (not appended) content, so a replayed updater stays correct.
      let text = ''
      const write = (content: string, failed = false) =>
        setMessages((prev) => {
          const index = prev.findIndex((m) => m.id === assistantId)
          const message: Message = {
            id: assistantId,
            role: 'assistant',
            content,
            model: activeStamp,
            failed,
            createdAt: Date.now(),
          }
          if (index === -1) return [...prev, message]
          const next = [...prev]
          next[index] = { ...next[index], content, failed }
          return next
        })

      try {
        await streamChat({
          selection: activeSelection,
          messages: history,
          signal: controller.signal,
          onToken: (chunk) => {
            text += chunk
            write(text)
          },
        })
      } catch (error) {
        const err = error as Error
        // A user-initiated stop keeps whatever streamed in already.
        if (err.name !== 'AbortError') write(text ? `${text}\n\n${err.message}` : err.message, true)
      } finally {
        abortRef.current = null
        setIsStreaming(false)
        setStreamingId(null)
      }
    },
    [],
  )

  function send(raw: string) {
    const content = raw.trim()
    if (!content || isStreaming || !selection) return

    const userMessage: Message = { id: nextId(), role: 'user', content, createdAt: Date.now() }
    const history = [...messages, userMessage]

    setMessages(history)
    setDraft('')
    void runTurn(history, selection, stamp)
  }

  /** Drops the given assistant turn and asks again from the same history. */
  function regenerate(target: Message) {
    if (isStreaming || !selection) return

    const index = messages.findIndex((m) => m.id === target.id)
    if (index === -1) return

    const history = messages.slice(0, index)
    if (history.length === 0) return

    setMessages(history)
    void runTurn(history, selection, stamp)
  }

  function stop() {
    abortRef.current?.abort()
  }

  function newChat() {
    stop()
    setMessages([])
    setDraft('')
    setActiveConversation(null)
  }

  function pickProvider(next: Provider) {
    if (!next.available || next.models.length === 0) return
    setSelection({ provider: next.id, model: next.models[0].id })
  }

  const isEmpty = messages.length === 0
  const awaitingFirstToken = isStreaming && !messages.some((m) => m.id === streamingId)

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
            <ModelPicker
              provider={provider}
              selectedId={selection?.model ?? null}
              onSelect={(modelId) =>
                setSelection((current) => (current ? { ...current, model: modelId } : current))
              }
            />
            <ProviderPicker
              providers={providers}
              selectedId={selection?.provider ?? null}
              onSelect={pickProvider}
            />
            <button
              type="button"
              className={`icon-btn refresh-btn ${loadingCatalog ? 'is-busy' : ''}`}
              onClick={refreshCatalog}
              aria-label="Reload providers"
              title="Reload providers"
            >
              <RetryIcon />
            </button>
          </div>

          {/* Instrument rail — mono readout of the live session. */}
          <div className="readout" aria-hidden="true">
            <span className="readout-cell">
              <em>ctx</em>
              {model?.context ?? '—'}
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

        {catalogError && (
          <div className="banner" role="status">
            <span>{catalogError}</span>
            <button type="button" onClick={refreshCatalog}>
              Retry
            </button>
          </div>
        )}

        <div className={`thread ${isEmpty ? 'is-empty' : ''}`} ref={threadRef}>
          {isEmpty ? (
            <section className="welcome">
              <p className="label welcome-eyebrow">
                <span>AI Workspace</span>
                <span className="tick" />
                <span>
                  {providers.filter((p) => p.available).length} providers ·{' '}
                  {providers.reduce((total, p) => total + p.models.length, 0)} models online
                </span>
              </p>

              <KineticHeadline text="Ask anything. Switch minds mid-thought." />

              <p className="welcome-sub">
                One thread, every provider. Pick the mind that fits the question —
                the conversation carries over.
              </p>
            </section>
          ) : (
            <div className="messages">
              {messages.map((message) => (
                <ChatMessage
                  key={message.id}
                  message={message}
                  onCopy={(m) => void navigator.clipboard?.writeText(m.content)}
                  onRetry={regenerate}
                />
              ))}
              {awaitingFirstToken && <TypingMessage model={stamp} />}
            </div>
          )}
        </div>

        <Composer
          value={draft}
          onChange={setDraft}
          onSubmit={() => send(draft)}
          onStop={stop}
          isStreaming={isStreaming}
          modelName={model?.name ?? 'a model'}
          disabled={!selection}
        />
      </main>
    </div>
  )
}
