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
}

interface ChatResponseDto {
  reply: string
  sources?: Source[]
}

interface ErrorDto {
  error: string
}

export async function sendChat(messages: Message[]): Promise<ChatResult> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages } satisfies ChatRequestDto),
  })

  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ErrorDto | null
    throw new Error(body?.error ?? `Request failed: ${res.status}`)
  }

  const data = (await res.json()) as ChatResponseDto
  return { reply: data.reply, sources: data.sources ?? [] }
}
