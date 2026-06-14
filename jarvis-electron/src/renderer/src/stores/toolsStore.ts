import { create } from 'zustand'
import type { ToolId, ToolNode, ToolStatus } from '@/types'
import { useCoreStore } from './coreStore'

/** Accent each tool injects into the Core when engaged. */
export const TOOL_TINT: Record<ToolId, string> = {
  browser: '#38e8ff',
  notion: '#ffffff',
  calendar: '#4d7cff',
  files: '#8af3ff',
  email: '#4d7cff',
  memory: '#8052ff',
  tasks: '#38e8ff',
  terminal: '#8af3ff'
}

const INITIAL: ToolNode[] = [
  { id: 'browser', label: 'Browser', status: 'idle' },
  { id: 'notion', label: 'Notion', status: 'idle' },
  { id: 'calendar', label: 'Calendar', status: 'idle' },
  { id: 'files', label: 'Files', status: 'idle' },
  { id: 'email', label: 'Email', status: 'idle' },
  { id: 'memory', label: 'Memory', status: 'idle' },
  { id: 'tasks', label: 'Tasks', status: 'idle' },
  { id: 'terminal', label: 'Terminal', status: 'idle' }
]

interface ToolsStore {
  tools: ToolNode[]
  activeId: ToolId | null
  setStatus: (id: ToolId, status: ToolStatus) => void
  setActive: (id: ToolId | null) => void
  /** One-shot standalone flash (used by command palette); fully self-manages the Core. */
  engage: (id: ToolId, duration?: number) => void
  /** Subtle orbital flicker that does NOT touch the Core (idle ambient life). */
  pulse: (id: ToolId, duration?: number) => void
}

export const useToolsStore = create<ToolsStore>((set, get) => ({
  tools: INITIAL,
  activeId: null,
  setStatus: (id, status) =>
    set((s) => ({ tools: s.tools.map((t) => (t.id === id ? { ...t, status } : t)) })),
  setActive: (activeId) => set({ activeId }),
  engage: (id, duration = 2400) => {
    get().setStatus(id, 'engaged')
    set({ activeId: id })
    const core = useCoreStore.getState()
    core.setState(id === 'memory' ? 'memory' : 'tool')
    core.setTint(TOOL_TINT[id])
    setTimeout(() => {
      get().setStatus(id, 'idle')
      if (get().activeId === id) set({ activeId: null })
      const c = useCoreStore.getState()
      c.setTint(null)
      if (c.state === 'tool' || c.state === 'memory') c.setState('idle')
    }, duration)
  },
  pulse: (id, duration = 1600) => {
    get().setStatus(id, 'engaged')
    setTimeout(() => get().setStatus(id, 'idle'), duration)
  }
}))
