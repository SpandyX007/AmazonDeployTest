import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Sidebar } from '../components/Sidebar'
import { ProviderPicker } from '../components/ProviderPicker'
import { ModelPicker } from '../components/ModelPicker'
import { ChatMessage, TypingMessage } from '../components/ChatMessage'
import { Composer } from '../components/Composer'
import { KineticHeadline } from '../components/KineticHeadline'
import { Paywall } from '../components/Paywall'
import { MoonIcon, RetryIcon, SidebarIcon, SunIcon } from '../components/Icons'
import { useAuth } from '../context/auth-context'
import { useBilling } from '../context/billing-context'
import { useTheme } from '../lib/theme'
import * as api from '../lib/api'
import type {
  Conversation,
  Message,
  ModelStamp,
  Provider,
  Selection,
  StoredMessage,
} from '../types'

const SELECTION_KEY = 'nexus.selection'

/** How often a streaming turn repaints — roughly one animation frame. */
const FLUSH_INTERVAL_MS = 60

const UNKNOWN_MODEL: ModelStamp = { name: 'Assistant', provider: '', initials: '··', hue: 0 }

function storedSelection(): Selection | null {
  try {
    const raw = localStorage.getItem(SELECTION_KEY)
    return raw ? (JSON.parse(raw) as Selection) : null
  } catch {
    return null
  }
}

const formatNumber = new Intl.NumberFormat('en-IN')

/**
 * Keeps the choice only if the catalog still offers it — models come and go —
 * and never lands on a locked model: a remembered premium pick from before
 * the account lapsed falls back to the provider's first free one.
 */
function reconcile(providers: Provider[], wanted: Selection | null): Selection | null {
  const usable = providers.filter((p) => p.available && p.models.some((m) => !m.locked))
  if (usable.length === 0) return null

  const firstOpen = (provider: Provider) => provider.models.find((m) => !m.locked)!

  const provider = usable.find((p) => p.id === wanted?.provider)
  if (provider) {
    const model = provider.models.find((m) => m.id === wanted?.model && !m.locked)
    return { provider: provider.id, model: (model ?? firstOpen(provider)).id }
  }

  return { provider: usable[0].id, model: firstOpen(usable[0]).id }
}

/**
 * Ids for turns that exist only in this tab so far. They are replaced with the
 * server's ids as soon as it reports them, because "regenerate" names a stored
 * message — a local id would mean nothing to the backend.
 */
let localCounter = 0
function localId(prefix: string) {
  localCounter += 1
  return `${prefix}-${localCounter}`
}

function toMessage(stored: StoredMessage): Message {
  return {
    id: stored.id,
    role: stored.role === 'assistant' ? 'assistant' : 'user',
    content: stored.content,
    providerId: stored.provider || undefined,
    modelId: stored.model || undefined,
    failed: stored.failed,
    createdAt: new Date(stored.createdAt).getTime(),
  }
}

