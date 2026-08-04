import type { Conversation, Model } from '../types'

export const MODELS: Model[] = [
  {
    id: 'openai/gpt-oss-20b',
    name: 'GPT-OSS 20B',
    provider: 'OpenAI',
    tagline: 'Balanced open-weight model for everyday chat',
    initials: 'OA',
    hue: 158,
    context: '128K',
    speed: 'Fastest',
  },
  {
    id: 'openai/gpt-oss-120b',
    name: 'GPT-OSS 120B',
    provider: 'OpenAI',
    tagline: 'Bigger sibling — stronger reasoning and code',
    initials: 'OA',
    hue: 158,
    context: '128K',
    speed: 'Balanced',
  },
  {
    id: 'llama-3.3-70b-versatile',
    name: 'Llama 3.3 70B',
    provider: 'Meta',
    tagline: 'Versatile generalist with broad world knowledge',
    initials: 'ME',
    hue: 214,
    context: '128K',
    speed: 'Fast',
  },
  {
    id: 'llama-3.1-8b-instant',
    name: 'Llama 3.1 8B',
    provider: 'Meta',
    tagline: 'Tiny and instant — great for quick lookups',
    initials: 'ME',
    hue: 214,
    context: '128K',
    speed: 'Fastest',
  },
  {
    id: 'deepseek-r1-distill-llama-70b',
    name: 'DeepSeek R1 Distill',
    provider: 'DeepSeek',
    tagline: 'Thinks step by step before answering',
    initials: 'DS',
    hue: 266,
    context: '128K',
    speed: 'Deep',
  },
  {
    id: 'qwen/qwen3-32b',
    name: 'Qwen 3 32B',
    provider: 'Alibaba',
    tagline: 'Strong multilingual and structured output',
    initials: 'QW',
    hue: 24,
    context: '131K',
    speed: 'Fast',
  },
  {
    id: 'moonshotai/kimi-k2-instruct',
    name: 'Kimi K2',
    provider: 'Moonshot',
    tagline: 'Agentic tool use and long-form synthesis',
    initials: 'KM',
    hue: 336,
    context: '200K',
    speed: 'Balanced',
  },
  {
    id: 'gemma2-9b-it',
    name: 'Gemma 2 9B',
    provider: 'Google',
    tagline: 'Lightweight instruction-tuned assistant',
    initials: 'GG',
    hue: 44,
    context: '8K',
    speed: 'Fastest',
  },
]

export const DEFAULT_MODEL_ID = MODELS[0].id

export function getModel(id: string): Model {
  return MODELS.find((m) => m.id === id) ?? MODELS[0]
}

/** Placeholder history so the sidebar reads like a real product. */
export const SAMPLE_CONVERSATIONS: Conversation[] = [
  {
    id: 'c1',
    title: 'Deploying FastAPI to AWS App Runner',
    modelId: 'openai/gpt-oss-20b',
    group: 'Today',
  },
  {
    id: 'c2',
    title: 'Explain vector databases simply',
    modelId: 'llama-3.3-70b-versatile',
    group: 'Today',
  },
  {
    id: 'c3',
    title: 'Rewrite my landing page headline',
    modelId: 'moonshotai/kimi-k2-instruct',
    group: 'Yesterday',
  },
  {
    id: 'c4',
    title: 'Debug a CORS preflight failure',
    modelId: 'deepseek-r1-distill-llama-70b',
    group: 'Yesterday',
  },
  {
    id: 'c5',
    title: 'Compare Postgres vs DynamoDB',
    modelId: 'qwen/qwen3-32b',
    group: 'Previous 7 days',
  },
  {
    id: 'c6',
    title: 'Draft release notes for v2.1',
    modelId: 'gemma2-9b-it',
    group: 'Previous 7 days',
  },
]

/** Opening moves, presented as a numbered index rather than a card grid. */
export const SUGGESTIONS = [
  { title: 'Review my code', body: 'Find the bugs in this FastAPI endpoint' },
  { title: 'Brainstorm', body: 'Ten names for an AI note-taking app' },
  { title: 'Explain a concept', body: 'How does JWT authentication actually work' },
  { title: 'Write a draft', body: 'A launch email for our new public API' },
]
