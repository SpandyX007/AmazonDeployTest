import type {
  Billing,
  Catalog,
  Conversation,
  ConversationDetail,
  CreditEntry,
  PaymentRequest,
  Selection,
  StoredMessage,
  TokenResponse,
  TurnUsage,
  User,
} from '../types'

/**
 * Empty by default: Vite proxies /api to the backend in dev (vite.config.ts),
 * and in production both are served from the same origin. Override with
 * VITE_API_BASE when the API lives somewhere else.
 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

/**
 * Only /api/auth/* needs this — the refresh cookie is path-scoped, so the
 * browser will not attach it to a chat request even when asked to. Setting it
 * everywhere costs nothing and means a cross-origin deployment works without
 * a second rule.
 */
const CREDENTIALS: RequestCredentials = 'include'

/** Refresh this far before `exp`, so a token cannot die mid-flight. */
const REFRESH_SKEW_MS = 30_000

/**
 * Machine-readable refusals the UI reacts to specifically — a paywall for one,
 * an upgrade prompt for the other. Anything else is shown as plain text.
 */
export type ApiReason = 'insufficient_credits' | 'model_locked'

export class ApiError extends Error {
  readonly status: number
  readonly reason: ApiReason | null

  constructor(message: string, status: number, reason: ApiReason | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.reason = reason
  }

  /** True for the two errors that mean "pay", not "something broke". */
  get isPaywall(): boolean {
    return this.reason === 'insufficient_credits' || this.reason === 'model_locked'
  }
}

// --- the access token ------------------------------------------------------

/**
 * Deliberately a module variable and not localStorage.
 *
 * A token in storage is readable by any script that reaches the page, and it
 * outlives the tab — so a token stolen once keeps working. Here it dies with
 * the JavaScript context: closing the tab drops it, and nothing on disk can be
 * scraped. The cost is that a page reload starts with no token, which is
 * exactly what the refresh call below is for.
 */
let accessToken: string | null = null
let accessExpiresAt = 0

function adoptSession(session: TokenResponse): TokenResponse {
  accessToken = session.accessToken
  accessExpiresAt = Date.now() + session.expiresIn * 1000
  return session
}

export function clearSession() {
  accessToken = null
  accessExpiresAt = 0
}

/**
 * Fires when the server rejects a call and a refresh could not rescue it —
 * the session was revoked, expired, or signed out from another device.
 * AuthProvider registers a handler that drops local state.
 */
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

// --- refresh ---------------------------------------------------------------

let refreshInFlight: Promise<TokenResponse | null> | null = null

async function requestRefresh(): Promise<TokenResponse | null> {
  const response = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: 'POST',
    credentials: CREDENTIALS,
  })

  if (!response.ok) {
    clearSession()
    return null
  }

  return adoptSession((await response.json()) as TokenResponse)
}

/**
 * Trade the refresh cookie for a new access token.
 *
 * Single-flight on purpose: when a token expires, every request in flight
 * fails at once, and each would otherwise start its own refresh. Since every
 * refresh *rotates* the token, a burst of them would spend each other's
 * successors and the server would read the pile-up as a stolen token being
 * replayed. One shared promise means one rotation.
 */
export function refreshSession(): Promise<TokenResponse | null> {
  if (!refreshInFlight) {
    refreshInFlight = requestRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

// --- the authenticated fetch ----------------------------------------------

async function authorizedFetch(
  path: string,
  init: RequestInit = {},
  mayRetry = true,
): Promise<Response> {
  // Proactive: renew a token that is about to expire rather than spend a
  // round-trip finding out it did.
  if (accessToken && Date.now() > accessExpiresAt - REFRESH_SKEW_MS) {
    await refreshSession()
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: CREDENTIALS,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...init.headers,
    },
  })

  // Reactive: the clock skewed, or the token died between the check and the
  // server reading it. One refresh, one retry, then give up — a 401 that
  // survives a fresh token is a real rejection, not a stale one.
  if (response.status === 401 && mayRetry) {
    const renewed = await refreshSession()
    if (renewed) return authorizedFetch(path, init, false)
  }

  return response
}

