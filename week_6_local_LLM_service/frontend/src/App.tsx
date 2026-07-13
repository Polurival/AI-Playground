import { useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import { sendChat, sendChatStream } from './api'
import type { Message, Source } from './api'

/** A chat turn as shown in the UI: the wire message plus any grounding sources. */
type DisplayMessage = Message & { sources?: Source[] }

/** Display names for the wire roles; `Message.role` itself stays 'user'/'assistant'. */
const ROLE_LABEL: Record<Message['role'], string> = {
  user: 'Gerald',
  assistant: 'Marlene de Trastamara',
  system: 'system',
}

/**
 * Real dish titles from the knowledge base (category "meals"), so asking for any
 * of these is guaranteed to clear the relevance threshold and return a grounded
 * recipe rather than a refusal.
 */
const DISH_SUGGESTIONS = [
  'Kaedweni Bigos',
  'Nilfgaardian Meat Pie',
  'Redanian Goulash',
  'Skellige Herring Salad',
  'Toussaint Duck Breast with Plum Sauce',
  'Zerrikanian Spiced Eggs',
]

function pickRandomDishes(count: number): string[] {
  return [...DISH_SUGGESTIONS].sort(() => Math.random() - 0.5).slice(0, count)
}

/** True while awaiting the reply's first content: a user turn or an empty streaming bubble. */
function awaitingFirstToken(messages: DisplayMessage[]): boolean {
  const last = messages[messages.length - 1]
  return !last || last.role !== 'assistant' || last.content === ''
}

function App() {
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [greetingDishes] = useState(() => pickRandomDishes(3))

  async function sendMessage(content: string) {
    if (!content || loading) return

    const nextMessages: DisplayMessage[] = [...messages, { role: 'user', content }]
    setMessages(nextMessages)
    setInput('')
    setError(null)
    setLoading(true)

    try {
      // Send only the wire fields; sources are display-only and the server is stateless.
      const history: Message[] = nextMessages.map(({ role, content }) => ({ role, content }))
      if (streaming) {
        await streamReply(nextMessages, history)
      } else {
        const { reply, sources } = await sendChat(history)
        setMessages([...nextMessages, { role: 'assistant', content: reply, sources }])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    void sendMessage(input.trim())
  }

  /** Appends an assistant bubble and grows it as tokens arrive, then fills in sources. */
  async function streamReply(base: DisplayMessage[], history: Message[]) {
    setMessages([...base, { role: 'assistant', content: '' }])
    await sendChatStream(history, {
      onToken: (text) =>
        setMessages((prev) => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          copy[copy.length - 1] = { ...last, content: last.content + text }
          return copy
        }),
      onSources: (sources) =>
        setMessages((prev) => {
          const copy = [...prev]
          const last = copy[copy.length - 1]
          copy[copy.length - 1] = { ...last, sources }
          return copy
        }),
    })
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Witcher Cookbook</h1>
      </header>

      <main className="chat-window">
        <div className="message message-assistant message-greeting">
          <span className="message-role">{ROLE_LABEL.assistant}</span>
          <p>
            Welcome, traveler. Hungry after the road? I can cook from what's written in this
            cookbook — try asking for one of these:
          </p>
          <div className="dish-suggestions">
            {greetingDishes.map((dish) => (
              <button
                key={dish}
                type="button"
                className="dish-suggestion"
                onClick={() => void sendMessage(dish)}
                disabled={loading}
              >
                {dish}
              </button>
            ))}
          </div>
        </div>
        {messages.map((m, i) => (
          <div key={i} className={`message message-${m.role}`}>
            <span className="message-role">{ROLE_LABEL[m.role]}</span>
            <p>{m.content}</p>
            {m.sources && m.sources.length > 0 && (
              <div className="message-sources">
                <span className="message-sources-label">Sources</span>
                <ul>
                  {m.sources.map((s, j) => (
                    <li key={j}>
                      {s.title} <span className="source-score">{s.score.toFixed(2)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
        {loading && awaitingFirstToken(messages) && (
          <div className="message message-assistant message-pending">...brewing...</div>
        )}
        {error && <div className="message message-error">{error}</div>}
      </main>

      <form className="chat-form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask for a recipe, e.g. hearty stew"
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          Send
        </button>
        <label className="stream-toggle">
          <input
            type="checkbox"
            checked={streaming}
            onChange={(e) => setStreaming(e.target.checked)}
            disabled={loading}
          />
          Stream
        </label>
      </form>
    </div>
  )
}

export default App
