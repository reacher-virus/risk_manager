import { describe, expect, it } from 'vitest'
import { savings, savingsPct, nearestPoint } from '../lib/cost'
import { formatINR, formatINRShort, pct, titleCase } from '../lib/format'
import { radialLayout, riskColor } from '../lib/graphLayout'
import type { GraphNode, SweepPoint } from '../types'

describe('format', () => {
  it('formats rupees with Indian digit grouping', () => {
    expect(formatINR(1234567)).toBe('₹12,34,567')
    expect(formatINR(49.6)).toBe('₹50')
  })
  it('abbreviates large amounts', () => {
    expect(formatINRShort(850)).toBe('₹850')
    expect(formatINRShort(250000)).toBe('₹2.5L')
    expect(formatINRShort(30000000)).toBe('₹3.0Cr')
  })
  it('formats percentages and labels', () => {
    expect(pct(0.9437)).toBe('94.4%')
    expect(pct(0.0079, 2)).toBe('0.79%')
    expect(titleCase('HOLD_FOR_VERIFICATION')).toBe('Hold For Verification')
  })
})

describe('cost helpers', () => {
  const sweep: SweepPoint[] = [0.1, 0.3, 0.5].map((t) => ({ threshold: t, precision: 0, recall: 0, fp: 0, fn: 0, total_cost: t * 1000 }))
  it('finds the nearest sweep point', () => {
    expect(nearestPoint(sweep, 0.34)?.threshold).toBe(0.3)
    expect(nearestPoint([], 0.3)).toBeUndefined()
  })
  it('computes savings safely', () => {
    expect(savings(1000, 250)).toBe(750)
    expect(savingsPct(1000, 250)).toBe(75)
    expect(savingsPct(0, 0)).toBe(0)
  })
})

describe('graph layout', () => {
  const nodes: GraphNode[] = [
    { id: 'd:1', type: 'device', label: '1', risk: 0.9, transactions: 3 },
    ...[1, 2, 3, 4].map((i): GraphNode => ({ id: `c:${i}`, type: 'customer', label: `${i}`, risk: 0.5, transactions: 1 })),
    { id: 'p:1', type: 'card', label: '1', risk: 0.1, transactions: 1 },
  ]
  it('puts a lone device at the centre and spreads customers on a circle', () => {
    const placed = radialLayout(nodes, 400)
    const dev = placed.find((n) => n.type === 'device')!
    expect([dev.x, dev.y]).toEqual([200, 200])
    const radii = placed.filter((n) => n.type === 'customer').map((n) => Math.hypot(n.x - 200, n.y - 200))
    radii.forEach((r) => expect(r).toBeCloseTo(radii[0]))
    expect(new Set(placed.map((n) => `${n.x.toFixed(1)},${n.y.toFixed(1)}`)).size).toBe(placed.length)
  })
  it('maps risk to colour bands', () => {
    expect(riskColor(0.9)).toContain('critical')
    expect(riskColor(0.3)).toContain('high')
    expect(riskColor(0.1)).toContain('medium')
    expect(riskColor(0.01)).toContain('low')
  })
})
