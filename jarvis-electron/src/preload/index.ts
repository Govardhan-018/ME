/**
 * Preload bridge — the ONLY surface the renderer can touch the OS through.
 * Runs sandboxed; exposes a tiny, explicit, typed API via contextBridge.
 * Add capabilities here deliberately; never expose ipcRenderer wholesale.
 */
import { contextBridge, ipcRenderer } from 'electron'

const api = {
  minimize: () => ipcRenderer.send('window:minimize'),
  toggleMaximize: () => ipcRenderer.send('window:toggle-maximize'),
  close: () => ipcRenderer.send('window:close'),
  isMaximized: (): Promise<boolean> => ipcRenderer.invoke('window:is-maximized'),
  onMaximizedChange: (cb: (maximized: boolean) => void) => {
    const listener = (_e: unknown, value: boolean): void => cb(value)
    ipcRenderer.on('window:maximized', listener)
    return () => ipcRenderer.removeListener('window:maximized', listener)
  },
  // Status of the Python "brain" (spawned by the main process).
  getBackendStatus: (): Promise<string> => ipcRenderer.invoke('backend:get-status'),
  onBackendStatus: (cb: (status: string) => void) => {
    const listener = (_e: unknown, status: string): void => cb(status)
    ipcRenderer.on('backend:status', listener)
    return () => ipcRenderer.removeListener('backend:status', listener)
  },
  platform: process.platform
}

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('jarvis', api)
  } catch (error) {
    console.error('[preload] exposeInMainWorld failed', error)
  }
} else {
  // Fallback for the (disabled) non-isolated case.
  // @ts-expect-error — augmenting window without context isolation
  window.jarvis = api
}
