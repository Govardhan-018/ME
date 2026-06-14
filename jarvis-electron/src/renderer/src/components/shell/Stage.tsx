import { AnimatePresence, motion } from 'framer-motion'
import { useUiStore } from '@/stores/uiStore'
import { useConversationStore } from '@/stores/conversationStore'
import { AICore } from '@/components/core/AICore'
import { OrbitalSystem } from '@/components/orbital/OrbitalSystem'
import { ChatPanel } from '@/components/chat/ChatPanel'
import { MemoryGalaxy } from '@/components/memory/MemoryGalaxy'
import { AgentFlow } from '@/components/agent/AgentFlow'
import { Composer } from '@/components/chat/Composer'
import { GlassPanel } from '@/components/ui/GlassPanel'
import { springs } from '@/lib/motion'
import { cn } from '@/lib/utils'
import type { ViewId } from '@/types'

const VIEWS: { id: ViewId; label: string }[] = [
  { id: 'core', label: 'Core' },
  { id: 'chat', label: 'Chat' },
  { id: 'memory', label: 'Memory' },
  { id: 'agent', label: 'Agent' }
]

function ViewSwitcher(): JSX.Element {
  const view = useUiStore((s) => s.view)
  const setView = useUiStore((s) => s.setView)
  const panelOpen = view !== 'core'
  return (
    <motion.div
      className="glass absolute top-3 z-20 flex -translate-x-1/2 items-center gap-1 rounded-full p-1"
      animate={{ left: panelOpen ? '27%' : '50%' }}
      transition={springs.glass}
    >
      {VIEWS.map((v) => {
        const active = view === v.id
        return (
          <button
            key={v.id}
            onClick={() => setView(v.id)}
            className="no-drag relative rounded-full px-4 py-1.5 text-[13px] font-medium tracking-wide"
          >
            {active && (
              <motion.span
                layoutId="view-pill"
                className="absolute inset-0 rounded-full bg-cyan/15"
                style={{ border: '1px solid rgba(56,232,255,0.3)' }}
                transition={springs.snappy}
              />
            )}
            <span className={cn('relative', active ? 'text-cyan' : 'text-smoke')}>{v.label}</span>
          </button>
        )
      })}
    </motion.div>
  )
}

function CoreStage({ compact }: { compact: boolean }): JSX.Element {
  return (
    <div className="relative flex h-full w-full items-center justify-center">
      <AnimatePresence>
        {!compact && (
          <motion.div
            className="absolute inset-0"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <OrbitalSystem radius={244} />
          </motion.div>
        )}
      </AnimatePresence>
      <motion.div animate={{ scale: compact ? 0.6 : 1 }} transition={springs.glass}>
        <AICore size={360} />
      </motion.div>
    </div>
  )
}

function CoreHome(): JSX.Element {
  const messages = useConversationStore((s) => s.messages)
  const isStreaming = useConversationStore((s) => s.isStreaming)
  const last = [...messages].reverse().find((m) => m.role === 'assistant')
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="absolute bottom-8 left-1/2 w-[min(620px,86%)] -translate-x-1/2"
    >
      <AnimatePresence>
        {last && (isStreaming || last.content) && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="selectable mb-5 line-clamp-2 px-6 text-center text-[13px] leading-relaxed tracking-wide text-smoke"
          >
            {last.content}
          </motion.div>
        )}
      </AnimatePresence>
      <Composer />
    </motion.div>
  )
}

function Panel(): JSX.Element | null {
  const view = useUiStore((s) => s.view)
  if (view === 'chat') return <ChatPanel />
  if (view === 'memory') return <MemoryGalaxy />
  if (view === 'agent') return <AgentFlow />
  return null
}

export function Stage(): JSX.Element {
  const view = useUiStore((s) => s.view)
  const panelOpen = view !== 'core'

  return (
    <div className="relative h-full w-full">
      <ViewSwitcher />
      <div className="flex h-full w-full">
        <motion.section
          layout
          transition={springs.glass}
          className="relative flex min-w-0 flex-1 items-center justify-center"
        >
          <CoreStage compact={panelOpen} />
          <AnimatePresence>{view === 'core' && <CoreHome key="home" />}</AnimatePresence>
        </motion.section>

        <AnimatePresence>
          {panelOpen && (
            <motion.aside
              key="panel"
              initial={{ width: '0%', opacity: 0 }}
              animate={{ width: '46%', opacity: 1 }}
              exit={{ width: '0%', opacity: 0 }}
              transition={springs.glass}
              className="relative h-full overflow-hidden"
            >
              <div className="h-full py-3 pr-3">
                <GlassPanel className="h-full overflow-hidden p-5">
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={view}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -12 }}
                      transition={{ duration: 0.25 }}
                      className="h-full"
                    >
                      <Panel />
                    </motion.div>
                  </AnimatePresence>
                </GlassPanel>
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
