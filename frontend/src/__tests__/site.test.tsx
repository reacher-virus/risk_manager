import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../auth/AuthContext'
import Component from '../components/ui/modern-login-signup'
import { ToastProvider } from '../components/Toast'
import { useToast } from '../components/toast-context'
import { cancelSmoothScroll, scrollToSection } from '../lib/scroll'
import { canAutoFocus } from '../lib/device'
import { SITE, copyrightYear, mailto } from '../lib/site'
import { titleFor } from '../lib/title'
import { captcha, comparison, fail, me, mockFetch, summary } from './helpers'

const anon = { 'GET /auth/me': () => fail(401, 'Authentication required'), 'GET /auth/captcha': captcha }
const data = { 'GET /dashboard/summary': summary, 'GET /model-comparison': comparison, 'GET /metrics': { dataset_note: 'x' }, 'GET /alerts': { total: 0, threshold: 0.25, items: [] } }
const clearCookies = () => document.cookie.split('; ').forEach((c) => { document.cookie = `${c.split('=')[0]}=; Max-Age=0; Path=/` })

beforeEach(() => { localStorage.clear(); clearCookies(); document.cookie = 'risk_cookie_notice=1; Path=/' })
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('landing page', () => {
  it('is the home page for visitors, with working calls to action', async () => {
    mockFetch(anon); window.location.hash = '#/'
    render(<App />)
    expect(await screen.findByRole('heading', { level: 1, name: /Stop fraud before it costs you/ })).toBeInTheDocument()
    const hero = screen.getByRole('region', { name: /Stop fraud/ })
    expect(within(hero).getByRole('link', { name: /Create your account/ })).toHaveAttribute('href', '#/signup')
    expect(within(hero).getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '#/signin')
    const closing = screen.getByRole('region', { name: /Ready to see it catch/ })           // the second call to action further down
    expect(within(closing).getByRole('link', { name: /Create your account/ })).toHaveAttribute('href', '#/signup')
    expect(within(closing).getByRole('link', { name: /Email Yash/ })).toHaveAttribute('href', expect.stringContaining('mailto:yashpree237915@gmail.com'))
  })

  it('has every section the navigation points to, and an interactive 3D diagram with a text alternative', async () => {
    mockFetch(anon); window.location.hash = '#/'
    const { container } = render(<App />)
    await screen.findByRole('heading', { level: 1 })
    for (const id of ['features', 'how', 'security', 'results', 'faq']) expect(container.querySelector(`#${id}`), id).not.toBeNull()
    expect(screen.getByRole('img', { name: /Interactive 3D diagram.*Drag to rotate/ })).toBeInTheDocument()
  })

  it('states honestly that the numbers come from synthetic data, and invents no testimonials or prices', async () => {
    mockFetch(anon); window.location.hash = '#/'
    render(<App />)
    await screen.findByRole('heading', { level: 1 })
    expect(screen.getAllByText(/synthetic data/i).length).toBeGreaterThanOrEqual(2)
    expect(document.body.textContent).not.toMatch(/\$\d|per month|testimonial|“.*”\s*[-—]/i)
  })

  it('results table is labelled for phones (stacked cards need data-label on each value)', async () => {
    mockFetch(anon); window.location.hash = '#/'
    const { container } = render(<App />)
    await screen.findByRole('heading', { level: 1 })
    const cells = container.querySelectorAll('#results td')
    expect(cells.length).toBe(8)
    cells.forEach((td) => expect(td.getAttribute('data-label')).toMatch(/^(Rules only|Risk Manager model)$/))
  })

  it('FAQ answers are native <details> (work without scripting)', async () => {
    mockFetch(anon); window.location.hash = '#/'
    const { container } = render(<App />)
    await screen.findByRole('heading', { level: 1 })
    expect(container.querySelectorAll('details.faq__item').length).toBe(5)
  })
})

