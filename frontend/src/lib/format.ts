export const formatINR = (n: number): string => `₹${Math.round(n).toLocaleString('en-IN')}`

export const formatINRShort = (n: number): string => {
  const a = Math.abs(n)
  if (a >= 1e7) return `₹${(n / 1e7).toFixed(1)}Cr`
  if (a >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`
  return formatINR(n)
}

export const pct = (x: number, digits = 1): string => `${(x * 100).toFixed(digits)}%`

export const formatTime = (iso: string): string => {
  const d = new Date(iso.includes('T') || iso.includes('Z') ? iso : iso.replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
}

export const titleCase = (s: string): string => s.replace(/_/g, ' ').toLowerCase().replace(/^\w|\s\w/g, (c) => c.toUpperCase())
