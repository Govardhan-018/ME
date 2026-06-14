import { useRef } from 'react'
import type * as React from 'react'
import { useMotionValue, useSpring, type MotionValue } from 'framer-motion'

interface Magnetic {
  ref: React.RefObject<HTMLDivElement>
  style: { x: MotionValue<number>; y: MotionValue<number> }
  onMouseMove: (e: React.MouseEvent) => void
  onMouseLeave: () => void
}

/** Cursor-reactive magnetism — elements lean toward the pointer, spring back on leave. */
export function useMagnetic(strength = 0.35): Magnetic {
  const ref = useRef<HTMLDivElement>(null)
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const config = { stiffness: 280, damping: 18, mass: 0.5 }
  const sx = useSpring(x, config)
  const sy = useSpring(y, config)

  const onMouseMove = (e: React.MouseEvent): void => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    x.set((e.clientX - (r.left + r.width / 2)) * strength)
    y.set((e.clientY - (r.top + r.height / 2)) * strength)
  }
  const onMouseLeave = (): void => {
    x.set(0)
    y.set(0)
  }

  return { ref, style: { x: sx, y: sy }, onMouseMove, onMouseLeave }
}
