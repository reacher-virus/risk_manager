import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { AuthProvider } from './auth/AuthContext'
import { atLeast, useAuth } from './auth/context'
import { AlertDetail } from './components/AlertDetail'
import { CookieBanner } from './components/CookieBanner'
import { Logo } from './components/Logo'
import { MobileMenu } from './components/MobileMenu'
import { ToastProvider } from './components/Toast'
import { navigate, useRoute } from './lib/route'
import { cancelSmoothScroll } from './lib/scroll'
import { useTheme } from './lib/theme'
import { titleFor } from './lib/title'
import { AlertsPage } from './pages/AlertsPage'
import { BatchPage } from './pages/BatchPage'
import { HeroPage } from './pages/HeroPage'
import { LandingPage } from './pages/LandingPage'
import { PrivacyPage, TermsPage } from './pages/LegalPages'
import { MonitoringPage } from './pages/MonitoringPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { OverviewPage } from './pages/OverviewPage'
import { RingsPage } from './pages/RingsPage'
import { SettingsPage } from './pages/SettingsPage'
import { SimulatorPage } from './pages/SimulatorPage'
import { UsersPage } from './pages/UsersPage'
import { SignInPage } from './pages/auth/SignInPage'
import { SignUpPage } from './pages/auth/SignUpPage'
import { ForgotPage, ResetPage } from './pages/auth/PasswordResetPages'
import type { Role } from './types'

// recharts is heavy: load the two chart-driven pages only when their tab is opened
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })))
const ThresholdPage = lazy(() => import('./pages/ThresholdPage').then((m) => ({ default: m.ThresholdPage })))

const TABS: { id: string; label: string; min: Role }[] = [
  { id: 'overview', label: 'Overview', min: 'viewer' }, { id: 'alerts', label: 'Alerts', min: 'viewer' }, { id: 'simulator', label: 'Simulator', min: 'analyst' },
  { id: 'threshold', label: 'Threshold & cost', min: 'viewer' }, { id: 'rings', label: 'Networks', min: 'viewer' }, { id: 'analytics', label: 'Analytics', min: 'viewer' },
  { id: 'monitoring', label: 'Monitoring', min: 'viewer' }, { id: 'batch', label: 'Batch CSV', min: 'analyst' }, { id: 'users', label: 'Users', min: 'admin' },
  { id: 'settings', label: 'Settings', min: 'viewer' },
]
const SIGNED_OUT_ONLY = ['/signin', '/signup', '/admin-login', '/forgot']
const KNOWN = ['/', '/signin', '/signup', '/admin-login', '/forgot', '/reset', '/terms', '/privacy', '/hero']

