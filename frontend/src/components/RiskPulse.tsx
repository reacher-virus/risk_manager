import { useMemo } from 'react'
import type { RiskLevel } from '../types'

const seeded = (seed: string, i: number): number => {
  let h = 0
  for (const ch of `${seed}-${i}`) h = ((h << 5) - h + ch.charCodeAt(0)) | 0
  return (Math.abs(h) % 1000) / 1000
}

/** Tiny waveform whose height encodes the risk score; colour is set by the `.pulse--LEVEL` class. */
export function RiskPulse({ score, level, seed, bars = 9 }: { score: number; level: RiskLevel; seed: string; bars?: number }) {
  const heights = useMemo(() => Array.from({ length: bars }, (_, i) => {
    const mid = (bars - 1) / 2
    const shape = 1 - Math.abs(i - mid) / mid
    return Math.min(1, Math.max(0.08, score * (0.4 + 0.6 * shape) * (0.55 + seeded(seed, i) * 0.5)))
  }), [score, seed, bars])
  return (
    <div className={`pulse pulse--${level}`} role="img" aria-label={`Risk ${(score * 100).toFixed(0)}%`}>
      {heights.map((h, i) => <span key={i} style={{ height: `${Math.max(10, h * 100)}%` }} />)}
    </div>
  )
}
