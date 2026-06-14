import { motion } from 'framer-motion'
import {
  Globe,
  NotebookText,
  CalendarDays,
  FolderOpen,
  Mail,
  BrainCircuit,
  ListChecks,
  Terminal,
  type LucideIcon
} from 'lucide-react'
import { useToolsStore, TOOL_TINT } from '@/stores/toolsStore'
import type { ToolId } from '@/types'
import { springs } from '@/lib/motion'

function hexA(hex: string, a: number): string {
  const h = hex.replace('#', '')
  const f = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  return `rgba(${parseInt(f.slice(0, 2), 16)}, ${parseInt(f.slice(2, 4), 16)}, ${parseInt(f.slice(4, 6), 16)}, ${a})`
}

const ICONS: Record<ToolId, LucideIcon> = {
  browser: Globe,
  notion: NotebookText,
  calendar: CalendarDays,
  files: FolderOpen,
  email: Mail,
  memory: BrainCircuit,
  tasks: ListChecks,
  terminal: Terminal
}

function ToolNode({
  id,
  label,
  engaged,
  tint
}: {
  id: ToolId
  label: string
  engaged: boolean
  tint: string
}): JSX.Element {
  const engage = useToolsStore((s) => s.engage)
  const Icon = ICONS[id]
  return (
    <button onClick={() => engage(id)} className="no-drag flex flex-col items-center gap-2">
      <motion.div
        whileHover={{ scale: 1.14 }}
        whileTap={{ scale: 0.92 }}
        transition={springs.bouncy}
        className="relative flex h-14 w-14 items-center justify-center rounded-full"
        style={{
          background: engaged ? hexA(tint, 0.16) : 'rgba(255,255,255,0.04)',
          border: `1px solid ${engaged ? hexA(tint, 0.6) : 'rgba(255,255,255,0.1)'}`,
          boxShadow: engaged ? `0 0 26px ${hexA(tint, 0.55)}` : 'none',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          transition: 'background 0.4s ease, border-color 0.4s ease, box-shadow 0.4s ease'
        }}
      >
        <Icon size={20} color={engaged ? tint : '#c4cedd'} style={{ transition: 'color 0.4s ease' }} />
        {engaged && (
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{ border: `1px solid ${tint}` }}
            animate={{ scale: [1, 1.55], opacity: [0.6, 0] }}
            transition={{ duration: 1.5, repeat: Infinity, ease: 'easeOut' }}
          />
        )}
      </motion.div>
      <span
        className="text-[10px] font-medium uppercase tracking-[0.16em]"
        style={{ color: engaged ? tint : '#828b9c', transition: 'color 0.4s ease' }}
      >
        {label}
      </span>
    </button>
  )
}

/** Tools orbit the Core; on use a node ignites, a data line flows inward,
 *  and the node is pulled toward the Core, then released back to orbit. */
export function OrbitalSystem({ radius = 248 }: { radius?: number }): JSX.Element {
  const tools = useToolsStore((s) => s.tools)
  const box = radius * 2 + 72
  const c = box / 2
  const ry = radius * 0.9

  const placed = tools.map((t, i) => {
    const angle = (i / tools.length) * Math.PI * 2 - Math.PI / 2
    const engaged = t.status === 'engaged'
    const rr = engaged ? radius * 0.5 : radius
    const ryy = engaged ? ry * 0.5 : ry
    return {
      t,
      engaged,
      tint: TOOL_TINT[t.id],
      x: Math.cos(angle) * rr,
      y: Math.sin(angle) * ryy
    }
  })

  return (
    <div
      className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
      style={{ width: box, height: box }}
    >
      <svg className="absolute inset-0 h-full w-full" viewBox={`0 0 ${box} ${box}`}>
        <ellipse
          cx={c}
          cy={c}
          rx={radius}
          ry={ry}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth="1"
          strokeDasharray="2 9"
        />
        {placed.map(({ t, x, y, engaged, tint }) =>
          engaged ? (
            <g key={t.id}>
              <line x1={c} y1={c} x2={c + x} y2={c + y} stroke={tint} strokeWidth="1.3" strokeOpacity="0.45" />
              <motion.line
                x1={c}
                y1={c}
                x2={c + x}
                y2={c + y}
                stroke={tint}
                strokeWidth="2"
                strokeDasharray="4 10"
                initial={{ strokeDashoffset: 0 }}
                animate={{ strokeDashoffset: -140 }}
                transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
                style={{ filter: `drop-shadow(0 0 6px ${tint})` }}
              />
            </g>
          ) : null
        )}
      </svg>

      {placed.map(({ t, x, y, engaged, tint }) => (
        <motion.div
          key={t.id}
          className="pointer-events-auto absolute left-1/2 top-1/2"
          animate={{ x: x - 28, y: y - 28, scale: engaged ? 1.16 : 1 }}
          transition={springs.soft}
        >
          <ToolNode id={t.id} label={t.label} engaged={engaged} tint={tint} />
        </motion.div>
      ))}
    </div>
  )
}
