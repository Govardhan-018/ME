import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Mic, Loader2, X } from 'lucide-react'
import { useVoiceStore } from '@/stores/voiceStore'
import { useCoreStore } from '@/stores/coreStore'
import { useMicAnalyser } from '@/hooks/useMicAnalyser'
import { useVoiceSession } from '@/hooks/useVoiceSession'

const SIZE = 340
const C = SIZE / 2
const R = 118

export function VoiceOverlay(): JSX.Element {
  const open = useVoiceStore((s) => s.open)
  const voiceState = useVoiceStore((s) => s.state)
  const bands = useVoiceStore((s) => s.bands)
  const level = useVoiceStore((s) => s.level)
  const setOpen = useVoiceStore((s) => s.setOpen)
  const session = useVoiceSession()

  const listening = voiceState === 'listening'
  const processing = voiceState === 'processing'

  // Visualize the mic only while actively recording.
  useMicAnalyser(open && listening)

  // Reflect voice activity on the Core.
  useEffect(() => {
    if (open) useCoreStore.getState().setState('listening')
    return () => {
      const c = useCoreStore.getState()
      if (c.state === 'listening') c.setState('idle')
    }
  }, [open])

  // Start recording on open; discard on any close that wasn't an explicit send.
  useEffect(() => {
    if (!open) return
    void session.start()
    return () => session.cancel()
    // session uses stable refs; only re-run on open changes.
  }, [open])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-40 flex flex-col items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-black/40"
            style={{ backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)' }}
            onClick={() => setOpen(false)}
          />

          <motion.div
            className="relative z-10 flex flex-col items-center"
            initial={{ scale: 0.9, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.9, y: 20 }}
          >
            <div className="mb-2 text-[11px] uppercase tracking-[0.4em] text-cyan/80">
              {processing ? 'Transcribing…' : 'Listening'}
            </div>

            <div className="relative" style={{ width: SIZE, height: SIZE }}>
              <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="h-full w-full">
                <circle cx={C} cy={C} r={R} fill="none" stroke="rgba(56,232,255,0.18)" strokeWidth="1" />
                {bands.map((v, i) => {
                  const a = (i / bands.length) * Math.PI * 2 - Math.PI / 2
                  const len = 6 + v * 78
                  return (
                    <line
                      key={i}
                      x1={C + Math.cos(a) * R}
                      y1={C + Math.sin(a) * R}
                      x2={C + Math.cos(a) * (R + len)}
                      y2={C + Math.sin(a) * (R + len)}
                      stroke="#38e8ff"
                      strokeWidth="3"
                      strokeLinecap="round"
                      opacity={0.45 + v * 0.55}
                      style={{ filter: 'drop-shadow(0 0 4px #38e8ff)' }}
                    />
                  )
                })}
              </svg>

              {/* center: tap to send (while listening), spinner while transcribing */}
              <motion.button
                onClick={() => listening && session.stopAndSend()}
                disabled={!listening}
                aria-label="Send"
                className="no-drag absolute left-1/2 top-1/2 flex h-20 w-20 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-cyan/15"
                style={{
                  border: '1px solid rgba(56,232,255,0.5)',
                  transform: `translate(-50%, -50%) scale(${1 + level * 0.3})`,
                  boxShadow: `0 0 ${30 + level * 50}px rgba(56,232,255,0.5)`
                }}
              >
                {processing ? (
                  <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}>
                    <Loader2 size={26} className="text-cyan" />
                  </motion.div>
                ) : (
                  <Mic size={26} className="text-cyan" />
                )}
              </motion.button>
            </div>

            <div className="mt-6 flex h-10 items-center gap-[3px]">
              {bands.slice(0, 28).map((v, i) => (
                <div
                  key={i}
                  className="w-[3px] rounded-full bg-cyan/70"
                  style={{ height: `${8 + v * 32}px`, transition: 'height 0.06s linear' }}
                />
              ))}
            </div>

            <div className="mt-6 flex items-center gap-3">
              <button
                onClick={() => listening && session.stopAndSend()}
                disabled={!listening}
                className="no-drag flex items-center gap-2 rounded-full bg-cyan px-5 py-2 text-xs font-medium text-void transition-opacity disabled:opacity-40"
                style={{ boxShadow: '0 0 20px rgba(56,232,255,0.45)' }}
              >
                <Mic size={13} /> Send
              </button>
              <button
                onClick={() => setOpen(false)}
                className="no-drag flex items-center gap-2 rounded-full border border-white/12 px-4 py-2 text-xs text-smoke transition-colors hover:text-bone"
              >
                <X size={13} /> Cancel · Esc
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
