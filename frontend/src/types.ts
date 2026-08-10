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

/** The signed-in account. Never includes anything secret — the session token
 *  lives in an httpOnly cookie this code cannot read. */
export interface User {
  id: string
  name: string
  email: string
  initials: string
  createdAt: string
}

/** One signed-in browser, from GET /api/auth/sessions. */
export interface AuthSession {
  id: string
  current: boolean
  createdAt: string
  lastSeenAt: string
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
