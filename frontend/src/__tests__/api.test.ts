import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, SESSION_EXPIRED_EVENT, api, auth, csrfToken } from '../api'
import { fail, mockFetch } from './helpers'

const setCsrf = (v: string, name = 'risk_csrf') => { document.cookie = `${name}=${v}; Path=/` }
const clearCookies = () => document.cookie.split('; ').forEach((c) => { document.cookie = `${c.split('=')[0]}=; Max-Age=0; Path=/` })

describe('api client (cookie sessions)', () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear(); clearCookies(); vi.restoreAllMocks() })
  afterEach(() => vi.unstubAllGlobals())

  it('always sends cookies and never an API key or bearer token', async () => {
    const m = mockFetch({ 'GET /config': {} })
    await api.config()
    const init = m.calls[0].init!
    expect(init.credentials).toBe('include')
    const h = init.headers as Headers
    expect(h.has('X-API-Key')).toBe(false)
    expect(h.has('Authorization')).toBe(false)
  })

  it('adds the CSRF header to state-changing requests only', async () => {
    setCsrf('tok123')
    const m = mockFetch({ 'GET /config': {}, 'PUT /config/costs': {}, 'POST /alerts/T1/review': {} })
    await api.config()
    await api.setCosts(1, 2)
    await api.review('T1', { action: 'HOLD' })
    const hdr = (i: number) => m.calls[i].init!.headers as Headers
    expect(hdr(0).has('X-CSRF-Token')).toBe(false)
    expect(hdr(1).get('X-CSRF-Token')).toBe('tok123')
    expect(hdr(2).get('X-CSRF-Token')).toBe('tok123')
  })

  it('reads the CSRF token from the __Secure- prefixed cookie used over https', () => {
    // jsdom runs on http:// where browsers refuse __Secure- cookies, so stub the cookie string instead of setting one
    const spy = vi.spyOn(document, 'cookie', 'get').mockReturnValue('theme=dark; __Secure-risk_csrf=pre%2Ffixed; other=1')
    expect(csrfToken()).toBe('pre/fixed')
    spy.mockReturnValue('theme=dark')
    expect(csrfToken()).toBe('')
    spy.mockRestore()
  })

  it('silently refreshes once on 401 and retries the original request', async () => {
    let first = true
    const m = mockFetch({
      'GET /alerts': () => { if (first) { first = false; return fail(401, 'Invalid or expired session') } return { total: 0, threshold: 0.2, items: [] } },
      'POST /auth/refresh': { user: {} },
    })
    await expect(api.alerts({})).resolves.toMatchObject({ total: 0 })
    expect(m.count('POST /auth/refresh')).toBe(1)
    expect(m.count('GET /alerts')).toBe(2)
  })

  it('signals session expiry (and gives up) when the refresh fails', async () => {
    const onExpired = vi.fn()
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired)
    const m = mockFetch({ 'GET /alerts': () => fail(401, 'expired'), 'POST /auth/refresh': () => fail(401, 'Session expired') })
    await expect(api.alerts({})).rejects.toMatchObject({ status: 401 })
    expect(onExpired).toHaveBeenCalledTimes(1)
    expect(m.count('GET /alerts')).toBe(1)                      // no retry loop
    window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired)
  })

  it('concurrent 401s share ONE refresh (rotating tokens must not be spent twice)', async () => {
    const seen = new Set<string>()
    const m = mockFetch({
      'GET /alerts': () => { if (!seen.has('a')) { seen.add('a'); return fail(401, 'x') } return { total: 0, threshold: 0, items: [] } },
      'GET /metrics': () => { if (!seen.has('m')) { seen.add('m'); return fail(401, 'x') } return {} },
      'POST /auth/refresh': {},
    })
    await Promise.all([api.alerts({}), api.metrics()])
    expect(m.count('POST /auth/refresh')).toBe(1)
  })

  it('does not try to refresh when an /auth endpoint itself returns 401', async () => {
    const m = mockFetch({ 'POST /auth/login': () => fail(401, 'Invalid email, password or CAPTCHA.') })
    await expect(auth.login({ email: 'a@b.co', password: 'x', captcha_id: '1', captcha_answer: 'y' })).rejects.toMatchObject({ status: 401, message: 'Invalid email, password or CAPTCHA.' })
    expect(m.count('POST /auth/refresh')).toBe(0)
  })

  it('uses the dedicated admin endpoints for admin sign-in', async () => {
    const m = mockFetch({ 'POST /auth/admin/login': { challenge_id: 'c' }, 'POST /auth/admin/login/verify': { user: {} }, 'POST /auth/login': {} })
    await auth.login({ email: 'a@b.co', password: 'x', captcha_id: '1', captcha_answer: 'y' }, true)
    await auth.loginVerify('c', '123456', true)
    expect(m.calls.map((c) => c.key)).toEqual(['POST /auth/admin/login', 'POST /auth/admin/login/verify'])
  })

  it('turns FastAPI string and validation-array errors into readable messages', async () => {
    mockFetch({ 'PUT /config/costs': () => fail(403, 'Admin role required') })
    await expect(api.setCosts(1, 2)).rejects.toMatchObject({ status: 403, message: 'Admin role required' })
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: [{ msg: 'String should have at least 6 characters' }] }), { status: 422 }))))
    await expect(auth.signupVerify('c', '1')).rejects.toMatchObject({ status: 422, message: 'String should have at least 6 characters' })
  })

  it('reports an unreachable backend as status 0', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    const err = await api.summary().catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(0)
  })

  it('builds query strings (skipping empties) and encodes ids in paths', async () => {
    const m = mockFetch({ 'GET /alerts': { total: 0, threshold: 0, items: [] }, 'POST /alerts/TX%2F1%20x/review': { status: 'HELD', label: null } })
    await api.alerts({ limit: 10, min_level: 'HIGH', status: '', source: undefined })
    expect(m.calls[0].url).toContain('limit=10')
    expect(m.calls[0].url).not.toContain('status=')
    await api.review('TX/1 x', { action: 'HOLD' })
    expect(m.calls[1].url).toContain('TX%2F1%20x')
  })

  it('never writes tokens or secrets to web storage', async () => {
    mockFetch({ 'POST /auth/login/verify': { user: {} }, 'GET /auth/me': {} })
    await auth.loginVerify('c', '123456')
    await auth.me()
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })
})
