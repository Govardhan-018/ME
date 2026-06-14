import { useEffect, useState } from 'react'
import type * as React from 'react'
import { motion } from 'framer-motion'
import { Minus, Square, X, Command as CommandIcon } from 'lucide-react'
import { useCoreStore } from '@/stores/coreStore'
import { useCommandStore } from '@/stores/commandStore'
import { useBackendStore } from '@/stores/backendStore'
import type { CoreState } from '@/types'

const LABELS: Record<CoreState, string> = {
  idle: 'Standing by',
  listening: 'Listening',
  thinking: 'Thinking',
  reasoning: 'Reasoning',
  tool: 'Using tools',
  memory: 'Recalling',
  responding: 'Responding',
  speaking: 'Speaking'
}

const bridge = typeof window !== 'undefined' ? window.jarvis : undefined

export function TitleBar(): JSX.Element {
  const state = useCoreStore((s) => s.state)
  const toggleCommand = useCommandStore((s) => s.toggle)
  const [maximized, setMaximized] = useState(false)

  useEffect(() => bridge?.onMaximizedChange(setMaximized), [])

  const backend = useBackendStore((s) => s.status)
  const dot = backend === 'online' ? '#38e8ff' : backend === 'starting' ? '#ffb829' : '#ff5d5d'
  const statusLabel =
    backend === 'online'
      ? LABELS[state]
      : backend === 'starting'
        ? 'Connecting to Core…'
        : 'Core offline'

  return (
    <header className="drag relative z-30 flex h-12 items-center justify-between px-5">
      <div className="flex items-center gap-3">
        <div className="h-2 w-2 rotate-45 bg-cyan" style={{ boxShadow: '0 0 12px #38e8ff' }} />
        <span className="font-display text-sm font-semibold tracking-[0.42em] text-bone">JARVIS</span>
        <span className="ml-2 flex items-center gap-2 text-[11px] tracking-wide text-smoke">
          <motion.span
            className="h-1.5 w-1.5 rounded-full"
            animate={{ opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 2, repeat: Infinity }}
            style={{ background: dot, boxShadow: `0 0 8px ${dot}` }}
          />
          {statusLabel}
        </span>
      </div>

      <div className="no-drag flex items-center gap-2">
        <button
          onClick={toggleCommand}
          className="flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-[11px] text-smoke transition-colors hover:text-bone"
        >
          <CommandIcon size={12} />K
        </button>
        <div className="ml-1 flex items-center gap-1">
          <WinButton onClick={() => bridge?.minimize()} label="Minimize">
            <Minus size={13} />
          </WinButton>
          <WinButton onClick={() => bridge?.toggleMaximize()} label="Maximize">
            <Square size={11} />
          </WinButton>
          <WinButton onClick={() => bridge?.close()} label="Close" danger>
            <X size={13} />
          </WinButton>
        </div>
      </div>
    </header>
  )
}

function WinButton({
  children,
  onClick,
  label,
  danger
}: {
  children: React.ReactNode
  onClick: () => void
  label: string
  danger?: boolean
}): JSX.Element {
  return (
    <button
      aria-label={label}
      onClick={onClick}
      className={
        'flex h-7 w-7 items-center justify-center rounded-full text-smoke transition-colors ' +
        (danger ? 'hover:bg-red-500/20 hover:text-red-300' : 'hover:bg-white/10 hover:text-bone')
      }
    >
      {children}
    </button>
  )
}
