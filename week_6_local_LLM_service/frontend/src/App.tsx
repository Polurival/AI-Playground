import { useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import { sendChat, sendChatStream } from './api'
import type { Message, Source } from './api'

/** A chat turn as shown in the UI: the wire message plus any grounding sources. */
type DisplayMessage = Message & { sources?: Source[] }

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

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const content = input.trim()
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
        {messages.map((m, i) => (
          <div key={i} className={`message message-${m.role}`}>
            <span className="message-role">{m.role}</span>
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
