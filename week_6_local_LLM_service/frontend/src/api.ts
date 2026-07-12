export type Role = 'user' | 'assistant' | 'system'

export interface Message {
  role: Role
  content: string
}

export interface Source {
  title: string
  score: number
}

export interface ChatResult {
  reply: string
  sources: Source[]
}

interface ChatRequestDto {
  messages: Message[]
  stream?: boolean
}

interface ChatResponseDto {
  reply: string
  sources?: Source[]
}

interface ErrorDto {
  error: { code: string; message: string }
}

export async function sendChat(messages: Message[]): Promise<ChatResult> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages } satisfies ChatRequestDto),
  })

  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ErrorDto | null
    throw new Error(body?.error?.message ?? `Request failed: ${res.status}`)
  }

  const data = (await res.json()) as ChatResponseDto
  return { reply: data.reply, sources: data.sources ?? [] }
}

/** Callbacks invoked as a streamed reply arrives. */
export interface StreamHandlers {
  onToken: (text: string) => void
  onSources: (sources: Source[]) => void
}

/**
 * Streams a chat reply via Server-Sent Events (`stream: true`).
 *
 * Tokens are delivered to `onToken` as they arrive; `onSources` fires once at the
 * end. Rejects on a non-2xx response or on a mid-stream `error` event.
 */
export async function sendChatStream(
  messages: Message[],
  handlers: StreamHandlers,
): Promise<void> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, stream: true } satisfies ChatRequestDto),
  })

  if (!res.ok || !res.body) {
    const body = (await res.json().catch(() => null)) as ErrorDto | null
    throw new Error(body?.error?.message ?? `Request failed: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE frames are separated by a blank line; process each complete frame.
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      handleFrame(frame, handlers)
    }
  }
}

function handleFrame(frame: string, handlers: StreamHandlers): void {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''))
  }
  const data = dataLines.join('\n')

  switch (event) {
    case 'token':
      handlers.onToken(JSON.parse(data) as string)
      break
    case 'sources':
      handlers.onSources(JSON.parse(data) as Source[])
      break
    case 'error': {
      const err = JSON.parse(data) as { message?: string }
      throw new Error(err.message ?? 'Streaming failed')
    }
    // 'done' and unknown events: nothing to do.
  }
}
