import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { SESSION_EXPIRED_EVENT, auth } from '../api'
import { useToast } from '../components/toast-context'
import { navigate } from '../lib/route'
import type { User } from '../types'
import { AuthCtx, type Status } from './context'

/** Session state comes from the server (HttpOnly cookies); nothing secret is ever kept in JavaScript or web storage. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUser] = useState<User | null>(null)
  const [adminSession, setAdminSession] = useState(false)
  const toast = useToast()

  const reload = useCallback(async () => {
    try {
      const me = await auth.me()
      setUser(me.user); setAdminSession(me.admin_session); setStatus('authed')
    } catch {
      setUser(null); setAdminSession(false); setStatus('anon')
    }
  }, [])

  useEffect(() => {
    void reload()
    const expired = () => { setUser(null); setStatus('anon') }
    window.addEventListener(SESSION_EXPIRED_EVENT, expired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expired)
  }, [reload])

  const signOut = useCallback(async () => {
    try { await auth.logout() } catch { /* the cookies are cleared server-side when reachable; either way we leave */ }
    setUser(null); setStatus('anon'); toast.info('You have been signed out.'); navigate('/signin', true)
  }, [toast])

  const value = useMemo(() => ({ status, user, role: user?.role ?? null, adminSession, reload, signOut }), [status, user, adminSession, reload, signOut])
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}
