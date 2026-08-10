import type {
  Catalog,
  Conversation,
  ConversationDetail,
  Selection,
  StoredMessage,
  User,
} from '../types'

/**
 * Empty by default: Vite proxies /api to the backend in dev (vite.config.ts),
 * and in production both are served from the same origin. Override with
 * VITE_API_BASE when the API lives somewhere else.
 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

/**
 * The session cookie is httpOnly, so nothing here ever sees or sends a token
 * by hand — `credentials: 'include'` is the whole authentication story on this
 * side. It also means a cross-origin deployment needs ALLOWED_ORIGINS set on
 * the backend; browsers refuse to send credentials to a wildcard origin.
 */
const CREDENTIALS: RequestCredentials = 'include'

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * Fires when the server rejects a call as unauthenticated — the cookie expired,
 * or the session was revoked from another device. AuthProvider registers a
 * handler that drops local state so the UI falls back to the login screen,
 * rather than every caller having to check for 401 itself.
 */
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

async function failure(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') return body.detail
    // FastAPI validation errors arrive as a list of field problems.
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return body.detail[0].msg
  } catch {
    /* fall through to the status line */
  }
  return `${response.status} ${response.statusText}`
}

interface RequestOptions extends RequestInit {
  /** Skip the global sign-out handler — used by calls whose whole job is to
   *  find out whether we are signed in. */
  expect401?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { expect401, body, headers, ...init } = options

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: CREDENTIALS,
    headers: body ? { 'Content-Type': 'application/json', ...headers } : headers,
    body,
  })

  if (response.status === 401 && !expect401) onUnauthorized?.()
  if (!response.ok) throw new ApiError(await failure(response), response.status)

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const json = (payload: unknown) => JSON.stringify(payload)

// --- catalog ---------------------------------------------------------------

/** Providers, their models, and which one to select on first load. */
export function fetchCatalog(signal?: AbortSignal): Promise<Catalog> {
  return request<Catalog>('/api/providers', { signal })
}

// --- auth ------------------------------------------------------------------

export function signup(input: { name: string; email: string; password: string }): Promise<User> {
  return request<User>('/api/auth/signup', { method: 'POST', body: json(input) })
}

export function login(input: { email: string; password: string }): Promise<User> {
  return request<User>('/api/auth/login', { method: 'POST', body: json(input) })
}

/** Resolves to null when there is no live session — the app's boot check. */
export async function fetchMe(signal?: AbortSignal): Promise<User | null> {
  try {
    return await request<User>('/api/auth/me', { signal, expect401: true })
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

export function logout(): Promise<void> {
  return request<void>('/api/auth/logout', { method: 'POST' })
}

export function logoutEverywhere(): Promise<void> {
  return request<void>('/api/auth/logout-all', { method: 'POST' })
}

// --- conversations ---------------------------------------------------------

export function listConversations(signal?: AbortSignal): Promise<Conversation[]> {
  return request<Conversation[]>('/api/conversations', { signal })
}

export function fetchConversation(id: string, signal?: AbortSignal): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/api/conversations/${id}`, { signal })
}

export function renameConversation(id: string, title: string): Promise<Conversation> {
  return request<Conversation>(`/api/conversations/${id}`, {
    method: 'PATCH',
    body: json({ title }),
  })
}

export function deleteConversation(id: string): Promise<void> {
  return request<void>(`/api/conversations/${id}`, { method: 'DELETE' })
}

// --- chat ------------------------------------------------------------------

/** Sent once, before any token — carries the thread id for a brand-new chat. */
export interface StreamMeta {
  conversationId: string
  title: string
  isNew: boolean
  userMessage: StoredMessage | null
}

/** Sent last — the assistant turn as it was stored. */
export interface StreamDone {
  conversationId: string
  message: StoredMessage | null
}

interface StreamOptions {
  selection: Selection
  /** Omit to start a new thread; the `meta` event returns the id. */
  conversationId: string | null
  content: string
  /** Id of an assistant message to redo — it and everything after it are
   *  dropped server-side before the question is asked again. */
  regenerateFrom?: string | null
  onMeta?: (meta: StreamMeta) => void
  onToken: (text: string) => void
  onDone?: (done: StreamDone) => void
  signal: AbortSignal
}

/**
 * Streams one assistant turn.
 *
 * Only the new message goes up — history lives on the server, keyed to the
 * signed-in account. Resolves when the stream ends; rejects on transport or
 * provider errors.
 */
export async function streamChat({
  selection,
  conversationId,
  content,
  regenerateFrom = null,
  onMeta,
  onToken,
  onDone,
  signal,
}: StreamOptions) {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: 'POST',
    credentials: CREDENTIALS,
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: json({
      provider: selection.provider,
      model: selection.model,
      conversationId,
      content,
      regenerateFrom,
    }),
  })

  if (response.status === 401) onUnauthorized?.()
  if (!response.ok) throw new ApiError(await failure(response), response.status)
  if (!response.body) throw new ApiError('The server returned an empty stream', 502)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // SSE frames are separated by a blank line; keep any partial tail.
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      let event = 'message'
      let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue

      const payload = JSON.parse(data)
      if (event === 'token') onToken(payload.text)
      else if (event === 'meta') onMeta?.(payload as StreamMeta)
      else if (event === 'done') onDone?.(payload as StreamDone)
      else if (event === 'error') throw new ApiError(payload.message, 502)
    }
  }
}