function Dashboard({ tab }: { tab: string }) {
  const { user, role, signOut } = useAuth()
  const [theme, toggleTheme] = useTheme()
  const [openTx, setOpenTx] = useState<string | null>(null)
  const [ring, setRing] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [menu, setMenu] = useState(false)
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), [])
  const closeMenu = useCallback(() => setMenu(false), [])
  const visible = TABS.filter((t) => atLeast(role, t.min))
  const current = visible.find((t) => t.id === tab)?.id ?? 'overview'
  const go = (id: string) => { closeMenu(); navigate(`/app/${id}`) }
  const openRing = (id: string) => { setRing(id); go('rings') }
  const tabButtons = (cls: string) => visible.map((t) => (
    <button key={t.id} className={`${cls} ${current === t.id ? `${cls}--active` : ''}`} aria-current={current === t.id ? 'page' : undefined} onClick={() => go(t.id)}>{t.label}</button>
  ))

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <Logo href="#/hero" size={36} />
          <div><a className="brand__name" href="#/hero">Risk Manager</a><div className="brand__tag">Defense-only loss detection</div></div>
        </div>
        <nav className="tabs" aria-label="Sections">{tabButtons('tab')}</nav>
        <div className="userbar"><span className="userbar__name" title={user?.email}>{user?.full_name}</span> <span className={`chip chip--role-${role}`}>{role}</span>
          <button className="btn btn--ghost" onClick={toggleTheme} aria-label="Toggle theme">{theme === 'dark' ? '☀' : '☾'}</button>
          <button className="btn btn--ghost userbar__signout" onClick={() => void signOut()}>Sign out</button>
          <MobileMenu id="app-menu" label="navigation menu" open={menu} onToggle={() => setMenu((m) => !m)} onClose={closeMenu}>
            <nav className="menu-list" aria-label="Sections (mobile)">
              {tabButtons('menu-tab')}
              <a href="#/hero" onClick={closeMenu}>Workspace home</a>
              <button className="menu-tab" onClick={() => { closeMenu(); void signOut() }}>Sign out</button>
            </nav>
          </MobileMenu>
        </div>
      </header>
      <main className="page">
        <Suspense fallback={<div className="loading" role="status">Loading…</div>}>
          {current === 'overview' && <OverviewPage onOpen={setOpenTx} onNavigate={go} refreshKey={refreshKey} />}
          {current === 'alerts' && <AlertsPage onOpen={setOpenTx} refreshKey={refreshKey} />}
          {current === 'simulator' && <SimulatorPage onOpen={setOpenTx} onChanged={refresh} />}
          {current === 'threshold' && <ThresholdPage onChanged={refresh} />}
          {current === 'rings' && <RingsPage selected={ring} onSelect={setRing} refreshKey={refreshKey} />}
          {current === 'analytics' && <AnalyticsPage refreshKey={refreshKey} />}
          {current === 'monitoring' && <MonitoringPage onChanged={refresh} refreshKey={refreshKey} />}
          {current === 'batch' && <BatchPage onOpen={setOpenTx} />}
          {current === 'users' && <UsersPage />}
          {current === 'settings' && <SettingsPage theme={theme} onTheme={(t) => { if (t !== theme) toggleTheme() }} onChanged={refresh} />}
        </Suspense>
      </main>
      <footer className="footer">Defense-only system: no fraud generation, exploit guidance, or autonomous financial action. Metrics are on synthetic data.</footer>
      {openTx && <AlertDetail txId={openTx} onClose={() => setOpenTx(null)} onChanged={refresh} onOpenRing={openRing} />}
    </div>
  )
}

/** Route guard + page chooser. Signed-out visitors see the public site; members never see the sign-in forms; unknown URLs get the 404. */
function Shell() {
  const { status } = useAuth()
  const { path, params } = useRoute()
  const signedIn = status === 'authed'
  const isApp = path === '/app' || path.startsWith('/app/')
  const notFound = !(KNOWN.includes(path) || isApp)
  const redirect = status === 'anon' && (path === '/hero' || isApp) ? '/signin'
    : signedIn && (path === '/' || SIGNED_OUT_ONLY.includes(path)) ? '/hero' : null

  useEffect(() => { document.title = titleFor(path, notFound) }, [path, notFound])
  useEffect(() => { cancelSmoothScroll(); window.scrollTo(0, 0) }, [path])      // a section scroll still running must not carry over to the next page
  useEffect(() => { if (redirect) navigate(redirect, true) }, [redirect])

  if (status === 'loading' || redirect) return <div className="loading" role="status">Loading…</div>
  if (notFound) return <NotFoundPage signedIn={signedIn} />
  if (path === '/terms') return <TermsPage />
  if (path === '/privacy') return <PrivacyPage />
  if (path === '/reset') return <ResetPage token={params.get('token')} />
  if (signedIn) return path === '/hero' ? <HeroPage /> : <Dashboard tab={path.split('/')[2] ?? 'overview'} />
  if (path === '/signup') return <SignUpPage />
  if (path === '/admin-login') return <SignInPage admin />
  if (path === '/forgot') return <ForgotPage />
  if (path === '/signin') return <SignInPage />
  return <LandingPage />
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <Shell />
        <CookieBanner />
      </AuthProvider>
    </ToastProvider>
  )
}
