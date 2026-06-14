import { create } from 'zustand'
import type { ViewId } from '@/types'

interface UiStore {
  view: ViewId
  booted: boolean
  setView: (view: ViewId) => void
  setBooted: (booted: boolean) => void
}

export const useUiStore = create<UiStore>((set) => ({
  view: 'core',
  booted: false,
  setView: (view) => set({ view }),
  setBooted: (booted) => set({ booted })
}))
