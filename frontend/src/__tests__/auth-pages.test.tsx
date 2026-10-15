import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { CookieBanner } from '../components/CookieBanner'
import { checkPassword } from '../lib/password'
import { parseHash } from '../lib/route'
import { ForgotPage, ResetPage } from '../pages/auth/PasswordResetPages'
import { SignInPage } from '../pages/auth/SignInPage'
import { SignUpPage } from '../pages/auth/SignUpPage'
import { captcha, fail, me, mockFetch } from './helpers'

const GOOD_PW = 'Tr1cky-Horse-Battery!'
const wrap = (ui: React.ReactElement) => render(<AuthProvider>{ui}</AuthProvider>)
const clearCookies = () => document.cookie.split('; ').forEach((c) => { document.cookie = `${c.split('=')[0]}=; Max-Age=0; Path=/` })

describe('route parsing', () => {
  it('splits path and query from the hash', () => {
    expect(parseHash('#/reset?token=abc_-9')).toMatchObject({ path: '/reset' })
    expect(parseHash('#/reset?token=abc_-9').params.get('token')).toBe('abc_-9')
    expect(parseHash('')).toMatchObject({ path: '/' })
    expect(parseHash('#hero').path).toBe('/hero')
    expect(parseHash('#/app/alerts').path).toBe('/app/alerts')
  })
})

describe('password hints', () => {
  it('flags each rule the server also enforces', () => {
    const ok = (pw: string, email = '') => checkPassword(pw, email).every((r) => r.ok)
    expect(ok(GOOD_PW)).toBe(true)
    expect(ok('short1A!')).toBe(false)
    expect(ok('alllowercaselettersonly')).toBe(true)         // 20+ chars passphrase rule
    expect(ok('alllowercase')).toBe(false)                    // 12 chars, one class
    expect(ok('Xx-janedoe42-Zz-99!', 'janedoe42@example.org')).toBe(false)
    expect(ok('aaaaAAAA1111!!!!')).toBe(false)
  })
})

