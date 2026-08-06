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
  /** Present on assistant messages. */
  model?: ModelStamp
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

export interface Conversation {
  id: string
  title: string
  /** Hue used for the conversation dot. */
  hue: number
  /** Bucket used to group the sidebar list. */
  group: string
}
