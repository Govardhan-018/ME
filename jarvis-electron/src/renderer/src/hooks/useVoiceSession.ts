import { useRef } from 'react'
import { useVoiceStore } from '@/stores/voiceStore'
import { useConversationStore } from '@/stores/conversationStore'
import { submitPrompt } from '@/lib/sim/conductor'
import { speak, stopSpeaking } from '@/lib/voice/tts'

const BRAIN = 'http://127.0.0.1:8000'

/** When the next assistant reply finishes streaming, speak it aloud. */
function speakReplyWhenReady(): void {
  let started = false
  const timer = setTimeout(() => unsub(), 180_000)
  const unsub = useConversationStore.subscribe((state, prev) => {
    if (!started) {
      if (state.isStreaming) started = true
      return
    }
    if (prev.isStreaming && !state.isStreaming) {
      unsub()
      clearTimeout(timer)
      const last = [...state.messages].reverse().find((m) => m.role === 'assistant')
      if (last?.content) {
        useVoiceStore.getState().setState('speaking')
        speak(last.content, () => useVoiceStore.getState().setState('idle'))
      }
    }
  })
}

interface VoiceSession {
  start: () => Promise<void>
  stopAndSend: () => Promise<void>
  cancel: () => void
}

/**
 * The voice loop: record mic → faster-whisper STT (brain) → submitPrompt →
 * speak the reply. Recording uses MediaRecorder; the overlay's spectrum is
 * driven separately by useMicAnalyser.
 */
export function useVoiceSession(): VoiceSession {
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const teardown = (): void => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    recorderRef.current = null
    streamRef.current = null
  }

  const start = async (): Promise<void> => {
    stopSpeaking()
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      chunksRef.current = []
      const rec = new MediaRecorder(stream)
      rec.ondataavailable = (e) => {
        if (e.data.size) chunksRef.current.push(e.data)
      }
      rec.start()
      recorderRef.current = rec
      useVoiceStore.getState().setState('listening')
    } catch {
      useVoiceStore.getState().setOpen(false)
    }
  }

  const stopAndSend = async (): Promise<void> => {
    const rec = recorderRef.current
    if (!rec || rec.state === 'inactive') return

    const blob = await new Promise<Blob>((resolve) => {
      rec.onstop = () => resolve(new Blob(chunksRef.current, { type: 'audio/webm' }))
      rec.stop()
    })
    teardown()

    const voice = useVoiceStore.getState()
    voice.setState('processing')
    try {
      const r = await fetch(`${BRAIN}/api/voice/transcribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'audio/webm' },
        body: blob
      })
      const data = await r.json()
      const text = (data.text || '').trim()
      voice.setOpen(false)
      if (!text) return
      speakReplyWhenReady()
      await submitPrompt(text)
    } catch {
      voice.setOpen(false)
      voice.setState('idle')
    }
  }

  const cancel = (): void => {
    const rec = recorderRef.current
    if (rec && rec.state !== 'inactive') {
      rec.onstop = null
      rec.stop()
    }
    teardown()
  }

  return { start, stopAndSend, cancel }
}
