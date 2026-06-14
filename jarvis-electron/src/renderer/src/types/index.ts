/// <reference types="vite/client" />

/** Cognitive state of the AI Core — drives every visual parameter of the orb. */
export type CoreState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'reasoning'
  | 'tool'
  | 'memory'
  | 'responding'
  | 'speaking'

export type ToolId =
  | 'browser'
  | 'notion'
  | 'calendar'
  | 'files'
  | 'email'
  | 'memory'
  | 'tasks'
  | 'terminal'

export type ToolStatus = 'idle' | 'active' | 'engaged'

export interface ToolNode {
  id: ToolId
  label: string
  status: ToolStatus
}

export type Role = 'user' | 'assistant' | 'system'

export interface ChatMessage {
  id: string
  role: Role
  content: string
  reasoning?: string
  tools?: ToolId[]
  streaming?: boolean
  createdAt: number
}

export type AgentStepStatus = 'pending' | 'active' | 'done'

export interface AgentStep {
  id: string
  label: string
  detail?: string
  tool?: ToolId
  status: AgentStepStatus
}

export interface MemoryNode {
  id: string
  label: string
  cluster: number
  x: number
  y: number
  r: number
}

export interface MemoryEdge {
  from: string
  to: string
}

export type VoiceState = 'idle' | 'listening' | 'processing' | 'speaking'

export type ViewId = 'core' | 'chat' | 'memory' | 'agent'

export interface Command {
  id: string
  label: string
  hint?: string
  group: string
  keywords?: string
  run: () => void
}
