import { create } from 'zustand'
import type { CoreState } from '@/types'

/**
 * The AI Core's cognitive state. Components derive every visual parameter
 * (speed, scale, hue, turbulence, glow) from `state` + `energy`.
 * `energy` is an external 0..1 drive — e.g. live microphone amplitude.
 */
interface CoreStore {
  state: CoreState
  energy: number
  tint: string | null
  setState: (state: CoreState) => void
  setEnergy: (energy: number) => void
  setTint: (tint: string | null) => void
}

export const useCoreStore = create<CoreStore>((set) => ({
  state: 'idle',
  energy: 0,
  tint: null,
  setState: (state) => set({ state }),
  setEnergy: (energy) => set({ energy }),
  setTint: (tint) => set({ tint })
}))
