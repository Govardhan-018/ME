/**
 * The CONDUCTOR — the single place that choreographs cross-domain activity.
 *
 * Today it *simulates* an agent turn (think → reason → tool use → stream) so
 * the OS is visibly alive with zero backend. To go live, replace the bodies of
 * `submitPrompt` / `startAmbientLife` with calls to the Python Agent Core over
 * IPC/WebSocket — the UI and stores never change.
 */
import type { AgentStep, ToolId } from '@/types'
import { wait } from '@/lib/utils'
import { useCoreStore } from '@/stores/coreStore'
import { useToolsStore, TOOL_TINT } from '@/stores/toolsStore'
import { useConversationStore } from '@/stores/conversationStore'
import { useAgentStore } from '@/stores/agentStore'
import { useVoiceStore } from '@/stores/voiceStore'

interface Plan {
  title: string
  reasoning: string
  chain: ToolId[]
  answer: string
}

const TOOL_LABEL: Record<ToolId, string> = {
  browser: 'Web search',
  notion: 'Notion',
  calendar: 'Calendar',
  files: 'File system',
  email: 'Email',
  memory: 'Memory recall',
  tasks: 'Task tracker',
  terminal: 'Terminal'
}

// Replaced with real API calls

let turnLock = false

export async function submitPrompt(text: string): Promise<void> {
  const value = text.trim()
  if (!value || turnLock) return
  turnLock = true

  const convo = useConversationStore.getState()
  const core = useCoreStore.getState()
  const agent = useAgentStore.getState()
  const tools = useToolsStore.getState()

  convo.add('user', value)
  
  // Set up loading UI
  core.setState('thinking')
  const replyId = convo.add('assistant', '', { streaming: true })
  
  try {
    // 1. Call real Python API
    const response = await fetch('http://127.0.0.1:8000/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: value })
    })
    
    if (!response.ok) {
      throw new Error(`API returned ${response.status}`)
    }
    
    const data = await response.json()
    
    // 2. Map domain to frontend tool
    const domain = data.domain || 'general'
    let uiTool: ToolId | null = null
    
    if (domain === 'browser') uiTool = 'browser'
    else if (domain === 'files') uiTool = 'files'
    else if (domain === 'notion') uiTool = 'notion'
    else if (domain === 'gmail') uiTool = 'email'
    // 'general' has no tool

    // 3. Build UI Flow
    const steps: AgentStep[] = [
      { id: 'request', label: 'User request', status: 'done' },
      { id: 'reason', label: `Routed to: ${domain}`, status: 'done' }
    ]
    if (uiTool) {
      steps.push({ id: 'tool0', label: TOOL_LABEL[uiTool] || domain, tool: uiTool, status: 'active' })
    }
    steps.push({ id: 'synth', label: 'Synthesis', status: 'pending' })
    agent.start('Processing', steps)

    // 4. Simulate tool active phase visually
    if (uiTool) {
      core.setState('tool')
      core.setTint(TOOL_TINT[uiTool])
      tools.setStatus(uiTool, 'engaged')
      tools.setActive(uiTool)
      convo.addTool(replyId, uiTool)
      await wait(1500) // minimum visual time
      tools.setStatus(uiTool, 'idle')
      if (tools.activeId === uiTool) tools.setActive(null)
      core.setTint(null)
      agent.setStep('tool0', 'done')
    }

    // 5. Stream final response
    core.setState('responding')
    agent.setStep('synth', 'active')
    
    let answer = data.answer
    if (!answer && data.result) {
      // if it's a browser synthesis, extract it. if it's raw JSON, stringify it
      if (data.result.synthesis?.answer) {
        answer = data.result.synthesis.answer
      } else {
        answer = "I executed the command. Here is the raw result:\n" + JSON.stringify(data.result, null, 2)
      }
    }
    
    if (data.error) {
      answer = `Error: ${data.error}`
    }

    await streamWords(replyId, answer || "Done.")
    
    convo.setStreaming(replyId, false)
    agent.setStep('synth', 'done')
    agent.finish()
    
    core.setState('speaking')
    await wait(800)

  } catch (err: any) {
    console.error("Backend Error:", err)
    core.setState('responding')
    convo.setStreaming(replyId, false)
    convo.appendToken(replyId, `Failed to connect to JARVIS Core: ${err.message}`)
    agent.finish()
  } finally {
    core.setState('idle')
    turnLock = false
  }
}

async function streamWords(id: string, text: string): Promise<void> {
  const convo = useConversationStore.getState()
  const core = useCoreStore.getState()
  const words = text.split(' ')
  for (let i = 0; i < words.length; i++) {
    convo.appendToken(id, (i === 0 ? '' : ' ') + words[i])
    core.setEnergy(0.45 + Math.sin(i * 0.45) * 0.25)
    await wait(36 + Math.random() * 26)
  }
  core.setEnergy(0)
}

/* ── Ambient life: subtle activity while idle so the OS breathes ───────── */
let ambientTimer: ReturnType<typeof setInterval> | null = null

export function startAmbientLife(): () => void {
  if (ambientTimer) return () => undefined
  ambientTimer = setInterval(() => {
    const core = useCoreStore.getState()
    const voice = useVoiceStore.getState()
    const convo = useConversationStore.getState()
    if (core.state !== 'idle' || voice.open || convo.isStreaming || turnLock) return
    // Calm idle: only a subtle orbital flicker — never recolour or restart the Core.
    const pool: ToolId[] = ['calendar', 'tasks', 'browser', 'files', 'email']
    useToolsStore.getState().pulse(pool[Math.floor(Math.random() * pool.length)], 1600)
  }, 14000)
  return () => {
    if (ambientTimer) {
      clearInterval(ambientTimer)
      ambientTimer = null
    }
  }
}

/* ── One-time showcase turn shortly after boot ─────────────────────────── */
let introRan = false
export function runIntroDemo(): void {
  if (introRan) return
  introRan = true
  setTimeout(() => {
    void submitPrompt('Find the latest papers on video frame interpolation and create a research page')
  }, 1600)
}