async function failure(response: Response): Promise<ApiError> {
  try {
    const body = await response.json()
    const detail = body?.detail
    if (typeof detail === 'string') return new ApiError(detail, response.status)
    // FastAPI validation errors arrive as a list of field problems.
    if (Array.isArray(detail) && detail[0]?.msg) return new ApiError(detail[0].msg, response.status)
    // Our own structured refusals: { reason, message, ...context }.
    if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
      const reason = detail.reason
      const known = reason === 'insufficient_credits' || reason === 'model_locked'
      return new ApiError(detail.message, response.status, known ? reason : null)
    }
  } catch {
    /* fall through to the status line */
  }
  return new ApiError(`${response.status} ${response.statusText}`, response.status)
}

interface RequestOptions extends RequestInit {
  /** Skip the global sign-out handler — for calls whose whole job is to find
   *  out whether we are signed in. */
  expect401?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { expect401, ...init } = options
  const response = await authorizedFetch(path, init)

  if (response.status === 401 && !expect401) onUnauthorized?.()
  if (!response.ok) throw await failure(response)

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

export async function signup(input: {
  name: string
  email: string
  password: string
}): Promise<TokenResponse> {
  return adoptSession(
    await request<TokenResponse>('/api/auth/signup', { method: 'POST', body: json(input) }),
  )
}

export async function login(input: {
  email: string
  password: string
}): Promise<TokenResponse> {
  return adoptSession(
    await request<TokenResponse>('/api/auth/login', { method: 'POST', body: json(input) }),
  )
}

export function fetchMe(signal?: AbortSignal): Promise<User> {
  return request<User>('/api/auth/me', { signal })
}

export async function logout(): Promise<void> {
  try {
    await request<void>('/api/auth/logout', { method: 'POST', expect401: true })
  } finally {
    clearSession()
  }
}

export async function logoutEverywhere(): Promise<void> {
  try {
    await request<void>('/api/auth/logout-all', { method: 'POST', expect401: true })
  } finally {
    clearSession()
  }
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

// --- billing ---------------------------------------------------------------

export function fetchBilling(signal?: AbortSignal): Promise<Billing> {
  return request<Billing>('/api/billing/me', { signal })
}

export function fetchCreditHistory(limit = 50, signal?: AbortSignal): Promise<CreditEntry[]> {
  return request<CreditEntry[]>(`/api/billing/history?limit=${limit}`, { signal })
}

/** "I paid the QR" — records the claim; the owner verifies it by hand. */
export function submitPayment(input: { reference: string; note?: string }): Promise<PaymentRequest> {
  return request<PaymentRequest>('/api/billing/payments', {
    method: 'POST',
    body: json({ reference: input.reference, note: input.note ?? '' }),
  })
}

/** The QR image is public (an <img> cannot carry a bearer token). */
export function qrImageUrl(path: string): string {
  return `${API_BASE}${path}`
}

// --- chat ------------------------------------------------------------------

/** Sent once, before any token — carries the thread id for a brand-new chat. */
export interface StreamMeta {
  conversationId: string
  title: string
  isNew: boolean
  userMessage: StoredMessage | null
}

/** Sent last — the assistant turn as it was stored, and what it cost. */
export interface StreamDone {
  conversationId: string
  message: StoredMessage | null
  /** Null when nothing was charged (the request never reached the vendor). */
  usage: TurnUsage | null
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
 * account named by the access token. Resolves when the stream ends; rejects on
 * transport or provider errors.
 *
 * Retrying this after a refresh is safe: a request rejected at the auth check
 * never reached the database, so nothing was written to replay.
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
  const response = await authorizedFetch('/api/chat/stream', {
    method: 'POST',
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
  if (!response.ok) throw await failure(response)
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
