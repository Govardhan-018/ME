import { useEffect } from 'react'
import { useCommandStore } from '@/stores/commandStore'
import { useVoiceStore } from '@/stores/voiceStore'

/** Global keyboard surface. ⌘/Ctrl-K command palette · ⌘/Ctrl-J voice · Esc dismiss. */
export function useHotkeys(): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      const mod = e.metaKey || e.ctrlKey
      const key = e.key.toLowerCase()

      if (mod && key === 'k') {
        e.preventDefault()
        useCommandStore.getState().toggle()
        return
      }
      if (mod && key === 'j') {
        e.preventDefault()
        useVoiceStore.getState().toggle()
        return
      }
      if (e.key === 'Escape') {
        const cmd = useCommandStore.getState()
        if (cmd.open) return cmd.setOpen(false)
        const voice = useVoiceStore.getState()
        if (voice.open) voice.setOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