describe('header, logo and mobile menu', () => {
  it('every logo is a link home (workspace home when signed in)', async () => {
    mockFetch(anon); window.location.hash = '#/'
    const { unmount } = render(<App />)
    await screen.findByRole('heading', { level: 1 })
    const logos = screen.getAllByRole('link', { name: 'Risk Manager home' })
    expect(logos.length).toBeGreaterThanOrEqual(2)                      // header + footer
    logos.forEach((l) => expect(l).toHaveAttribute('href', '#/'))
    unmount()
    mockFetch({ 'GET /auth/me': me('viewer'), ...data }); window.location.hash = '#/hero'
    render(<App />)
    await screen.findByRole('heading', { name: /Welcome back/ })
    expect(screen.getByRole('link', { name: 'Risk Manager home' })).toHaveAttribute('href', '#/hero')
  })

  it('mobile menu opens, announces its state, and closes with the close button, Escape, or a link', async () => {
    mockFetch(anon); window.location.hash = '#/'
    render(<App />)
    await screen.findByRole('heading', { level: 1 })
    const u = userEvent.setup()
    const toggle = screen.getByRole('button', { name: 'Open menu' })
    const panel = document.getElementById('site-menu')!
    expect(toggle).toHaveAttribute('aria-expanded', 'false'); expect(panel).not.toBeVisible()
    await u.click(toggle)
    expect(screen.getByRole('button', { name: /Close menu/, expanded: true })).toBeInTheDocument()
    expect(panel).toBeVisible(); expect(document.body.style.overflow).toBe('hidden')
    expect(within(panel).getByRole('link', { name: 'Get started' })).toHaveAttribute('href', '#/signup')
    await u.click(within(panel).getByRole('button', { name: 'Close menu' }))
    expect(panel).not.toBeVisible(); expect(document.body.style.overflow).not.toBe('hidden')
    await u.click(screen.getByRole('button', { name: 'Open menu' }))
    await u.keyboard('{Escape}')
    expect(panel).not.toBeVisible(); expect(screen.getByRole('button', { name: 'Open menu' })).toHaveFocus()
    await u.click(screen.getByRole('button', { name: 'Open menu' }))
    await u.click(within(panel).getByRole('link', { name: 'Sign in' }))
    expect(panel).not.toBeVisible()
  })

  it('dashboard has the same menu pattern with every section the role may see', async () => {
    mockFetch({ 'GET /auth/me': me('viewer'), ...data }); window.location.hash = '#/app/overview'
    render(<App />)
    await screen.findByText('10,000')
    const u = userEvent.setup()
    await u.click(screen.getByRole('button', { name: 'Open navigation menu' }))
    const panel = document.getElementById('app-menu')!
    const names = within(panel).getAllByRole('button').map((b) => b.textContent)
    expect(names).toEqual(expect.arrayContaining(['Overview', 'Alerts', 'Settings', 'Sign out']))
    expect(names).not.toContain('Users')                                // role-aware, like the desktop tabs
    await u.click(within(panel).getByRole('button', { name: 'Alerts' }))
    await waitFor(() => expect(window.location.hash).toBe('#/app/alerts'))
  })
})

describe('footer', () => {
  it('every link goes somewhere real, external links are safe, and the year is current', async () => {
    mockFetch(anon); window.location.hash = '#/'
    render(<App />)
    await screen.findByRole('heading', { level: 1 })
    const footer = screen.getByRole('contentinfo')
    const links = within(footer).getAllByRole('link')
    links.forEach((a) => { const h = a.getAttribute('href'); expect(h && h !== '#' && h !== '').toBe(true) })
    expect(within(footer).getByRole('link', { name: /Privacy Policy/ })).toHaveAttribute('href', '#/privacy')
    expect(within(footer).getByRole('link', { name: /Terms of Service/ })).toHaveAttribute('href', '#/terms')
    expect(within(footer).getByRole('link', { name: SITE.email })).toHaveAttribute('href', expect.stringContaining('mailto:yashpree237915@gmail.com'))
    const gh = within(footer).getByRole('link', { name: /GitHub/ })
    expect(gh).toHaveAttribute('href', 'https://github.com/reacher-virus/ai-risk-manager'); expect(gh).toHaveAttribute('target', '_blank'); expect(gh.getAttribute('rel')).toMatch(/noopener/)
    expect(footer).toHaveTextContent(`© ${new Date().getFullYear()} Yash. All rights reserved.`)
  })

  it('copyright year is computed, not hard-coded', () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2031-03-04T10:00:00Z'))
    expect(copyrightYear()).toBe(2031)
    vi.setSystemTime(new Date('2027-12-31T23:00:00Z'))
    expect(copyrightYear()).toBe(2027)
  })

  it('mailto links carry an encoded subject', () => {
    expect(mailto('Hello & welcome')).toBe('mailto:yashpree237915@gmail.com?subject=Hello%20%26%20welcome')
  })
})

