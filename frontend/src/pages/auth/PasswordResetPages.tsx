import { useEffect, useState } from 'react'
import { auth } from '../../api'
import { Captcha } from '../../components/Captcha'
import { PasswordField } from '../../components/PasswordField'
import { canAutoFocus } from '../../lib/device'
import { checkPassword } from '../../lib/password'
import { Button, ErrorNote, Field } from '../../components/ui'
import { AuthLayout } from './AuthLayout'
import { useToast } from '@/components/toast-context'

export function ForgotPage() {
  const toast = useToast()
  const [email, setEmail] = useState('')
  const [captcha, setCaptcha] = useState({ captcha_id: '', captcha_answer: '' })
  const [nonce, setNonce] = useState(0)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setError(null)
    try { setMessage((await auth.forgot({ email, ...captcha })).message); toast.success('If that address has an account, a reset link is on its way.') }
    catch (err) { setError(err as Error); toast.error((err as Error).message); setNonce((n) => n + 1) }
    finally { setBusy(false) }
  }
  return (
    <AuthLayout title="Reset your password" subtitle="We will email a one-time link if the address belongs to an account." footer={<a href="#/signin">← Back to sign in</a>}>
      {message ? <p className="callout" role="status">{message} The link expires in 30 minutes.</p> : (
        <form className="auth-form" onSubmit={submit}>
          <Field label="Email"><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" maxLength={254} required autoFocus={canAutoFocus()} /></Field>
          <Captcha nonce={nonce} onChange={setCaptcha} />
          <ErrorNote error={error} />
          <Button type="submit" variant="primary" busy={busy}>Email me a reset link</Button>
        </form>
      )}
    </AuthLayout>
  )
}

/** The token arrives in the URL fragment (never sent to servers). We move it into memory and scrub it from the address bar. */
export function ResetPage({ token: initial }: { token: string | null }) {
  const toast = useToast()
  const [token] = useState(initial)
  const [pw, setPw] = useState('')
  const [confirm, setConfirm] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => { if (initial) window.history.replaceState(null, '', '#/reset') }, [initial])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (pw !== confirm) { setError(new Error('The two passwords do not match')); return }
    if (!token) return
    setBusy(true); setError(null)
    try { await auth.reset(token, pw); setPw(''); setConfirm(''); setDone(true); toast.success('Password updated. Please sign in.') }
    catch (err) { setError(err as Error); toast.error((err as Error).message) }
    finally { setBusy(false) }
  }
  if (!token && !done) return (
    <AuthLayout title="Reset link needed" footer={<a href="#/forgot">Request a new link</a>}>
      <p className="error-note" role="alert">This page needs the link from your reset email. It may have expired or already been used.</p>
    </AuthLayout>
  )
  return (
    <AuthLayout title="Choose a new password" footer={<a href="#/signin">← Back to sign in</a>}>
      {done ? <p className="callout" role="status">Password updated and all devices signed out. <a href="#/signin">Sign in with your new password.</a></p> : (
        <form className="auth-form" onSubmit={submit}>
          <PasswordField label="New password" value={pw} onChange={setPw} autoComplete="new-password" showRules />
          <PasswordField label="Confirm new password" value={confirm} onChange={setConfirm} autoComplete="new-password" />
          <ErrorNote error={error} />
          <Button type="submit" variant="primary" busy={busy} disabled={!checkPassword(pw).every((r) => r.ok) || pw !== confirm}>Update password</Button>
        </form>
      )}
    </AuthLayout>
  )
}
