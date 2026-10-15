import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { captcha, comparison, fail, me, mockFetch, summary } from './helpers'

const data = { 'GET /dashboard/summary': summary, 'GET /model-comparison': comparison, 'GET /metrics': { dataset_note: 'Synthetic dataset note.' },
  'GET /alerts': { total: 0, threshold: 0.25, items: [] } }
const clearCookies = () => document.cookie.split('; ').forEach((c) => { document.cookie = `${c.split('=')[0]}=; Max-Age=0; Path=/` })

describe('route guard', () => {
  beforeEach(() => { localStorage.clear(); clearCookies(); document.cookie = 'risk_cookie_notice=1; Path=/' })
  afterEach(() => vi.unstubAllGlobals())

  it('sends a signed-out visitor from any protected route to the sign-in page', async () => {
    mockFetch({ 'GET /auth/me': () => fail(401, 'Authentication required'), 'GET /auth/captcha': captcha })
    for (const target of ['#/hero', '#/app/alerts', '#/app/users']) {
      window.location.hash = target
      const { unmount } = render(<App />)
      expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
      await waitFor(() => expect(window.location.hash).toBe('#/signin'))
      unmount()
    }
  })

  it('lets signed-out visitors reach sign-up, forgot-password and the admin door', async () => {
    mockFetch({ 'GET /auth/me': () => fail(401, 'x'), 'GET /auth/captcha': captcha })
    for (const [hash, title] of [['#/signup', 'Create your account'], ['#/forgot', 'Reset your password'], ['#/admin-login', 'Administrator sign-in']]) {
      window.location.hash = hash
      const { unmount } = render(<App />)
      expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument()
      unmount()
    }
  })

  it('signed-in users land on the hero page and never see the auth forms again', async () => {
    mockFetch({ 'GET /auth/me': me('viewer'), ...data })
    window.location.hash = '#/signin'
    render(<App />)
    expect(await screen.findByRole('heading', { name: /Welcome back, Ana/ })).toBeInTheDocument()
    await waitFor(() => expect(window.location.hash).toBe('#/hero'))
    expect(screen.getByText('viewer', { selector: '.chip' })).toBeInTheDocument()
  })

  it('hero offers only what the role may use', async () => {
    mockFetch({ 'GET /auth/me': me('viewer'), ...data })
    window.location.hash = '#/hero'
    const { unmount } = render(<App />)
    await screen.findByRole('heading', { name: /Welcome back/ })
    expect(screen.queryByText('User management')).not.toBeInTheDocument()
    expect(screen.queryByText('Simulator', { selector: 'h3' })).not.toBeInTheDocument()
    unmount()
    mockFetch({ 'GET /auth/me': me('admin'), ...data })
    render(<App />)
    expect(await screen.findByText('User management')).toBeInTheDocument()
    expect(screen.getByText('Administrator session')).toBeInTheDocument()
  })

  it('the dashboard hides tabs above the role (server still enforces) and deep-links by hash', async () => {
    mockFetch({ 'GET /auth/me': me('viewer'), ...data })
    window.location.hash = '#/app/overview'
    const { unmount } = render(<App />)
    await screen.findByText('10,000')
    const nav = screen.getByRole('navigation', { name: 'Sections' })
    expect(nav).toHaveTextContent('Alerts')
    expect(nav).not.toHaveTextContent('Users')
    expect(nav).not.toHaveTextContent('Simulator')
    unmount()
    mockFetch({ 'GET /auth/me': me('admin'), ...data })
    window.location.hash = '#/app/overview'
    render(<App />)
    await screen.findByText('10,000')
    expect(screen.getByRole('navigation', { name: 'Sections' })).toHaveTextContent('Users')
  })

  it('a viewer who types the admin URL gets the overview, not the user list', async () => {
    const m = mockFetch({ 'GET /auth/me': me('viewer'), ...data })
    window.location.hash = '#/app/users'
    render(<App />)
    await screen.findByText('10,000')
    expect(m.count('GET /admin/users')).toBe(0)
  })

  it('sign-out clears the session client-side and returns to sign-in', async () => {
    const m = mockFetch({ 'GET /auth/me': me('viewer'), 'POST /auth/logout': { ok: true }, 'GET /auth/captcha': captcha, ...data })
    window.location.hash = '#/hero'
    const u = userEvent.setup()
    render(<App />)
    await screen.findByRole('heading', { name: /Welcome back/ })
    await u.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(await screen.findByText('You have been signed out.')).toBeInTheDocument()      // visible confirmation
    expect(m.count('POST /auth/logout')).toBe(1)
    expect(window.location.hash).toBe('#/signin')
  })

  it('an expired session mid-use drops the user back to sign-in', async () => {
    let n = 0
    mockFetch({ 'GET /auth/me': () => (n++ === 0 ? me('viewer') : fail(401, 'x')), 'GET /dashboard/summary': () => fail(401, 'expired'), 'GET /model-comparison': () => fail(401, 'expired'),
      'GET /metrics': () => fail(401, 'expired'), 'GET /alerts': () => fail(401, 'expired'), 'POST /auth/refresh': () => fail(401, 'Session expired'), 'GET /auth/captcha': captcha })
    window.location.hash = '#/app/overview'
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('shows the cookie notice on first visit', async () => {
    clearCookies()
    mockFetch({ 'GET /auth/me': () => fail(401, 'x'), 'GET /auth/captcha': captcha })
    window.location.hash = '#/signin'
    render(<App />)
    expect(await screen.findByRole('region', { name: /cookie notice/i })).toBeInTheDocument()
  })
})
