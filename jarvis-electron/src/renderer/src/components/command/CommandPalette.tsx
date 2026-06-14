import { useEffect, useMemo, useRef, useState } from 'react'
import type * as React from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Search, CornerDownLeft } from 'lucide-react'
import { useCommandStore } from '@/stores/commandStore'
import { useToolsStore } from '@/stores/toolsStore'
import { useUiStore } from '@/stores/uiStore'
import { useVoiceStore } from '@/stores/voiceStore'
import { useMemoryStore } from '@/stores/memoryStore'
import { useConversationStore } from '@/stores/conversationStore'
import { submitPrompt } from '@/lib/sim/conductor'
import { glassIn } from '@/lib/motion'
import { cn } from '@/lib/utils'
import type { Command } from '@/types'

const COMMANDS: Command[] = [
  { id: 'view-core', group: 'Navigate', label: 'Go to Core', run: () => useUiStore.getState().setView('core') },
  { id: 'view-chat', group: 'Navigate', label: 'Open Conversation', run: () => useUiStore.getState().setView('chat') },
  { id: 'view-memory', group: 'Navigate', label: 'Open Memory Galaxy', run: () => useUiStore.getState().setView('memory') },
  { id: 'view-agent', group: 'Navigate', label: 'Open Agent Flow', run: () => useUiStore.getState().setView('agent') },
  { id: 'voice', group: 'Actions', label: 'Start Voice', hint: '⌘J', keywords: 'mic speak talk listen', run: () => useVoiceStore.getState().setOpen(true) },
  { id: 'search-memory', group: 'Actions', label: 'Search Memory', keywords: 'recall knowledge graph', run: () => { useUiStore.getState().setView('memory'); useMemoryStore.getState().search('research') } },
  { id: 'clear', group: 'Actions', label: 'Clear conversation', run: () => useConversationStore.getState().clear() },
  { id: 'study', group: 'Tasks', label: 'Create a study plan', keywords: 'ml course notion', run: () => { useUiStore.getState().setView('chat'); void submitPrompt('Create a study plan for my ML course and store it in Notion') } },
  { id: 'research', group: 'Tasks', label: 'Research a topic', keywords: 'papers arxiv summarize', run: () => { useUiStore.getState().setView('chat'); void submitPrompt('Research the latest papers on video frame interpolation and summarize them') } },
  { id: 'schedule', group: 'Tasks', label: 'Plan my day', keywords: 'deadlines schedule priorities', run: () => { useUiStore.getState().setView('chat'); void submitPrompt('Check my deadlines, prioritize them and build today schedule') } },
  { id: 'stm32', group: 'Tasks', label: 'Continue STM32 project', keywords: 'code firmware vscode', run: () => { useUiStore.getState().setView('chat'); void submitPrompt('Read my STM32 project notes and help continue development') } },
  { id: 'open-notion', group: 'Tools', label: 'Open Notion', run: () => useToolsStore.getState().engage('notion') },
  { id: 'open-browser', group: 'Tools', label: 'Open Browser', run: () => useToolsStore.getState().engage('browser') },
  { id: 'open-calendar', group: 'Tools', label: 'Open Calendar', run: () => useToolsStore.getState().engage('calendar') },
  { id: 'open-files', group: 'Tools', label: 'Open Files', run: () => useToolsStore.getState().engage('files') },
  { id: 'open-terminal', group: 'Tools', label: 'Open Terminal', run: () => useToolsStore.getState().engage('terminal') }
]

export function CommandPalette(): JSX.Element {
  const open = useCommandStore((s) => s.open)
  const query = useCommandStore((s) => s.query)
  const setQuery = useCommandStore((s) => s.setQuery)
  const setOpen = useCommandStore((s) => s.setOpen)
  const inputRef = useRef<HTMLInputElement>(null)
  const [active, setActive] = useState(0)

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return COMMANDS
    return COMMANDS.filter((c) =>
      (c.label + ' ' + c.group + ' ' + (c.keywords ?? '')).toLowerCase().includes(q)
    )
  }, [query])

  useEffect(() => setActive(0), [query, open])
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 40)
  }, [open])

  const runAt = (i: number): void => {
    const cmd = results[i]
    if (!cmd) return
    cmd.run()
    setOpen(false)
  }

  const onKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => Math.min(results.length - 1, a + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(0, a - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      runAt(active)
    }
  }

  let lastGroup = ''

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center pt-[16vh]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            className="absolute inset-0 bg-black/50"
            style={{ backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)' }}
            onClick={() => setOpen(false)}
          />
          <motion.div
            variants={glassIn}
            initial="hidden"
            animate="show"
            exit="exit"
            className="glass-strong relative z-10 w-[min(620px,92vw)] overflow-hidden rounded-3xl"
            style={{ boxShadow: '0 30px 90px -30px rgba(0,0,0,0.8)' }}
          >
            <div className="flex items-center gap-3 border-b border-white/8 px-5 py-4">
              <Search size={18} className="text-cyan" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Command JARVIS…"
                className="no-drag w-full bg-transparent text-[15px] text-bone outline-none placeholder:text-smoke"
              />
              <span className="rounded-md border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-widest text-smoke">
                ESC
              </span>
            </div>

            <div className="max-h-[46vh] overflow-y-auto p-2">
              {results.length === 0 && (
                <div className="px-4 py-10 text-center text-sm text-smoke">No matching command.</div>
              )}
              {results.map((cmd, i) => {
                const showGroup = cmd.group !== lastGroup
                lastGroup = cmd.group
                const isActive = i === active
                return (
                  <div key={cmd.id}>
                    {showGroup && (
                      <div className="px-3 pb-1 pt-3 text-[10px] uppercase tracking-[0.18em] text-faint">
                        {cmd.group}
                      </div>
                    )}
                    <button
                      onMouseEnter={() => setActive(i)}
                      onClick={() => runAt(i)}
                      className={cn(
                        'no-drag flex w-full items-center justify-between rounded-2xl px-3 py-2.5 text-left text-sm transition-colors',
                        isActive ? 'bg-cyan/12 text-bone' : 'text-ash hover:text-bone'
                      )}
                    >
                      <span className="flex items-center gap-3">
                        <span
                          className="h-1.5 w-1.5 rounded-full"
                          style={{ background: isActive ? '#38e8ff' : 'transparent', boxShadow: isActive ? '0 0 8px #38e8ff' : 'none' }}
                        />
                        {cmd.label}
                      </span>
                      <span className="flex items-center gap-2 text-xs text-smoke">
                        {cmd.hint}
                        {isActive && <CornerDownLeft size={13} className="text-cyan" />}
                      </span>
                    </button>
                  </div>
                )
              })}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
