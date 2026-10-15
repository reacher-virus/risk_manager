import type { SweepPoint } from '../types'

/** Nearest sweep point for a threshold (the slider moves in 0.01 steps, the sweep in 0.02). */
export function nearestPoint(sweep: SweepPoint[], threshold: number): SweepPoint | undefined {
  return sweep.reduce<SweepPoint | undefined>(
    (best, p) => (!best || Math.abs(p.threshold - threshold) < Math.abs(best.threshold - threshold) ? p : best),
    undefined,
  )
}

export const savings = (noModel: number, withModel: number): number => noModel - withModel
export const savingsPct = (noModel: number, withModel: number): number => (noModel > 0 ? ((noModel - withModel) / noModel) * 100 : 0)
