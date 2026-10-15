import { useState } from 'react'
import { Button } from './ui'

const NAME = 'risk_cookie_notice'
const seen = (): boolean => document.cookie.split('; ').some((c) => c.startsWith(`${NAME}=`))

/** We only set strictly-necessary cookies (session + CSRF), so this is a notice, not a consent gate. Remembered in a cookie. */
export function CookieBanner() {
  const [hidden, setHidden] = useState(seen())
  if (hidden) return null
  const accept = () => {
    const secure = window.location.protocol === 'https:' ? '; Secure' : ''
    document.cookie = `${NAME}=1; Max-Age=31536000; Path=/; SameSite=Lax${secure}`
    setHidden(true)
  }
  return (
    <aside className="cookie-banner" role="region" aria-label="Cookie notice">
      <p>This site uses <strong>strictly necessary cookies</strong> only: they keep you signed in and protect against forged requests. No tracking, no advertising cookies.</p>
      <Button variant="primary" onClick={accept}>Got it</Button>
    </aside>
  )
}
