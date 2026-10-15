import { vi } from 'vitest'

type Handler = unknown | ((init: RequestInit | undefined, url: string) => unknown)
export type Routes = Record<string, Handler>

/** fetch stub keyed by "METHOD /path". A handler may return plain data (200), a Response, or throw. Unlisted routes return 404. */
export function mockFetch(routes: Routes) {
  const calls: { key: string; init?: RequestInit; url: string }[] = []
  const fn = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const path = url.replace(/^https?:\/\/[^/]+/, '').split('?')[0]
    const key = `${(init?.method ?? 'GET').toUpperCase()} ${path}`
    calls.push({ key, init, url })
    const h = routes[key]
    if (h === undefined) return Promise.resolve(new Response(JSON.stringify({ detail: `no mock for ${key}` }), { status: 404 }))
    const out = typeof h === 'function' ? (h as (i: RequestInit | undefined, u: string) => unknown)(init, url) : h
    if (out instanceof Response) return Promise.resolve(out)
    return Promise.resolve(new Response(JSON.stringify(out), { status: 200, headers: { 'Content-Type': 'application/json' } }))
  })
  vi.stubGlobal('fetch', fn)
  return { fn, calls, count: (key: string) => calls.filter((c) => c.key === key).length }
}

export const fail = (status: number, detail: string) => new Response(JSON.stringify({ detail }), { status, headers: { 'Content-Type': 'application/json' } })

export const user = (role: 'viewer' | 'analyst' | 'admin' = 'viewer') => ({
  id: 'u1', email: `${role}@example.org`, full_name: 'Ana Roy', role, created_at: '2026-08-01T10:00:00', last_login_at: null,
})
export const me = (role: 'viewer' | 'analyst' | 'admin' = 'viewer') => ({ authenticated: true, via: 'cookie', admin_session: role === 'admin', user: user(role) })
export const captcha = { captcha_id: 'a'.repeat(32), image: 'data:image/png;base64,iVBORw0KGgo=', expires_in: 300 }

export const summary = { transactions_analyzed: 10000, suspicious_transactions: 300, high_risk_transactions: 250, estimated_loss_prevented: 500000,
  precision: 0.8, recall: 0.9, pr_auc: 0.85, false_positive_rate: 0.01, threshold: 0.25, live_scored: 3, live_flagged: 1, open_alerts: 7 }
export const comparison = { rule_based: { precision: .4, recall: .5, f1: .4, pr_auc: .3, fp: 100, fn: 120, fp_cost: 15000, fn_cost: 300000 },
  ml_model: { precision: .8, recall: .9, f1: .85, pr_auc: .85, fp: 70, fn: 20, fp_cost: 10500, fn_cost: 50000 }, model_name: 'random_forest', cost_reduction_pct: 80.8 }
