import type {
  AlertDetail, AlertList, AuditRow, BatchResult, BreakdownRow, Comparison, Config, Confusion, Metrics, Monitoring,
  PRCurve, PredictResult, RingGraph, Ring, Scenario, SimResult, Summary, ThresholdAnalysis, TimePoint,
  AdminUser, CaptchaChallenge, Challenge, Me, User,
} from './types'

export const API_BASE: string =
  import.meta.env.VITE_API_BASE ||
  (import.meta.env.DEV ? 'http://localhost:8000' : '/api')
export const SESSION_EXPIRED_EVENT = 'risk:session-expired'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** The CSRF token is the one cookie page JavaScript may read (the session cookies are HttpOnly). */
export function csrfToken(): string {
  const hit = document.cookie.split('; ').find((c) => c.split('=')[0].endsWith('risk_csrf'))
  return hit ? decodeURIComponent(hit.slice(hit.indexOf('=') + 1)) : ''
}

const SAFE = new Set(['GET', 'HEAD', 'OPTIONS'])
let refreshing: Promise<boolean> | null = null

/** One shared refresh at a time: concurrent 401s wait for the same rotation instead of burning the token twice. */
function refreshSession(): Promise<boolean> {
  refreshing ??= fetch(`${API_BASE}/auth/refresh`, { method: 'POST', credentials: 'include', headers: { 'X-CSRF-Token': csrfToken() } })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => { refreshing = null })
  return refreshing
}

async function raw(path: string, init: RequestInit = {}, canRetry = true): Promise<Response> {
  const headers = new Headers(init.headers)
  const method = (init.method ?? 'GET').toUpperCase()
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (!SAFE.has(method)) headers.set('X-CSRF-Token', csrfToken())
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: 'include' })
  } catch {
    throw new ApiError(0, `Cannot reach the backend at ${API_BASE}. Is it running?`)
  }
  if (res.status === 401 && canRetry && !path.startsWith('/auth/')) {
    if (await refreshSession()) return raw(path, init, false)
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
  }
  if (!res.ok) {
    let detail = res.statusText
    try { const j = await res.json(); detail = typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: { msg?: string }) => d.msg).join('; ') : JSON.stringify(j.detail) } catch { /* not json */ }
    throw new ApiError(res.status, detail)
  }
  return res
}

const json = async <T,>(path: string, init?: RequestInit): Promise<T> => (await raw(path, init)).json() as Promise<T>
const body = (method: string, data?: unknown): RequestInit => ({ method, body: data === undefined ? undefined : JSON.stringify(data) })
const qs = (o: Record<string, string | number | undefined | null>): string => {
  const p = new URLSearchParams()
  Object.entries(o).forEach(([k, v]) => v !== undefined && v !== null && v !== '' && p.set(k, String(v)))
  const s = p.toString()
  return s ? `?${s}` : ''
}

/** Authenticated file download (a plain <a href> cannot attach the CSRF header or be rate-limited per user). */
export async function download(path: string, filename: string): Promise<void> {
  const blob = await (await raw(path)).blob()
  const url = URL.createObjectURL(blob)
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
}

export interface AlertQuery { limit?: number; offset?: number; min_level?: string; status?: string; source?: string; sort?: string }

export interface Captcha { captcha_id: string; captcha_answer: string }

export const auth = {
  captcha: () => json<CaptchaChallenge>('/auth/captcha'),
  me: () => json<Me>('/auth/me'),
  signup: (d: { email: string; password: string; full_name: string } & Captcha) => json<Challenge>('/auth/signup', body('POST', d)),
  signupVerify: (challenge_id: string, code: string) => json<{ message: string }>('/auth/signup/verify', body('POST', { challenge_id, code })),
  resend: (challenge_id: string) => json<{ message: string }>('/auth/otp/resend', body('POST', { challenge_id })),
  login: (d: { email: string; password: string } & Captcha, admin = false) => json<Challenge>(admin ? '/auth/admin/login' : '/auth/login', body('POST', d)),
  loginVerify: (challenge_id: string, code: string, admin = false) => json<{ user: User }>(admin ? '/auth/admin/login/verify' : '/auth/login/verify', body('POST', { challenge_id, code })),
  logout: () => json<{ ok: boolean }>('/auth/logout', body('POST')),
  logoutAll: () => json<{ ok: boolean }>('/auth/logout-all', body('POST')),
  forgot: (d: { email: string } & Captcha) => json<{ message: string }>('/auth/password/forgot', body('POST', d)),
  reset: (token: string, new_password: string) => json<{ message: string }>('/auth/password/reset', body('POST', { token, new_password })),
  changePassword: (current_password: string, new_password: string) => json<{ message: string }>('/auth/password/change', body('POST', { current_password, new_password })),
}

