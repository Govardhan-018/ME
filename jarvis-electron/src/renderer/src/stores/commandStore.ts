import { create } from 'zustand'

interface CommandStore {
  open: boolean
  query: string
  setOpen: (open: boolean) => void
  setQuery: (query: string) => void
  toggle: () => void
}

export const useCommandStore = create<CommandStore>((set, get) => ({
  open: false,
  query: '',
  setOpen: (open) => set({ open, query: open ? '' : get().query }),
  setQuery: (query) => set({ query }),
  toggle: () => set({ open: !get().open, query: '' })
}))
