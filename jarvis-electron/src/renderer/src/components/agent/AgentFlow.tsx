import { motion } from 'framer-motion'
import { Check, Loader2, Circle, GitBranch } from 'lucide-react'
import { useAgentStore } from '@/stores/agentStore'
import type { AgentStep } from '@/types'

function Step({ step, last }: { step: AgentStep; last: boolean }): JSX.Element {
  const active = step.status === 'active'
  const done = step.status === 'done'
  const color = done ? '#38e8ff' : active ? '#8af3ff' : 'rgba(255,255,255,0.25)'

  return (
    <div className="relative flex gap-4 pb-7">
      {!last && (
        <div
          className="absolute left-[15px] top-8 h-full w-px"
          style={{ background: done ? '#38e8ff' : 'rgba(255,255,255,0.1)', transition: 'background 0.5s ease' }}
        />
      )}
      <div
        className="relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border"
        style={{
          borderColor: color,
          background: active || done ? 'rgba(56,232,255,0.12)' : 'transparent',
          boxShadow: active ? '0 0 18px rgba(56,232,255,0.6)' : 'none',
          transition: 'all 0.4s ease'
        }}
      >
        {done ? (
          <Check size={15} color="#38e8ff" />
        ) : active ? (
          <motion.div animate={{ rotate: 360 }} transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}>
            <Loader2 size={15} color="#8af3ff" />
          </motion.div>
        ) : (
          <Circle size={7} color="rgba(255,255,255,0.3)" fill="rgba(255,255,255,0.3)" />
        )}
      </div>
      <div className="pt-1">
        <div className="text-sm" style={{ color: done || active ? '#fff' : '#828b9c', transition: 'color 0.4s ease' }}>
          {step.label}
        </div>
        {active && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-0.5 text-xs text-smoke">
            working…
          </motion.div>
        )}
      </div>
    </div>
  )
}

export function AgentFlow(): JSX.Element {
  const title = useAgentStore((s) => s.title)
  const steps = useAgentStore((s) => s.steps)

  if (steps.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center">
        <GitBranch size={28} className="mb-4 text-faint" />
        <div className="text-[11px] uppercase tracking-[0.3em] text-cyan/60">Agent Execution</div>
        <p className="mt-2 max-w-xs text-sm text-smoke">
          Ask JARVIS to do something and watch the reasoning, tool calls and synthesis unfold here.
        </p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-md py-2">
      <div className="mb-6">
        <div className="text-[11px] uppercase tracking-[0.3em] text-cyan/70">Agent Execution</div>
        <h2 className="font-display text-2xl font-extralight tracking-tight text-bone">{title}</h2>
      </div>
      <div className="relative flex flex-col">
        {steps.map((s, i) => (
          <Step key={s.id} step={s} last={i === steps.length - 1} />
        ))}
      </div>
    </div>
  )
}
