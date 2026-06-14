/**
 * The motion language. Every animated surface in JARVIS pulls from these
 * springs / curves / variants so the whole OS shares one physical feel.
 */
import type { Variants } from 'framer-motion'

type Bezier = [number, number, number, number]

export const ease = {
  out: [0.16, 1, 0.3, 1] as Bezier,
  inOut: [0.65, 0, 0.35, 1] as Bezier,
  soft: [0.4, 0, 0.2, 1] as Bezier
}

export const springs = {
  soft: { type: 'spring', stiffness: 120, damping: 20, mass: 0.9 },
  snappy: { type: 'spring', stiffness: 320, damping: 30 },
  bouncy: { type: 'spring', stiffness: 440, damping: 17, mass: 0.8 },
  glass: { type: 'spring', stiffness: 210, damping: 26, mass: 1 }
} as const

/* ── Reveal variants ──────────────────────────────────────────────────── */
export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.5, ease: ease.out } }
}

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 18, filter: 'blur(6px)' },
  show: {
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: { duration: 0.62, ease: ease.out }
  }
}

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.92 },
  show: { opacity: 1, scale: 1, transition: springs.glass }
}

export const glassIn: Variants = {
  hidden: { opacity: 0, scale: 0.96, y: 10, filter: 'blur(10px)' },
  show: {
    opacity: 1,
    scale: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: springs.glass
  },
  exit: {
    opacity: 0,
    scale: 0.97,
    y: 8,
    filter: 'blur(8px)',
    transition: { duration: 0.22, ease: ease.soft }
  }
}

export const staggerContainer: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.04 } }
}

/** Line-by-line text reveal (premium streaming feel). */
export const lineReveal: Variants = {
  hidden: { opacity: 0, y: 10, filter: 'blur(4px)' },
  show: { opacity: 1, y: 0, filter: 'blur(0px)', transition: { duration: 0.45, ease: ease.out } }
}
