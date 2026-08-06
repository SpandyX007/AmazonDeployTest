import type { Catalog, Message, Selection } from '../types'

/**
 * Empty by default: Vite proxies /api to the backend in dev (vite.config.ts),
 * and in production both are served from the same origin. Override with
 * VITE_API_BASE when the API lives somewhere else.
 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

async function failure(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    /* fall through to the status line */
  }
  return `${response.status} ${response.statusText}`
}

/** Providers, their models, and which one to select on first load. */
export async function fetchCatalog(signal?: AbortSignal): Promise<Catalog> {
  const response = await fetch(`${API_BASE}/api/providers`, { signal })
  if (!response.ok) throw new Error(await failure(response))
  return response.json()
}

interface StreamOptions {
  selection: Selection
  messages: Message[]
  onToken: (text: string) => void
  signal: AbortSignal
}

/**
 * Streams one assistant turn, calling `onToken` per chunk.
 * Resolves when the stream ends; rejects on transport or provider errors.
 */
export async function streamChat({ selection, messages, onToken, signal }: StreamOptions) {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({
      provider: selection.provider,
      model: selection.model,
      messages: messages.map(({ role, content }) => ({ role, content })),
    }),
  })

  if (!response.ok) throw new Error(await failure(response))
  if (!response.body) throw new Error('The server returned an empty stream')

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
      else if (event === 'error') throw new Error(payload.message)
    }
  }
}
