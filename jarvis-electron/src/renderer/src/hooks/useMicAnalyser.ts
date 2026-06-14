import { useEffect, useRef } from 'react'
import { useVoiceStore, VOICE_BANDS } from '@/stores/voiceStore'
import { useCoreStore } from '@/stores/coreStore'

/**
 * Drives the voice spectrum from the real microphone via the Web Audio API.
 * If permission is denied (or unavailable), it falls back to a synthesized
 * spectrum so the visualization never goes dead.
 */
export function useMicAnalyser(active: boolean): void {
  const raf = useRef<number | null>(null)
  const sim = useRef<number | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  useEffect(() => {
    if (!active) return
    const { setBands, setLevel } = useVoiceStore.getState()
    const { setEnergy } = useCoreStore.getState()
    let cancelled = false

    const simulate = (): void => {
      const t = performance.now() / 1000
      const bands = Array.from({ length: VOICE_BANDS }, (_, i) => {
        const v = (Math.sin(t * 6 + i * 0.5) * 0.5 + 0.5) * (0.4 + 0.6 * Math.abs(Math.sin(t * 2 + i)))
        return Math.max(0.05, v)
      })
      const level = bands.reduce((a, b) => a + b, 0) / bands.length
      setBands(bands)
      setLevel(level)
      setEnergy(level)
      sim.current = requestAnimationFrame(simulate)
    }

    try {
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((tr) => tr.stop())
          return
        }
        streamRef.current = stream
        const ctx = new AudioContext()
        ctxRef.current = ctx
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 128
        analyser.smoothingTimeConstant = 0.8
        ctx.createMediaStreamSource(stream).connect(analyser)
        const data = new Uint8Array(analyser.frequencyBinCount)
        const step = Math.floor(data.length / VOICE_BANDS) || 1

        const loop = (): void => {
          analyser.getByteFrequencyData(data)
          const bands: number[] = []
          let sum = 0
          for (let i = 0; i < VOICE_BANDS; i++) {
            let m = 0
            for (let j = 0; j < step; j++) m = Math.max(m, data[i * step + j] ?? 0)
            const v = m / 255
            bands.push(v)
            sum += v
          }
          const level = sum / VOICE_BANDS
          setBands(bands)
          setLevel(level)
          setEnergy(Math.min(1, level * 1.7))
          raf.current = requestAnimationFrame(loop)
        }
        loop()
        })
        .catch(() => simulate())
    } catch {
      simulate()
    }

    return () => {
      cancelled = true
      if (raf.current) cancelAnimationFrame(raf.current)
      if (sim.current) cancelAnimationFrame(sim.current)
      streamRef.current?.getTracks().forEach((tr) => tr.stop())
      void ctxRef.current?.close().catch(() => undefined)
      setEnergy(0)
      setLevel(0)
      setBands(new Array(VOICE_BANDS).fill(0))
    }
  }, [active])
}
