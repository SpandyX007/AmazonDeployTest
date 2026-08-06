import type { Conversation } from '../types'

/**
 * Providers and models now come from the backend catalog (GET /api/providers),
 * so the only thing left here is placeholder history for the sidebar.
 */
export const SAMPLE_CONVERSATIONS: Conversation[] = [
  { id: 'c1', title: 'Deploying FastAPI to AWS App Runner', hue: 158, group: 'Today' },
  { id: 'c2', title: 'Explain vector databases simply', hue: 214, group: 'Today' },
  { id: 'c3', title: 'Rewrite my landing page headline', hue: 336, group: 'Yesterday' },
  { id: 'c4', title: 'Debug a CORS preflight failure', hue: 266, group: 'Yesterday' },
  { id: 'c5', title: 'Compare Postgres vs DynamoDB', hue: 24, group: 'Previous 7 days' },
  { id: 'c6', title: 'Draft release notes for v2.1', hue: 44, group: 'Previous 7 days' },
]
