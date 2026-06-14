/** Ambient type for the bridge exposed by the preload script. */
export interface JarvisBridge {
  minimize: () => void
  toggleMaximize: () => void
  close: () => void
  isMaximized: () => Promise<boolean>
  onMaximizedChange: (cb: (maximized: boolean) => void) => () => void
  getBackendStatus: () => Promise<string>
  onBackendStatus: (cb: (status: string) => void) => () => void
  platform: string
}

declare global {
  interface Window {
    jarvis: JarvisBridge
  }
}