export function Chat() {
  const { theme, toggle } = useTheme()
  const { user, signOut, signOutEverywhere } = useAuth()
  const { billing, applyUsage, openPaywall } = useBilling()
  const navigate = useNavigate()
  const params = useParams<{ conversationId?: string }>()
  const routeId = params.conversationId ?? null

  const [sidebarOpen, setSidebarOpen] = useState(true)

  const [providers, setProviders] = useState<Provider[]>([])
  const [selection, setSelection] = useState<Selection | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [loadingCatalog, setLoadingCatalog] = useState(true)

  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loadingThreads, setLoadingThreads] = useState(true)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingId, setStreamingId] = useState<string | null>(null)

  const threadRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  /** Which thread the on-screen messages came from — stops the loader from
   *  re-fetching (and clobbering) a thread we just created mid-stream. */
  const hydratedRef = useRef<string | null>(null)
  /** The live thread id. A ref, not state, because a turn started before the
   *  URL changed still has to post into the right conversation. */
  const threadIdRef = useRef<string | null>(routeId)
  const pendingUserRef = useRef<string | null>(null)

  const provider = useMemo(
    () => providers.find((p) => p.id === selection?.provider) ?? null,
    [providers, selection],
  )
  const model = useMemo(
    () => provider?.models.find((m) => m.id === selection?.model) ?? null,
    [provider, selection],
  )

  /** Turns the ids stored on a message into the byline the UI renders. Done at
   *  render time so a thread loaded before the catalog still labels correctly. */
  const stampFor = useCallback(
    (providerId?: string, modelId?: string): ModelStamp => {
      if (!providerId) return UNKNOWN_MODEL
      const source = providers.find((p) => p.id === providerId)
      const named = source?.models.find((m) => m.id === modelId)
      return {
        name: named?.name ?? modelId ?? 'Assistant',
        provider: source?.label ?? providerId,
        initials: source?.initials ?? '··',
        hue: source?.hue ?? 0,
      }
    },
    [providers],
  )

  const liveStamp = useMemo(
    () => stampFor(selection?.provider, selection?.model),
    [stampFor, selection],
  )

  // Keep the newest message in view.
  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, isStreaming])

  useEffect(() => {
    threadIdRef.current = routeId
  }, [routeId])

  // --- catalog -------------------------------------------------------------

  const loadCatalog = useCallback(async (signal?: AbortSignal) => {
    try {
      const catalog = await api.fetchCatalog(signal)
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

  // Locks are decided per account, so a payment landing mid-session means the
  // catalog must be re-read to unlock the premium rows.
  const premiumRef = useRef<boolean | undefined>(undefined)
  useEffect(() => {
    const premium = billing?.isPremium
    if (premium === undefined) return
    if (premiumRef.current !== undefined && premiumRef.current !== premium) void loadCatalog()
    premiumRef.current = premium
  }, [billing?.isPremium, loadCatalog])

  // Remember the choice across reloads.
  useEffect(() => {
    if (selection) localStorage.setItem(SELECTION_KEY, JSON.stringify(selection))
  }, [selection])

  // --- thread list ---------------------------------------------------------

  const refreshThreads = useCallback(async (signal?: AbortSignal) => {
    try {
      setConversations(await api.listConversations(signal))
    } catch {
      // A failed refresh leaves the previous list on screen; the next turn or
      // page load will try again.
    } finally {
      setLoadingThreads(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      await refreshThreads(controller.signal)
    })()
    return () => controller.abort()
  }, [refreshThreads])

  // --- opening a thread ----------------------------------------------------

  /** Replaces the on-screen thread with what the server has stored. */
  const hydrate = useCallback(async (id: string, signal?: AbortSignal) => {
    const detail = await api.fetchConversation(id, signal)
    hydratedRef.current = id
    setMessages(detail.messages.map(toMessage))
    return detail
  }, [])

  useEffect(() => {
    if (!routeId) {
      // Back to a blank thread.
      if (hydratedRef.current !== null) {
        hydratedRef.current = null
        setMessages([])
      }
      return
    }

    // Already showing it — including the thread this tab just created, whose
    // id was claimed the moment the stream's `meta` event arrived.
    if (hydratedRef.current === routeId) return

    const controller = new AbortController()
    void (async () => {
      try {
        const detail = await hydrate(routeId, controller.signal)
        // Reopening a thread restores the model it was last answered with.
        if (detail.provider && detail.model) {
          setSelection((current) =>
            reconcile(providers, { provider: detail.provider, model: detail.model }) ?? current,
          )
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') return
        // Deleted, or never ours — fall back to a fresh thread.
        navigate('/chat', { replace: true })
      }
    })()

    return () => controller.abort()
    // `providers` is deliberately absent: it changes after the catalog loads,
    // and re-running this would refetch a thread that is already on screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeId, hydrate, navigate])

  // Abort any in-flight turn when the page unmounts.
  useEffect(() => () => abortRef.current?.abort(), [])

  // --- one turn ------------------------------------------------------------

  const runTurn = useCallback(
    async (activeSelection: Selection, content: string, regenerateFrom: string | null) => {
      const assistantId = localId('a')
      const controller = new AbortController()
      abortRef.current = controller

      setIsStreaming(true)
      setStreamingId(assistantId)

      // Absolute (not appended) content, so a replayed updater stays correct.
      let text = ''
      const write = (body: string, failed = false) =>
        setMessages((prev) => {
          const index = prev.findIndex((m) => m.id === assistantId)
          if (index === -1) {
            return [
              ...prev,
              {
                id: assistantId,
                role: 'assistant',
                content: body,
                providerId: activeSelection.provider,
                modelId: activeSelection.model,
                failed,
                createdAt: Date.now(),
              },
            ]
          }
          const next = [...prev]
          next[index] = { ...next[index], content: body, failed }
          return next
        })

      // Repainting per token would re-parse the whole markdown tree each time,
      // which grows quadratically on a long answer. Coalesce into frames.
      let flushTimer: number | undefined
      const cancelFlush = () => {
        window.clearTimeout(flushTimer)
        flushTimer = undefined
      }
      const scheduleFlush = () => {
        if (flushTimer !== undefined) return
        flushTimer = window.setTimeout(() => {
          flushTimer = undefined
          write(text)
        }, FLUSH_INTERVAL_MS)
      }

      // Boxed so the assignment inside the callback is visible afterwards.
      const outcome: { stored: StoredMessage | null; refused: boolean } = {
        stored: null,
        refused: false,
      }

      try {
        await api.streamChat({
          selection: activeSelection,
          conversationId: threadIdRef.current,
          content,
          regenerateFrom,
          signal: controller.signal,
          onMeta: (meta) => {
            threadIdRef.current = meta.conversationId
            hydratedRef.current = meta.conversationId

            if (meta.userMessage) {
              const storedId = meta.userMessage.id
              const optimisticId = pendingUserRef.current
              pendingUserRef.current = null
              if (optimisticId) {
                setMessages((prev) =>
                  prev.map((m) => (m.id === optimisticId ? { ...m, id: storedId } : m)),
                )
              }
            }

            // The thread now has a URL — swap it in without a history entry, so
            // Back still leaves the workspace rather than un-naming the thread.
            if (meta.isNew) navigate(`/chat/${meta.conversationId}`, { replace: true })
          },
          onToken: (chunk) => {
            text += chunk
            scheduleFlush()
          },
          onDone: (done) => {
            outcome.stored = done.message
            if (done.usage) applyUsage(done.usage)
          },
        })
        cancelFlush()
        write(text)
      } catch (error) {
        cancelFlush()
        const failure = error as Error
        if (failure.name === 'AbortError') {
          // A user-initiated stop keeps whatever streamed in already.
          write(text)
        } else if (failure instanceof api.ApiError && failure.isPaywall) {
          // Refused before anything was written: no turn to show, just the
          // paywall — and take the optimistic question back off the screen.
          outcome.refused = true
          openPaywall(failure.reason!)
        } else {
          write(text ? `${text}\n\n${failure.message}` : failure.message, true)
        }
      } finally {
        abortRef.current = null
        setIsStreaming(false)
        setStreamingId(null)

        const stored = outcome.stored
        const optimisticId = outcome.refused ? pendingUserRef.current : null
        if (optimisticId) {
          // Refused before the question was stored: take it back off the
          // screen and put it back in the composer for after the top-up.
          pendingUserRef.current = null
          setMessages((prev) => prev.filter((m) => m.id !== optimisticId))
          if (content) setDraft(content)
        } else if (stored) {
          // Adopt the server's id last, after the final write has landed.
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, id: stored.id } : m)),
          )
        } else if (threadIdRef.current) {
          // Stopped or errored: we never learned the stored ids, so re-read the
          // thread rather than leave the view and the database out of step.
          void api
            .fetchConversation(threadIdRef.current)
            .then((detail) => {
              hydratedRef.current = detail.id
              setMessages(detail.messages.map(toMessage))
            })
            .catch(() => undefined)
        }

        void refreshThreads()
      }
    },
    [navigate, refreshThreads, applyUsage, openPaywall],
  )

  function send(raw: string) {
    const content = raw.trim()
    if (!content || isStreaming || !selection) return

    const optimisticId = localId('u')
    pendingUserRef.current = optimisticId
    setMessages((prev) => [
      ...prev,
      { id: optimisticId, role: 'user', content, createdAt: Date.now() },
    ])
    setDraft('')
    void runTurn(selection, content, null)
  }

  /** Drops the given assistant turn (and anything after it) and asks again. */
  function regenerate(target: Message) {
    if (isStreaming || !selection || !threadIdRef.current) return

    const index = messages.findIndex((m) => m.id === target.id)
    if (index <= 0) return

    setMessages(messages.slice(0, index))
    void runTurn(selection, '', target.id)
  }

  function stop() {
    abortRef.current?.abort()
  }

  function newChat() {
    stop()
    setMessages([])
    setDraft('')
    threadIdRef.current = null
    hydratedRef.current = null
    navigate('/chat')
  }

  function openThread(id: string) {
    if (id === routeId) return
    stop()
    navigate(`/chat/${id}`)
  }

  async function removeThread(conversation: Conversation) {
    if (!window.confirm(`Delete "${conversation.title}"? This cannot be undone.`)) return

    try {
      await api.deleteConversation(conversation.id)
    } catch {
      return
    }

    setConversations((prev) => prev.filter((c) => c.id !== conversation.id))
    if (threadIdRef.current === conversation.id) newChat()
  }

  async function leave(everywhere: boolean) {
    stop()
    await (everywhere ? signOutEverywhere() : signOut())
    navigate('/', { replace: true })
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
        conversations={conversations}
        activeId={routeId}
        loading={loadingThreads}
        user={user}
        onSelect={openThread}
        onNewChat={newChat}
        onDelete={removeThread}
        onClose={() => setSidebarOpen(false)}
        onSignOut={() => void leave(false)}
        onSignOutEverywhere={() => void leave(true)}
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
              onLocked={() => openPaywall('model_locked')}
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
            {billing && (
              <span className={`readout-cell ${billing.balance <= 0 ? 'is-alert' : ''}`}>
                <em>credits</em>
                {formatNumber.format(Math.max(billing.balance, 0))}
              </span>
            )}
            <span className="readout-cell">
              <span className={`pulse ${isStreaming ? 'is-live' : ''}`} />
              {isStreaming ? 'generating' : 'ready'}
            </span>
          </div>

          <button
            type="button"
            className="icon-btn"
            onClick={toggle}
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
                <span>{user ? `Signed in as ${user.name.split(' ')[0]}` : 'AI Workspace'}</span>
                <span className="tick" />
                <span>
                  {providers.filter((p) => p.available).length} providers ·{' '}
                  {providers.reduce((total, p) => total + p.models.length, 0)} models online
                </span>
              </p>

              <KineticHeadline
                text="Ask anything. Switch minds mid-thought."
                className="welcome-title"
              />

              <p className="welcome-sub">
                One thread, every provider. This conversation is saved to your account, so the
                model picks up exactly where you left it — on any device.
              </p>
            </section>
          ) : (
            <div className="messages">
              {messages.map((message) => (
                <ChatMessage
                  key={message.id}
                  message={message}
                  model={stampFor(message.providerId, message.modelId)}
                  onCopy={(m) => void navigator.clipboard?.writeText(m.content)}
                  onRetry={regenerate}
                />
              ))}
              {awaitingFirstToken && <TypingMessage model={liveStamp} />}
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

      <Paywall />
    </div>
  )
}
