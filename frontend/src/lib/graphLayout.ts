import type { GraphNode } from '../types'

export interface Placed extends GraphNode { x: number; y: number }

/** Deterministic concentric layout: devices in the centre, customers in a ring around them, cards on the outside. */
export function radialLayout(nodes: GraphNode[], size = 560): Placed[] {
  const c = size / 2
  const radius = { device: size * 0.12, customer: size * 0.29, card: size * 0.44 } as const
  const groups = { device: [] as GraphNode[], customer: [] as GraphNode[], card: [] as GraphNode[] }
  nodes.forEach((n) => groups[n.type].push(n))
  const out: Placed[] = []
  ;(Object.keys(groups) as (keyof typeof groups)[]).forEach((type) => {
    const list = groups[type]
    list.forEach((n, i) => {
      if (type === 'device' && list.length === 1) { out.push({ ...n, x: c, y: c }); return }
      const angle = (2 * Math.PI * i) / list.length - Math.PI / 2 + (type === 'card' ? Math.PI / list.length : 0)
      out.push({ ...n, x: c + radius[type] * Math.cos(angle), y: c + radius[type] * Math.sin(angle) })
    })
  })
  return out
}

export const riskColor = (risk: number): string =>
  risk >= 0.5 ? 'var(--risk-critical)' : risk >= 0.2 ? 'var(--risk-high)' : risk >= 0.05 ? 'var(--risk-medium)' : 'var(--risk-low)'
