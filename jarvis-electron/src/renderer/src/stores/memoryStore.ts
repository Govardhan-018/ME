import { create } from 'zustand'
import type { MemoryEdge, MemoryNode } from '@/types'

/** Deterministic "knowledge galaxy" layout in normalized [-1, 1] space. */
function buildGalaxy(): { nodes: MemoryNode[]; edges: MemoryEdge[] } {
  const clusters = [
    { name: 'Academics', labels: ['ML Lecture 4', 'Study Plan', 'Exam Deadline'] },
    { name: 'STM32', labels: ['PWM Config', 'CubeMX', 'Flash Script', 'UART Bug'] },
    { name: 'Research', labels: ['Frame Interp', 'Survey Notes', 'arXiv 2406', 'Citations'] },
    { name: 'People', labels: ['Mom Birthday', 'Advisor Mtg', 'Team Sync'] },
    { name: 'Workflow', labels: ['Notion Tracker', 'Today Tasks', 'Inbox'] },
    { name: 'System', labels: ['VS Code', 'Terminal Logs', 'File Index'] },
    { name: 'Prefs', labels: ['Concise Tone', 'Cyan Accent', 'Dark Mode'] }
  ]
  const nodes: MemoryNode[] = []
  const edges: MemoryEdge[] = []
  const R = 0.66

  clusters.forEach((c, ci) => {
    const a = (ci / clusters.length) * Math.PI * 2 - Math.PI / 2
    const cx = Math.cos(a) * R
    const cy = Math.sin(a) * R * 0.84
    const hubId = `c${ci}`
    nodes.push({ id: hubId, label: c.name, cluster: ci, x: cx, y: cy, r: 5.5 })
    c.labels.forEach((label, li) => {
      const spread = (li - (c.labels.length - 1) / 2) * 0.46
      const rr = 0.19 + (li % 2) * 0.08
      nodes.push({
        id: `c${ci}n${li}`,
        label,
        cluster: ci,
        x: cx + Math.cos(a + spread) * rr,
        y: cy + Math.sin(a + spread) * rr,
        r: 3.3
      })
      edges.push({ from: hubId, to: `c${ci}n${li}` })
    })
  })
  for (let i = 0; i < clusters.length; i++) {
    edges.push({ from: `c${i}`, to: `c${(i + 2) % clusters.length}` })
  }
  return { nodes, edges }
}

const { nodes, edges } = buildGalaxy()

const hash = (s: string): number => {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

interface MemoryStore {
  nodes: MemoryNode[]
  edges: MemoryEdge[]
  query: string
  activePath: string[]
  searching: boolean
  search: (query: string) => void
}

export const useMemoryStore = create<MemoryStore>((set) => ({
  nodes,
  edges,
  query: '',
  activePath: [],
  searching: false,
  search: (query) => {
    const ci = hash(query || 'memory') % 7
    const cj = (ci + 2) % 7
    const path = [`c${ci}`, `c${ci}n0`, `c${cj}`, `c${cj}n1`]
    set({ query, activePath: path, searching: true })
    setTimeout(() => set({ searching: false }), 2800)
  }
}))
