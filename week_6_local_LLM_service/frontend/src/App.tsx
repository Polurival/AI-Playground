import { useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import { sendChat } from './api'
import type { Message } from './api'

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const content = input.trim()
    if (!content || loading) return

    const nextMessages: Message[] = [...messages, { role: 'user', content }]
    setMessages(nextMessages)
    setInput('')
    setError(null)
    setLoading(true)

    try {
      const reply = await sendChat(nextMessages)
      setMessages([...nextMessages, { role: 'assistant', content: reply }])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
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
          </div>
        ))}
        {loading && <div className="message message-assistant message-pending">...brewing...</div>}
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
      </form>
    </div>
  )
}

export default App
