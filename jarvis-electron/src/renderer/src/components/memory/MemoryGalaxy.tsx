import { useState } from 'react'
import { motion } from 'framer-motion'
import { Search } from 'lucide-react'
import { useMemoryStore } from '@/stores/memoryStore'

const VB = 1000
const SCALE = 430

export function MemoryGalaxy(): JSX.Element {
  const nodes = useMemoryStore((s) => s.nodes)
  const edges = useMemoryStore((s) => s.edges)
  const activePath = useMemoryStore((s) => s.activePath)
  const searching = useMemoryStore((s) => s.searching)
  const search = useMemoryStore((s) => s.search)
  const [q, setQ] = useState('')

  const pos = (id: string): { x: number; y: number } => {
    const n = nodes.find((m) => m.id === id)
    return { x: VB / 2 + (n?.x ?? 0) * SCALE, y: VB / 2 + (n?.y ?? 0) * SCALE }
  }
  const inPath = (id: string): boolean => activePath.includes(id)

  return (
    <div className="flex h-full flex-col">
      <div className="mb-1 flex items-end justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-[0.3em] text-cyan/70">Knowledge Galaxy</div>
          <h2 className="font-display text-2xl font-extralight tracking-tight text-bone">Memory</h2>
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          search(q || 'research')
        }}
        className="glass mb-2 flex items-center gap-2 rounded-full px-4 py-2"
      >
        <Search size={15} className="text-cyan" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search memory — try “research” or “stm32”…"
          className="no-drag w-full bg-transparent text-sm text-bone outline-none placeholder:text-smoke"
        />
      </form>

      <div className="min-h-0 flex-1">
        <svg viewBox={`0 0 ${VB} ${VB}`} className="h-full w-full">
          {edges.map((e, i) => {
            const a = pos(e.from)
            const b = pos(e.to)
            const hot = inPath(e.from) && inPath(e.to)
            return (
              <g key={i}>
                <line
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke={hot ? '#38e8ff' : 'rgba(255,255,255,0.08)'}
                  strokeWidth={hot ? 2 : 1}
                  style={{ transition: 'stroke 0.4s ease' }}
                />
                {hot && searching && (
                  <motion.line
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke="#8af3ff"
                    strokeWidth="2.5"
                    strokeDasharray="6 12"
                    initial={{ strokeDashoffset: 0 }}
                    animate={{ strokeDashoffset: -180 }}
                    transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
                    style={{ filter: 'drop-shadow(0 0 6px #38e8ff)' }}
                  />
                )}
              </g>
            )
          })}

          {nodes.map((n) => {
            const p = pos(n.id)
            const hot = inPath(n.id)
            const isHub = n.r > 5
            const fill = hot ? '#38e8ff' : isHub ? '#4d7cff' : '#c4cedd'
            return (
              <g key={n.id}>
                <motion.circle
                  cx={p.x}
                  cy={p.y}
                  r={n.r * 2}
                  fill={fill}
                  fillOpacity={hot ? 1 : isHub ? 0.7 : 0.4}
                  animate={hot ? { scale: [1, 1.35, 1] } : { scale: 1 }}
                  transition={{ duration: 1.2, repeat: hot ? Infinity : 0 }}
                  style={{
                    transformBox: 'fill-box',
                    transformOrigin: 'center',
                    filter: hot ? 'drop-shadow(0 0 10px #38e8ff)' : 'none',
                    transition: 'fill 0.4s ease'
                  }}
                />
                {(isHub || hot) && (
                  <text
                    x={p.x}
                    y={p.y - n.r * 2 - 8}
                    textAnchor="middle"
                    fontSize="13"
                    fill={hot ? '#8af3ff' : '#828b9c'}
                    style={{ transition: 'fill 0.4s ease' }}
                  >
                    {n.label}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
