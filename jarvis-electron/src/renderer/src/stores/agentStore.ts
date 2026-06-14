import { create } from 'zustand'
import type { AgentStep, AgentStepStatus } from '@/types'

/** The live agent execution graph (request → reasoning → tools → synthesis → done). */
interface AgentStore {
  title: string
  steps: AgentStep[]
  running: boolean
  start: (title: string, steps: AgentStep[]) => void
  setStep: (id: string, status: AgentStepStatus, detail?: string) => void
  finish: () => void
  reset: () => void
}

export const useAgentStore = create<AgentStore>((set) => ({
  title: '',
  steps: [],
  running: false,
  start: (title, steps) => set({ title, steps, running: true }),
  setStep: (id, status, detail) =>
    set((s) => ({
      steps: s.steps.map((st) =>
        st.id === id ? { ...st, status, detail: detail ?? st.detail } : st
      )
    })),
  finish: () => set({ running: false }),
  reset: () => set({ title: '', steps: [], running: false })
}))
