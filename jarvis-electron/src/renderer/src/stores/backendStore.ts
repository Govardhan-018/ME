import { create } from 'zustand'

/** Connectivity of the Python Agent Core (the "brain"), reported by the main process. */
export type BackendStatus = 'starting' | 'online' | 'offline'

interface BackendStore {
  status: BackendStatus
  setStatus: (status: BackendStatus) => void
}

export const useBackendStore = create<BackendStore>((set) => ({
  status: 'offline',
  setStatus: (status) => set({ status })
}))
