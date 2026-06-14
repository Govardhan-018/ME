import { create } from 'zustand'
import type { ChatMessage, Role, ToolId } from '@/types'
import { uid } from '@/lib/utils'

const SEED: ChatMessage[] = [
  {
    id: 'seed',
    role: 'assistant',
    content:
      "Systems online. I'm JARVIS — your operating intelligence. Speak, type, or press ⌘K to command.",
    createdAt: Date.now()
  }
]

interface ConversationStore {
  messages: ChatMessage[]
  isStreaming: boolean
  add: (role: Role, content: string, extra?: Partial<ChatMessage>) => string
  appendToken: (id: string, token: string) => void
  setReasoning: (id: string, reasoning: string) => void
  addTool: (id: string, tool: ToolId) => void
  setStreaming: (id: string, streaming: boolean) => void
  clear: () => void
}

export const useConversationStore = create<ConversationStore>((set) => ({
  messages: SEED,
  isStreaming: false,
  add: (role, content, extra) => {
    const id = uid()
    set((s) => ({
      messages: [...s.messages, { id, role, content, createdAt: Date.now(), ...extra }],
      isStreaming: extra?.streaming ? true : s.isStreaming
    }))
    return id
  },
  appendToken: (id, token) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, content: m.content + token } : m))
    })),
  setReasoning: (id, reasoning) =>
    set((s) => ({ messages: s.messages.map((m) => (m.id === id ? { ...m, reasoning } : m)) })),
  addTool: (id, tool) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, tools: [...(m.tools ?? []), tool] } : m
      )
    })),
  setStreaming: (id, streaming) =>
    set((s) => ({
      isStreaming: streaming,
      messages: s.messages.map((m) => (m.id === id ? { ...m, streaming } : m))
    })),
  clear: () => set({ messages: [] })
}))