export const api = {
  summary: () => json<Summary>('/dashboard/summary'),
  metrics: () => json<Metrics>('/metrics'),
  comparison: () => json<Comparison>('/model-comparison'),
  config: () => json<Config>('/config'),
  setCosts: (cost_fp: number, cost_fn: number) => json<Config>('/config/costs', body('PUT', { cost_fp, cost_fn })),
  setThreshold: (threshold: number | null) => json<Config>('/config/threshold', body('PUT', { threshold })),

  alerts: (q: AlertQuery) => json<AlertList>(`/alerts${qs({ ...q })}`),
  alert: (id: string) => json<AlertDetail>(`/alerts/${encodeURIComponent(id)}`),
  review: (id: string, data: { action?: string; label?: string; note?: string }) =>
    json<{ status: string; label: string | null }>(`/alerts/${encodeURIComponent(id)}/review`, body('POST', data)),
  exportAlerts: (q: AlertQuery) => download(`/alerts/export.csv${qs({ min_level: q.min_level, status: q.status, source: q.source })}`, 'alerts.csv'),

  predict: (tx: Record<string, unknown>) => json<PredictResult>('/predict', body('POST', tx)),
  simulate: (scenario: Scenario, n: number) => json<{ scenario: string; results: SimResult[] }>('/simulate', body('POST', { scenario, n })),
  batch: (file: File) => { const f = new FormData(); f.append('file', file); return json<BatchResult>('/predict/batch', { method: 'POST', body: f }) },
  downloadBatch: (id: string) => download(`/predict/batch/${id}/download`, `scored_${id}.csv`),

  threshold: (q: { threshold?: number; cost_fp?: number; cost_fn?: number; split?: string }) => json<ThresholdAnalysis>(`/analysis/threshold${qs({ ...q })}`),
  timeseries: (bucket: string) => json<TimePoint[]>(`/analytics/timeseries${qs({ bucket })}`),
  breakdown: (by: string) => json<BreakdownRow[]>(`/analytics/breakdown${qs({ by })}`),
  prCurve: (split = 'test') => json<PRCurve>(`/analytics/pr-curve${qs({ split })}`),
  confusion: (threshold?: number, split = 'test') => json<Confusion>(`/analytics/confusion${qs({ threshold, split })}`),

  rings: (min_accounts: number) => json<{ total: number; rings: Ring[] }>(`/graph/rings${qs({ min_accounts })}`),
  ring: (id: string) => json<RingGraph>(`/graph/rings/${encodeURIComponent(id)}`),

  monitoring: () => json<Monitoring>('/monitoring/summary'),
  retrain: () => json<{ state: string }>('/admin/retrain', { method: 'POST' }),
  retrainStatus: () => json<Monitoring['retrain']>('/admin/retrain/status'),
  audit: (limit = 100) => json<AuditRow[]>(`/audit${qs({ limit })}`),

  users: (q: { q?: string; role?: string; status?: string; limit?: number; offset?: number }) => json<{ total: number; items: AdminUser[] }>(`/admin/users${qs({ ...q })}`),
  patchUser: (id: string, d: { role?: string; status?: string }) => json<AdminUser>(`/admin/users/${encodeURIComponent(id)}`, body('PATCH', d)),
  revokeSessions: (id: string) => json<{ ok: boolean }>(`/admin/users/${encodeURIComponent(id)}/revoke-sessions`, body('POST')),
  webhook: () => json<{ url: string | null }>('/admin/webhook'),
  setWebhook: (url: string | null) => json<{ url: string | null }>('/admin/webhook', body('PUT', { url })),
  testWebhook: () => json<{ delivered: boolean; status: number }>('/admin/webhook/test', body('POST')),
}
