import { create } from 'zustand'
import type { VoiceState } from '@/types'

const BANDS = 32

interface VoiceStore {
  state: VoiceState
  open: boolean
  level: number
  bands: number[]
  setState: (state: VoiceState) => void
  setLevel: (level: number) => void
  setBands: (bands: number[]) => void
  setOpen: (open: boolean) => void
  toggle: () => void
}

export const useVoiceStore = create<VoiceStore>((set, get) => ({
  state: 'idle',
  open: false,
  level: 0,
  bands: new Array(BANDS).fill(0),
  setState: (state) => set({ state }),
  setLevel: (level) => set({ level }),
  setBands: (bands) => set({ bands }),
  setOpen: (open) => set({ open, state: open ? 'listening' : 'idle' }),
  toggle: () => get().setOpen(!get().open)
}))

export const VOICE_BANDS = BANDS