describe('custom 404, legal pages and page titles', () => {
  it('unknown routes show the 404 with a way home, for visitors and members alike', async () => {
    mockFetch(anon); window.location.hash = '#/definitely-not-a-page'
    const { unmount } = render(<App />)
    expect(await screen.findByRole('heading', { name: 'This page could not be found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to home' })).toHaveAttribute('href', '#/')
    expect(screen.getByRole('link', { name: 'Report a broken link' })).toHaveAttribute('href', expect.stringContaining('mailto:'))
    expect(document.title).toBe('Page not found · Risk Manager')
    unmount()
    mockFetch({ 'GET /auth/me': me('viewer'), ...data }); window.location.hash = '#/app-typo'
    render(<App />)
    expect(await screen.findByRole('link', { name: 'Go to your workspace' })).toHaveAttribute('href', '#/hero')
  })

  it('privacy and terms pages exist and are reachable by anyone', async () => {
    mockFetch(anon)
    for (const [hash, title] of [['#/privacy', 'Privacy Policy'], ['#/terms', 'Terms of Service']]) {
      window.location.hash = hash
      const { unmount } = render(<App />)
      expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument()
      expect(document.title).toBe(`${title} · Risk Manager`)
      unmount()
    }
  })

  it('titles describe the page (and the 404 wins over a lookalike path)', () => {
    expect(titleFor('/')).toBe('Risk Manager: AI fraud detection that explains every decision')
    expect(titleFor('/signin')).toBe('Sign in · Risk Manager')
    expect(titleFor('/app/threshold')).toBe('Threshold & cost · Risk Manager')
    expect(titleFor('/app')).toBe('Overview · Risk Manager')
    expect(titleFor('/hero')).toBe('Welcome · Risk Manager')
    expect(titleFor('/nope')).toBe('Page not found · Risk Manager')
    expect(titleFor('/signin', true)).toBe('Page not found · Risk Manager')
  })

  it('the document title follows navigation', async () => {
    mockFetch(anon); window.location.hash = '#/signup'
    render(<App />)
    await screen.findByRole('heading', { name: 'Create your account' })
    expect(document.title).toBe('Create your account · Risk Manager')
    act(() => { window.location.hash = '#/forgot' })
    await screen.findByRole('heading', { name: 'Reset your password' })
    expect(document.title).toBe('Reset your password · Risk Manager')
  })
})

