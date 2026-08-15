export type Role = 'user' | 'assistant'

/** Model stamp copied onto an assistant message so its byline survives a switch. */
export interface ModelStamp {
  name: string
  provider: string
  initials: string
  hue: number
}

export interface Message {
  id: string
  role: Role
  content: string
  /** Which mind produced it. Stored as ids, not as a display stamp, so a
   *  reloaded thread renders correctly once the catalog arrives. */
  providerId?: string
  modelId?: string
  /** Set when the turn failed — rendered as a notice instead of prose. */
  failed?: boolean
  createdAt: number
}

/** One selectable model, as described by GET /api/providers. */
export interface Model {
  id: string
  name: string
  tagline: string
  context: string
  speed: 'Fastest' | 'Fast' | 'Balanced' | 'Deep'
}

/** One LLM vendor and everything the UI needs to render it. */
export interface Provider {
  id: string
  label: string
  /** Two-letter badge, e.g. "GQ". */
  initials: string
  /** Hue used for the provider's badge + accent dot. */
  hue: number
  available: boolean
  /** Why it is unavailable, when it is. */
  detail: string
  /** What to do about it, e.g. "Add GROQ_API_KEY to backend/.env". */
  setupHint: string
  models: Model[]
}

export interface Catalog {
  providers: Provider[]
  default: Selection | null
}

export interface Selection {
  provider: string
  model: string
}

/** The signed-in account. Carries nothing secret. */
export interface User {
  id: string
  name: string
  email: string
  initials: string
  createdAt: string
}

/** What sign-up, sign-in, and refresh all return. */
export interface TokenResponse {
  /** A JWT. Held in memory only — see lib/api.ts. */
  accessToken: string
  tokenType: string
  /** Seconds until it expires; the client renews just before. */
  expiresIn: number
  user: User
}

/** One live sign-in, from GET /api/auth/sessions. The id is the refresh
 *  family — a session is a chain of rotated tokens, and the family is the
 *  only id that stays stable across refreshes. */
export interface AuthSession {
  id: string
  current: boolean
  startedAt: string
  refreshedAt: string
  expiresAt: string
  userAgent: string
  ip: string
}

/** A thread as the sidebar knows it — no messages, just the spine. */
export interface Conversation {
  id: string
  title: string
  provider: string
  model: string
  messageCount: number
  createdAt: string
  updatedAt: string
}

/** One stored turn, as the server returns it. */
export interface StoredMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  provider: string
  model: string
  failed: boolean
  createdAt: string
}

export interface ConversationDetail extends Conversation {
  systemPrompt: string
  messages: StoredMessage[]
}
