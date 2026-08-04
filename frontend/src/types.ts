export type Role = 'user' | 'assistant'

export interface Message {
  id: string
  role: Role
  content: string
  /** Model id that produced an assistant message. */
  modelId?: string
  createdAt: number
}

export interface Model {
  id: string
  name: string
  provider: string
  tagline: string
  /** Short label shown on the badge, e.g. "OA". */
  initials: string
  /** Hue used for the model's badge + accent dot. */
  hue: number
  context: string
  speed: 'Fastest' | 'Fast' | 'Balanced' | 'Deep'
}

export interface Conversation {
  id: string
  title: string
  modelId: string
  /** Bucket used to group the sidebar list. */
  group: string
}
