import { motion } from 'framer-motion'
import { useCoreParams } from './coreParams'

/** hex (#fff or #ffffff) → rgba string. */
function hexA(hex: string, a: number): string {
  const h = hex.replace('#', '')
  const f = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  const r = parseInt(f.slice(0, 2), 16)
  const g = parseInt(f.slice(2, 4), 16)
  const b = parseInt(f.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${a})`
}

function PlasmaBlob({ color, delay, t }: { color: string; delay: number; t: number }): JSX.Element {
  return (
    <motion.div
      className="absolute h-1/2 w-1/2 rounded-full"
      style={{
        background: `radial-gradient(circle, ${color}, transparent 70%)`,
        filter: 'blur(10px)',
        mixBlendMode: 'screen',
        transition: 'background 0.8s ease'
      }}
      animate={{
        x: [`${-12 * t}%`, `${22 * t}%`, `${-12 * t}%`],
        y: [`${12 * t}%`, `${-16 * t}%`, `${12 * t}%`],
        scale: [1, 1.22, 1]
      }}
      transition={{ duration: 6 / Math.max(0.5, t), repeat: Infinity, ease: 'easeInOut', delay }}
    />
  )
}

/**
 * The living AI Core. A composition of independent layers — halo, rotating
 * rings, plasma body, nucleus, orbiting sparks — whose colors/speed are a pure
 * function of cognitive state, with `energy` driving glow & scale via CSS.
 */
export function AICore({ size = 360 }: { size?: number }): JSX.Element {
  const p = useCoreParams()
  const glowAlpha = Math.min(1, p.glow + p.energy * 0.4)
  const nucleusScale = 1 + p.energy * 0.12

  return (
    <div className="pointer-events-none relative" style={{ width: size, height: size }}>
      {/* volumetric halo */}
      <motion.div
        className="absolute inset-[-42%] rounded-full"
        style={{
          background: `radial-gradient(circle, ${hexA(p.primary, 0.28 + glowAlpha * 0.4)} 0%, transparent 62%)`,
          transition: 'background 0.8s ease'
        }}
        animate={{ scale: [1, 1.08, 1], opacity: [0.7, 1, 0.7] }}
        transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* outer rotating ring */}
      <motion.svg
        viewBox="0 0 200 200"
        className="absolute inset-0 h-full w-full"
        animate={{ rotate: 360 }}
        transition={{ duration: p.ringSpeed, repeat: Infinity, ease: 'linear' }}
      >
        <defs>
          <linearGradient id="jarvis-ring" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={p.primary} stopOpacity="0.95" />
            <stop offset="55%" stopColor={p.secondary} stopOpacity="0.25" />
            <stop offset="100%" stopColor={p.primary} stopOpacity="0" />
          </linearGradient>
        </defs>
        <circle
          cx="100"
          cy="100"
          r="94"
          fill="none"
          stroke="url(#jarvis-ring)"
          strokeWidth="1.1"
          strokeDasharray="2 7"
          strokeLinecap="round"
        />
      </motion.svg>

      {/* mid counter-rotating ring */}
      <motion.svg
        viewBox="0 0 200 200"
        className="absolute inset-[7%] h-[86%] w-[86%]"
        animate={{ rotate: -360 }}
        transition={{ duration: p.ringSpeed * 1.7, repeat: Infinity, ease: 'linear' }}
      >
        <circle
          cx="100"
          cy="100"
          r="90"
          fill="none"
          stroke={p.secondary}
          strokeOpacity="0.28"
          strokeWidth="0.7"
          strokeDasharray="1 11"
          style={{ transition: 'stroke 0.8s ease' }}
        />
      </motion.svg>

      {/* plasma body */}
      <motion.div
        className="absolute inset-[20%] overflow-hidden rounded-full"
        style={{
          background: `radial-gradient(circle at 50% 42%, ${p.primary}, ${p.secondary} 52%, #050a16 100%)`,
          boxShadow: `0 0 ${40 + glowAlpha * 70}px ${hexA(p.primary, glowAlpha * 0.7)}, inset 0 0 60px rgba(0,0,0,0.55)`,
          transition: 'background 0.8s ease, box-shadow 0.4s ease'
        }}
        animate={{ scale: [1, 1 + p.pulse, 1] }}
        transition={{ duration: 2.8, repeat: Infinity, ease: 'easeInOut' }}
      >
        <PlasmaBlob color={p.secondary} delay={0} t={p.turbulence} />
        <PlasmaBlob color={p.primary} delay={1.3} t={p.turbulence} />
        <PlasmaBlob color="#ffffff" delay={2.2} t={p.turbulence} />
        <div
          className="absolute inset-0 rounded-full"
          style={{ boxShadow: `inset 0 0 34px ${hexA(p.primary, 0.65)}`, transition: 'box-shadow 0.8s ease' }}
        />
      </motion.div>

      {/* bright nucleus (energy-reactive scale via CSS) */}
      <motion.div
        className="absolute inset-[42%] rounded-full bg-white"
        style={{
          boxShadow: `0 0 28px ${hexA(p.primary, 0.9)}`,
          transform: `scale(${nucleusScale})`,
          transition: 'transform 0.3s ease-out, box-shadow 0.4s ease'
        }}
        animate={{ opacity: [0.9, 1, 0.9] }}
        transition={{ duration: 2.8, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* orbiting sparks */}
      <motion.div
        className="absolute inset-0"
        animate={{ rotate: 360 }}
        transition={{ duration: p.ringSpeed * 0.85, repeat: Infinity, ease: 'linear' }}
      >
        {[0, 120, 240].map((deg) => (
          <div
            key={deg}
            className="absolute left-1/2 top-1/2 h-1 w-1 rounded-full"
            style={{
              background: p.primary,
              boxShadow: `0 0 8px ${p.primary}`,
              transform: `rotate(${deg}deg) translateY(-${size * 0.46}px)`,
              transition: 'background 0.8s ease'
            }}
          />
        ))}
      </motion.div>
    </div>
  )
}
