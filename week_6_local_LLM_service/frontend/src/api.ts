export type Role = 'user' | 'assistant' | 'system'

export interface Message {
  role: Role
  content: string
}

interface ChatRequestDto {
  messages: Message[]
}

interface ChatResponseDto {
  reply: string
}

interface ErrorDto {
  error: string
}

export async function sendChat(messages: Message[]): Promise<string> {
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
  return data.reply
}
