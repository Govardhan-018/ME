import { useEffect } from 'react'
import { AmbientBackground } from '@/components/background/AmbientBackground'
import { TitleBar } from '@/components/shell/TitleBar'
import { Stage } from '@/components/shell/Stage'
import { CommandPalette } from '@/components/command/CommandPalette'
import { VoiceOverlay } from '@/components/voice/VoiceOverlay'
import { useHotkeys } from '@/hooks/useHotkeys'
import { startAmbientLife } from '@/lib/sim/conductor'
import { useUiStore } from '@/stores/uiStore'
import { useBackendStore, type BackendStatus } from '@/stores/backendStore'

export function App(): JSX.Element {
  useHotkeys()
  const setBooted = useUiStore((s) => s.setBooted)

  useEffect(() => {
    const stop = startAmbientLife()
    setBooted(true)
    return stop
  }, [setBooted])

  // Live status of the Python brain (spawned by the Electron main process).
  useEffect(() => {
    const api = window.jarvis
    if (!api?.onBackendStatus) return
    api
      .getBackendStatus()
      .then((s) => useBackendStore.getState().setStatus(s as BackendStatus))
      .catch(() => undefined)
    return api.onBackendStatus((s) => useBackendStore.getState().setStatus(s as BackendStatus))
  }, [])

  return (
    <div className="relative flex h-screen w-screen flex-col overflow-hidden">
      <AmbientBackground />
      <div className="relative z-10 flex h-full flex-col">
        <TitleBar />
        <main className="relative flex-1 overflow-hidden">
          <Stage />
        </main>
      </div>
      <CommandPalette />
      <VoiceOverlay />
    </div>
  )
}
