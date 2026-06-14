import { useState } from 'react'
import type * as React from 'react'
import { motion } from 'framer-motion'
import { ArrowUp, Mic } from 'lucide-react'
import { submitPrompt } from '@/lib/sim/conductor'
import { useVoiceStore } from '@/stores/voiceStore'
import { useConversationStore } from '@/stores/conversationStore'

const SUGGESTIONS = [
  'Create a study plan for my ML course',
  'Plan my day from my deadlines',
  'Continue my STM32 project'
]

export function Composer(): JSX.Element {
  const [text, setText] = useState('')
  const isStreaming = useConversationStore((s) => s.isStreaming)
  const showSuggestions = useConversationStore((s) => s.messages.length) <= 1
  const setVoiceOpen = useVoiceStore((s) => s.setOpen)

  const send = (): void => {
    const v = text.trim()
    if (!v) return
    setText('')
    void submitPrompt(v)
  }

  const onKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="px-1 pb-2">
      {showSuggestions && (
        <div className="mb-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => void submitPrompt(s)}
              className="no-drag rounded-full border border-white/10 px-3 py-1.5 text-xs text-smoke transition-colors hover:border-cyan/30 hover:text-cyan"
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <div className="glass flex items-end gap-2 rounded-3xl p-2 pl-4">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="Ask JARVIS anything…"
          className="no-drag max-h-32 min-h-[28px] flex-1 resize-none bg-transparent py-1.5 text-[15px] leading-relaxed text-bone outline-none placeholder:text-smoke"
        />
        <button
          onClick={() => setVoiceOpen(true)}
          aria-label="Voice"
          className="no-drag flex h-9 w-9 items-center justify-center rounded-full text-smoke transition-colors hover:text-cyan"
        >
          <Mic size={18} />
        </button>
        <motion.button
          whileHover={{ scale: 1.06 }}
          whileTap={{ scale: 0.92 }}
          onClick={send}
          disabled={!text.trim() || isStreaming}
          aria-label="Send"
          className="no-drag flex h-9 w-9 items-center justify-center rounded-full bg-cyan text-void transition-opacity disabled:opacity-30"
          style={{ boxShadow: '0 0 20px rgba(56,232,255,0.45)' }}
        >
          <ArrowUp size={18} />
        </motion.button>
      </div>
    </div>
  )
}
