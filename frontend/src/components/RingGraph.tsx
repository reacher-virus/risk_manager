import { useMemo } from 'react'
import type { RingGraph as RG } from '../types'
import { radialLayout, riskColor } from '../lib/graphLayout'

const SIZE = 560

/** Concentric network view: devices in the centre, accounts around them, cards outside. Colour = risk. */
export function RingGraph({ graph }: { graph: RG }) {
  const placed = useMemo(() => radialLayout(graph.nodes, SIZE), [graph])
  const byId = useMemo(() => new Map(placed.map((n) => [n.id, n])), [placed])
  return (
    <svg className="ring-graph" viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`Network ${graph.ring_id}`}>
      {graph.edges.map((e, i) => {
        const s = byId.get(e.source), t = byId.get(e.target)
        return s && t ? <line key={i} x1={s.x} y1={s.y} x2={t.x} y2={t.y} className="ring-graph__edge" strokeWidth={Math.min(1 + e.weight * 0.4, 4)} /> : null
      })}
      {placed.map((n) => (
        <g key={n.id} transform={`translate(${n.x},${n.y})`} className={`ring-graph__node ring-graph__node--${n.type}`}>
          <title>{`${n.type}: ${n.label}\nrisk ${(n.risk * 100).toFixed(0)}% · ${n.transactions} tx`}</title>
          {n.type === 'customer' ? <circle r={9 + Math.min(n.transactions, 6)} fill={riskColor(n.risk)} />
            : n.type === 'device' ? <rect x={-10} y={-10} width={20} height={20} rx={3} fill={riskColor(n.risk)} />
            : <polygon points="0,-10 10,0 0,10 -10,0" fill={riskColor(n.risk)} />}
        </g>
      ))}
    </svg>
  )
}