describe('login component', () => {
  it('toggles between sign in and sign up like the original, with no dead social buttons', async () => {
    mockFetch(anon)
    render(<AuthProvider><Component /></AuthProvider>)
    expect(await screen.findByRole('heading', { name: 'Sign in to Account' })).toBeInTheDocument()
    expect(screen.queryByText(/Continue with (Google|GitHub|Apple)/)).not.toBeInTheDocument()
    const u = userEvent.setup()
    await u.click(screen.getByRole('button', { name: 'Sign up' }))
    expect(screen.getByRole('heading', { name: 'Sign up for Account' })).toBeInTheDocument()
    expect(screen.getByLabelText('Full name')).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(screen.getByRole('heading', { name: 'Sign in to Account' })).toBeInTheDocument()
  })

  it('shell links to the real legal pages and is dark-only', async () => {
    mockFetch(anon); window.location.hash = '#/signin'
    const { container } = render(<App />)
    await screen.findByRole('heading', { name: 'Sign in' })
    expect(screen.getByRole('link', { name: 'Terms of Service' })).toHaveAttribute('href', '#/terms')
    expect(screen.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute('href', '#/privacy')
    expect(container.querySelector('.auth.force-dark')).not.toBeNull()
    expect(container.querySelector('canvas.dotbg')).not.toBeNull()
    expect(screen.getByRole('link', { name: 'Risk Manager home' })).toHaveAttribute('href', '#/')
  })

  it('does not auto-focus fields on phones, but does on desktop with a mouse', () => {
    const mm = (matches: boolean) => vi.stubGlobal('matchMedia', () => ({ matches, addEventListener() {}, removeEventListener() {} }))
    mm(false); expect(canAutoFocus()).toBe(false)
    mm(true); expect(canAutoFocus()).toBe(true)
  })
})

describe('success and error messages (toasts)', () => {
  function Demo() {
    const t = useToast()
    return (<><button onClick={() => t.success('Saved it')}>ok</button><button onClick={() => t.error('Could not save')}>bad</button><button onClick={() => t.info('FYI')}>info</button></>)
  }

  it('announces success politely and errors assertively, and can be dismissed', async () => {
    const u = userEvent.setup()
    render(<ToastProvider><Demo /></ToastProvider>)
    await u.click(screen.getByText('ok')); await u.click(screen.getByText('bad'))
    expect(screen.getByRole('status')).toHaveTextContent('Saved it')
    expect(screen.getByRole('alert')).toHaveTextContent('Could not save')
    await u.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Dismiss notification' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('disappears on its own (errors stay longer) and never stacks more than four', async () => {
    vi.useFakeTimers()
    render(<ToastProvider><Demo /></ToastProvider>)
    const click = (label: string) => act(() => { screen.getByText(label).click() })
    click('ok'); click('bad')
    act(() => { vi.advanceTimersByTime(5000) })
    expect(screen.queryByText('Saved it')).not.toBeInTheDocument()
    expect(screen.getByText('Could not save')).toBeInTheDocument()
    act(() => { vi.advanceTimersByTime(4000) })
    expect(screen.queryByText('Could not save')).not.toBeInTheDocument()
    for (let i = 0; i < 7; i++) click('info')
    expect(screen.getAllByText('FYI').length).toBe(4)
  })

  it('is safe to call outside a provider', () => {
    function Lone() { useToast().error('nobody listens'); return <p>fine</p> }
    render(<Lone />)
    expect(screen.getByText('fine')).toBeInTheDocument()
  })

  it('a failed sign-in shows an error message, and a good flow confirms with a success message', async () => {
    const m = mockFetch({ ...anon, 'POST /auth/login': () => fail(401, 'Invalid email, password or CAPTCHA.') })
    window.location.hash = '#/signin'
    const { container } = render(<App />)
    const u = userEvent.setup()
    await u.type(await screen.findByLabelText(/^Email/), 'ana@example.org')
    await u.type(screen.getByLabelText('Password'), 'Wrong-Password-1!')
    await u.type(await screen.findByLabelText(/Type the characters/), 'KMPRT')
    await u.click(screen.getByRole('button', { name: 'Continue' }))
    await waitFor(() => expect(container.querySelector('.toast--error')).toHaveTextContent('Invalid email, password or CAPTCHA.'))
    expect(m.count('POST /auth/login')).toBe(1)
  })
})

describe('section scrolling', () => {
  it('scrolls to a section under the sticky header and can be cancelled by the user', () => {
    window.location.hash = '#/'
    document.body.innerHTML = '<div id="faq"></div>'
    vi.spyOn(document.getElementById('faq')!, 'getBoundingClientRect').mockReturnValue({ top: 500 } as DOMRect)
    vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} }))         // reduced motion: jump
    scrollToSection('faq')
    expect(window.scrollTo).toHaveBeenLastCalledWith(0, 440)                                                         // 500 minus the 60px header
    expect(() => cancelSmoothScroll()).not.toThrow()
  })

  it('from another page it goes home first, then scrolls', () => {
    vi.useFakeTimers()
    window.location.hash = '#/terms'
    document.body.innerHTML = '<div id="security"></div>'
    vi.spyOn(document.getElementById('security')!, 'getBoundingClientRect').mockReturnValue({ top: 300 } as DOMRect)
    vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} }))
    scrollToSection('security')
    expect(window.location.hash).toBe('#/')
    act(() => { vi.advanceTimersByTime(100) })
    expect(window.scrollTo).toHaveBeenLastCalledWith(0, 240)
  })
})
