import { useEffect, useRef } from 'react'
import { useCoreStore } from '@/stores/coreStore'

const COLORS = ['#38e8ff', '#4d7cff', '#8af3ff', '#ffffff']

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  r: number
  c: string
  a: number
}

/** Canvas neural-particle field: drifting nodes + proximity links that
 *  intensify with the Core's energy. Pure canvas — no React re-renders. */
export function ParticleField(): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let w = 0
    let h = 0
    let parts: Particle[] = []
    let raf = 0
    const LINK = 132

    const resize = (): void => {
      const rect = canvas.getBoundingClientRect()
      w = rect.width
      h = rect.height
      canvas.width = w * dpr
      canvas.height = h * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const count = Math.min(120, Math.floor((w * h) / 15000))
      parts = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.16,
        vy: (Math.random() - 0.5) * 0.16,
        r: Math.random() * 1.5 + 0.4,
        c: COLORS[Math.floor(Math.random() * COLORS.length)],
        a: Math.random() * 0.5 + 0.2
      }))
    }
    resize()
    window.addEventListener('resize', resize)

    const loop = (): void => {
      const energy = useCoreStore.getState().energy
      ctx.clearRect(0, 0, w, h)

      for (const p of parts) {
        p.x += p.vx * (1 + energy)
        p.y += p.vy * (1 + energy)
        if (p.x < 0) p.x += w
        else if (p.x > w) p.x -= w
        if (p.y < 0) p.y += h
        else if (p.y > h) p.y -= h
        ctx.globalAlpha = p.a * (0.6 + energy * 0.4)
        ctx.fillStyle = p.c
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fill()
      }

      ctx.globalAlpha = 1
      ctx.lineWidth = 0.6
      for (let i = 0; i < parts.length; i++) {
        for (let j = i + 1; j < parts.length; j++) {
          const a = parts[i]
          const b = parts[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const d2 = dx * dx + dy * dy
          if (d2 < LINK * LINK) {
            const al = (1 - Math.sqrt(d2) / LINK) * 0.12 * (0.55 + energy * 0.6)
            ctx.strokeStyle = `rgba(56,232,255,${al})`
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
          }
        }
      }
      raf = requestAnimationFrame(loop)
    }
    loop()

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
}
