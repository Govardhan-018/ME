import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Globe,
  NotebookText,
  CalendarDays,
  FolderOpen,
  Mail,
  BrainCircuit,
  ListChecks,
  Terminal,
  Sparkles,
  ChevronRight,
  type LucideIcon
} from 'lucide-react'
import type { ChatMessage, ToolId } from '@/types'
import { TOOL_TINT } from '@/stores/toolsStore'
import { fadeUp } from '@/lib/motion'
import { cn } from '@/lib/utils'

function hexA(hex: string, a: number): string {
  const h = hex.replace('#', '')
  const f = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  return `rgba(${parseInt(f.slice(0, 2), 16)}, ${parseInt(f.slice(2, 4), 16)}, ${parseInt(f.slice(4, 6), 16)}, ${a})`
}

const TOOL_ICON: Record<ToolId, LucideIcon> = {
  browser: Globe,
  notion: NotebookText,
  calendar: CalendarDays,
  files: FolderOpen,
  email: Mail,
  memory: BrainCircuit,
  tasks: ListChecks,
  terminal: Terminal
}
const TOOL_LABEL: Record<ToolId, string> = {
  browser: 'Web', notion: 'Notion', calendar: 'Calendar', files: 'Files',
  email: 'Email', memory: 'Memory', tasks: 'Tasks', terminal: 'Terminal'
}

function Caret(): JSX.Element {
  return (
    <motion.span
      className="ml-0.5 inline-block h-4 w-[7px] translate-y-0.5 rounded-[1px] bg-cyan align-middle"
      animate={{ opacity: [1, 0.2, 1] }}
      transition={{ duration: 1, repeat: Infinity }}
      style={{ boxShadow: '0 0 8px #38e8ff' }}
    />
  )
}

function ToolChip({ id }: { id: ToolId }): JSX.Element {
  const Icon = TOOL_ICON[id]
  const tint = TOOL_TINT[id]
  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px]"
      style={{ borderColor: hexA(tint, 0.32), color: tint, background: hexA(tint, 0.08) }}
    >
      <Icon size={11} />
      {TOOL_LABEL[id]}
    </motion.span>
  )
}

function Reasoning({ text }: { text: string }): JSX.Element {
  const [open, setOpen] = useState(true)
  return (
    <div className="mb-2.5 rounded-2xl border border-white/[0.07] bg-white/[0.02] px-3 py-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="no-drag flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-smoke"
      >
        <Sparkles size={12} className="text-violet" />
        Reasoning
        <ChevronRight size={12} className={cn('transition-transform', open && 'rotate-90')} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <p className="mt-1.5 text-[13px] italic leading-relaxed text-smoke">{text}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function Message({ m }: { m: ChatMessage }): JSX.Element {
  const isUser = m.role === 'user'
  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      animate="show"
      className={cn('flex', isUser ? 'justify-end' : 'justify-start')}
    >
      <div className={cn('max-w-[82%]', isUser ? 'text-right' : 'w-full text-left')}>
        {!isUser && m.reasoning && <Reasoning text={m.reasoning} />}
        {!isUser && m.tools && m.tools.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {m.tools.map((t, i) => (
              <ToolChip key={`${t}-${i}`} id={t} />
            ))}
          </div>
        )}
        {isUser ? (
          <span className="selectable glass inline-block rounded-3xl rounded-tr-lg px-4 py-2.5 text-[15px] leading-relaxed text-ash">
            {m.content}
          </span>
        ) : (
          <div className="selectable border-l border-cyan/25 pl-4 text-[15px] leading-relaxed text-bone">
            {m.content || (m.streaming ? '' : '…')}
            {m.streaming && <Caret />}
          </div>
        )}
      </div>
    </motion.div>
  )
}
