import { useCoreStore } from '@/stores/coreStore'
import type { CoreState } from '@/types'

/** Visual parameters derived purely from cognitive state + live energy. */
export interface CoreParams {
  state: CoreState
  energy: number
  primary: string
  secondary: string
  ringSpeed: number // seconds per full rotation (lower = faster)
  pulse: number // breathing amplitude
  glow: number // 0..1
  turbulence: number // plasma drift
  label: string
}

const PRESETS: Record<
  CoreState,
  { primary: string; secondary: string; ringSpeed: number; pulse: number; glow: number; turbulence: number; label: string }
> = {
  idle: { primary: '#38e8ff', secondary: '#4d7cff', ringSpeed: 26, pulse: 0.03, glow: 0.42, turbulence: 0.5, label: 'Idle' },
  listening: { primary: '#8af3ff', secondary: '#38e8ff', ringSpeed: 12, pulse: 0.07, glow: 0.78, turbulence: 1.0, label: 'Listening' },
  thinking: { primary: '#4d7cff', secondary: '#38e8ff', ringSpeed: 7, pulse: 0.05, glow: 0.7, turbulence: 1.4, label: 'Thinking' },
  reasoning: { primary: '#38e8ff', secondary: '#4d7cff', ringSpeed: 9, pulse: 0.05, glow: 0.8, turbulence: 1.4, label: 'Reasoning' },
  tool: { primary: '#38e8ff', secondary: '#4d7cff', ringSpeed: 6, pulse: 0.08, glow: 0.86, turbulence: 1.5, label: 'Tool use' },
  memory: { primary: '#8052ff', secondary: '#38e8ff', ringSpeed: 9, pulse: 0.05, glow: 0.8, turbulence: 1.3, label: 'Memory' },
  responding: { primary: '#8af3ff', secondary: '#38e8ff', ringSpeed: 8, pulse: 0.09, glow: 0.92, turbulence: 1.2, label: 'Responding' },
  speaking: { primary: '#8af3ff', secondary: '#4d7cff', ringSpeed: 10, pulse: 0.1, glow: 0.95, turbulence: 1.1, label: 'Speaking' }
}

export function useCoreParams(): CoreParams {
  const state = useCoreStore((s) => s.state)
  const energy = useCoreStore((s) => s.energy)
  const tint = useCoreStore((s) => s.tint)
  const p = PRESETS[state]
  // NOTE: looping params (ringSpeed/pulse/turbulence) are state-only so that
  // high-frequency `energy` updates during streaming never restart the orb's
  // infinite animations. `energy` is consumed separately for glow/scale via CSS.
  return {
    state,
    energy,
    primary: tint ?? p.primary,
    secondary: p.secondary,
    ringSpeed: p.ringSpeed,
    pulse: p.pulse,
    glow: p.glow,
    turbulence: p.turbulence,
    label: p.label
  }
}