describe('sign-in (two steps)', () => {
  beforeEach(() => { window.location.hash = ''; clearCookies() })
  afterEach(() => vi.unstubAllGlobals())

  const routes = (extra = {}) => ({
    'GET /auth/me': () => fail(401, 'Authentication required'), 'GET /auth/captcha': captcha,
    'POST /auth/login': { challenge_id: 'c'.repeat(32), mfa_required: true, expires_in: 600, message: 'Password accepted. Enter the 6-digit code we emailed you.' },
    'POST /auth/login/verify': { user: me().user }, ...extra,
  })

  it('asks for the emailed code only after the password step, then lands on the hero page', async () => {
    const m = mockFetch(routes())
    const u = userEvent.setup()
    wrap(<SignInPage />)
    expect(await screen.findByText('Step 1 of 2: your credentials')).toBeInTheDocument()
    await u.type(screen.getByLabelText(/^Email/), 'ana@example.org')
    await u.type(screen.getByLabelText('Password'), GOOD_PW)
    await u.type(await screen.findByLabelText(/Type the characters/), 'KMPRT')
    await u.click(screen.getByRole('button', { name: 'Continue' }))
    const login = m.calls.find((c) => c.key === 'POST /auth/login')!
    expect(JSON.parse(login.init!.body as string)).toEqual({ email: 'ana@example.org', password: GOOD_PW, captcha_id: captcha.captcha_id, captcha_answer: 'KMPRT' })
    expect(await screen.findByText('Step 2 of 2: verify it is you')).toBeInTheDocument()
    expect(m.count('POST /auth/login/verify')).toBe(0)       // not signed in yet
    m.fn.mockClear()
    mockFetch({ ...routes(), 'GET /auth/me': me() })         // after verification the server session exists
    await u.type(screen.getByRole('textbox', { name: /6-digit/ }), '123456')
    await u.click(screen.getByRole('button', { name: 'Verify' }))
    await waitFor(() => expect(window.location.hash).toBe('#/hero'))
  })

  it('shows the server error, clears nothing sensitive, and fetches a fresh CAPTCHA after a failure', async () => {
    const m = mockFetch(routes({ 'POST /auth/login': () => fail(401, 'Invalid email, password or CAPTCHA.') }))
    const u = userEvent.setup()
    wrap(<SignInPage />)
    await u.type(screen.getByLabelText(/^Email/), 'ana@example.org')
    await u.type(screen.getByLabelText('Password'), 'wrong-password-123')
    await u.type(await screen.findByLabelText(/Type the characters/), 'XXXXX')
    await u.click(screen.getByRole('button', { name: 'Continue' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email, password or CAPTCHA.')
    await waitFor(() => expect(m.count('GET /auth/captcha')).toBe(2))      // CAPTCHAs are single-use
    expect(screen.queryByText('Step 2 of 2: verify it is you')).not.toBeInTheDocument()
  })

  it('wrong code keeps the user on step 2 with the server message', async () => {
    mockFetch(routes({ 'POST /auth/login/verify': () => fail(401, 'Invalid or expired code.') }))
    const u = userEvent.setup()
    wrap(<SignInPage />)
    await u.type(screen.getByLabelText(/^Email/), 'ana@example.org')
    await u.type(screen.getByLabelText('Password'), GOOD_PW)
    await u.type(await screen.findByLabelText(/Type the characters/), 'KMPRT')
    await u.click(screen.getByRole('button', { name: 'Continue' }))
    await u.type(await screen.findByRole('textbox', { name: /6-digit/ }), '000000')
    await u.click(screen.getByRole('button', { name: 'Verify' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid or expired code.')
    expect(screen.getByText('Step 2 of 2: verify it is you')).toBeInTheDocument()
  })

  it('the code box accepts digits only and Verify needs all six', async () => {
    mockFetch(routes())
    const u = userEvent.setup()
    wrap(<SignInPage />)
    await u.type(screen.getByLabelText(/^Email/), 'ana@example.org')
    await u.type(screen.getByLabelText('Password'), GOOD_PW)
    await u.type(await screen.findByLabelText(/Type the characters/), 'KMPRT')
    await u.click(screen.getByRole('button', { name: 'Continue' }))
    const box = await screen.findByRole('textbox', { name: /6-digit/ })
    await u.type(box, '12ab34')
    expect(box).toHaveValue('1234')
    expect(screen.getByRole('button', { name: 'Verify' })).toBeDisabled()
  })

  it('the administrator door uses the dedicated endpoints and looks different', async () => {
    const m = mockFetch(routes({ 'POST /auth/admin/login': { challenge_id: 'c'.repeat(32), mfa_required: true, expires_in: 600, message: 'ok' } }))
    const u = userEvent.setup()
    const { container } = wrap(<SignInPage admin />)
    expect(await screen.findByRole('heading', { name: 'Administrator sign-in' })).toBeInTheDocument()
    expect(container.querySelector('.auth--admin')).toBeInTheDocument()
    await u.type(screen.getByLabelText(/^Email/), 'boss@example.org')
    await u.type(screen.getByLabelText('Password'), GOOD_PW)
    await u.type(await screen.findByLabelText(/Type the characters/), 'KMPRT')
    await u.click(screen.getByRole('button', { name: 'Continue' }))
    await screen.findByText('Step 2 of 2: verify it is you')
    expect(m.count('POST /auth/admin/login')).toBe(1)
    expect(m.count('POST /auth/login')).toBe(0)
  })
})

describe('sign-up', () => {
  beforeEach(() => { window.location.hash = '' })
  afterEach(() => vi.unstubAllGlobals())

  it('blocks submission until the password meets the rules and both entries match, then verifies the email', async () => {
    const m = mockFetch({
      'GET /auth/me': () => fail(401, 'x'), 'GET /auth/captcha': captcha,
      'POST /auth/signup': { challenge_id: 'd'.repeat(32), expires_in: 600, message: 'If the details are valid, we have emailed a 6-digit verification code.' },
      'POST /auth/signup/verify': { message: 'Email verified.' },
    })
    const u = userEvent.setup()
    wrap(<SignUpPage />)
    const send = await screen.findByRole('button', { name: 'Send verification code' })
    await u.type(screen.getByLabelText('Full name'), 'Ana Roy')
    await u.type(screen.getByLabelText(/^Email/), 'ana@example.org')
    await u.type(screen.getByLabelText('Password'), 'weak')
    expect(send).toBeDisabled()
    await u.clear(screen.getByLabelText('Password'))
    await u.type(screen.getByLabelText('Password'), GOOD_PW)
    await u.type(screen.getByLabelText('Confirm password'), 'Different-Pass-9!')
    expect(send).toBeDisabled()
    await u.clear(screen.getByLabelText('Confirm password'))
    await u.type(screen.getByLabelText('Confirm password'), GOOD_PW)
    await u.type(await screen.findByLabelText(/Type the characters/), 'KMPRT')
    expect(send).toBeEnabled()
    await u.click(send)
    const body = JSON.parse(m.calls.find((c) => c.key === 'POST /auth/signup')!.init!.body as string)
    expect(Object.keys(body).sort()).toEqual(['captcha_answer', 'captcha_id', 'email', 'full_name', 'password'])   // no role / confirm fields leave the browser
    expect(await screen.findByText('Step 2 of 2: confirm your email')).toBeInTheDocument()
    await u.type(screen.getByRole('textbox', { name: /6-digit/ }), '654321')
    await u.click(screen.getByRole('button', { name: 'Verify' }))
    expect(await screen.findByText(/Your account is ready/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Go to sign in/ })).toHaveAttribute('href', '#/signin')
  })
})

describe('password reset pages', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('forgot: shows the same neutral message whatever the server says about the account', async () => {
    mockFetch({ 'GET /auth/me': () => fail(401, 'x'), 'GET /auth/captcha': captcha, 'POST /auth/password/forgot': { message: 'If an account exists for that email, a password reset link has been sent.' } })
    const u = userEvent.setup()
    wrap(<ForgotPage />)
    await u.type(screen.getByLabelText(/^Email/), 'anyone@example.org')
    await u.type(await screen.findByLabelText(/Type the characters/), 'KMPRT')
    await u.click(screen.getByRole('button', { name: 'Email me a reset link' }))
    expect(await screen.findByRole('status')).toHaveTextContent('If an account exists')
  })

  it('reset: scrubs the token from the address bar, enforces matching strong passwords, and submits the token in the body', async () => {
    window.history.replaceState(null, '', '#/reset?token=' + 'T'.repeat(43))
    const m = mockFetch({ 'GET /auth/me': () => fail(401, 'x'), 'POST /auth/password/reset': { message: 'Password updated.' } })
    const u = userEvent.setup()
    wrap(<ResetPage token={'T'.repeat(43)} />)
    await waitFor(() => expect(window.location.hash).toBe('#/reset'))              // token no longer visible / shareable
    const submit = screen.getByRole('button', { name: 'Update password' })
    await u.type(screen.getByLabelText('New password'), 'weak')
    expect(submit).toBeDisabled()
    await u.clear(screen.getByLabelText('New password'))
    await u.type(screen.getByLabelText('New password'), GOOD_PW)
    await u.type(screen.getByLabelText('Confirm new password'), GOOD_PW)
    await u.click(submit)
    const call = m.calls.find((c) => c.key === 'POST /auth/password/reset')!
    expect(JSON.parse(call.init!.body as string)).toEqual({ token: 'T'.repeat(43), new_password: GOOD_PW })
    expect(call.url).not.toContain('token=')                                       // never in a URL
    expect(await screen.findByRole('status')).toHaveTextContent('Password updated')
  })

  it('reset without a token explains what to do', () => {
    mockFetch({ 'GET /auth/me': () => fail(401, 'x') })
    wrap(<ResetPage token={null} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/link from your reset email/i)
  })
})

describe('cookie notice', () => {
  beforeEach(clearCookies)

  it('shows until acknowledged, then remembers via a cookie', async () => {
    const u = userEvent.setup()
    const { container, rerender } = render(<CookieBanner />)
    expect(screen.getByRole('region', { name: /cookie notice/i })).toHaveTextContent(/strictly necessary/i)
    await u.click(screen.getByRole('button', { name: 'Got it' }))
    expect(container).toBeEmptyDOMElement()
    expect(document.cookie).toContain('risk_cookie_notice=1')
    rerender(<CookieBanner />)
    expect(container).toBeEmptyDOMElement()
  })
})
