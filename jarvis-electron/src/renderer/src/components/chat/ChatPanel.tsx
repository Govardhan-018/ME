import { useEffect, useRef } from 'react'
import { useConversationStore } from '@/stores/conversationStore'
import { Message } from './Message'
import { Composer } from './Composer'

export function ChatPanel(): JSX.Element {
  const messages = useConversationStore((s) => s.messages)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="mask-fade-y flex-1 overflow-y-auto px-2">
        <div className="mx-auto flex max-w-2xl flex-col gap-6 py-8">
          {messages.map((m) => (
            <Message key={m.id} m={m} />
          ))}
        </div>
      </div>
      <div className="mx-auto w-full max-w-2xl">
        <Composer />
      </div>
    </div>
  )
}
