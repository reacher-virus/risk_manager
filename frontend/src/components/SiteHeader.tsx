import { useContext, useState } from 'react'
import { Moon, Sun } from 'lucide-react'
import { Logo } from '@/components/Logo'
import { MobileMenu } from '@/components/MobileMenu'
import { ScrollLink } from '@/components/ScrollLink'
import { AuthCtx } from '@/auth/context'
import { SECTIONS } from '@/lib/site'
import { useTheme } from '@/lib/theme'

/** Public-site header: clickable logo, section links, sign-in / get-started, theme toggle and a mobile menu. */
export function SiteHeader() {
  const [open, setOpen] = useState(false)
  const [theme, toggle] = useTheme()
  const signedIn = useContext(AuthCtx)?.status === 'authed'
  const close = () => setOpen(false)
  const links = SECTIONS.map(([id, label]) => <ScrollLink key={id} to={id} onNavigate={close}>{label}</ScrollLink>)
  return (
    <header className="site-header">
      <div className="site-header__bar">
        <div className="site-header__brand"><Logo size={36} /><a className="site-header__name" href="#/">Risk Manager</a></div>
        <nav className="site-nav" aria-label="Main">{links}</nav>
        <div className="site-header__actions">
          <button className="icon-btn" onClick={toggle} aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}>{theme === 'dark' ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}</button>
          {signedIn
            ? <a className="btn btn--primary site-header__cta" href="#/hero">Open workspace</a>
            : <><a className="btn btn--ghost site-header__signin" href="#/signin">Sign in</a><a className="btn btn--primary site-header__cta" href="#/signup">Get started</a></>}
          <MobileMenu id="site-menu" open={open} onToggle={() => setOpen((o) => !o)} onClose={close}>
            <nav className="menu-list" aria-label="Mobile">
              {links}
              {signedIn
                ? <a className="btn btn--primary" href="#/hero" onClick={close}>Open workspace</a>
                : <><a href="#/signin" onClick={close}>Sign in</a><a className="btn btn--primary" href="#/signup" onClick={close}>Get started</a></>}
            </nav>
          </MobileMenu>
        </div>
      </div>
    </header>
  )
}
