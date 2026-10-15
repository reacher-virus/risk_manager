import { useState } from 'react'
import { auth } from '../../api'
import { useAuth } from '../../auth/context'
import { Captcha } from '../../components/Captcha'
import { OtpStep } from '../../components/OtpStep'
import { PasswordField } from '../../components/PasswordField'
import { Button, ErrorNote, Field } from '../../components/ui'
import { canAutoFocus } from '../../lib/device'
import { navigate } from '../../lib/route'
import type { Challenge } from '../../types'
import { AuthLayout } from './AuthLayout'
import { useToast } from '@/components/toast-context'

/** The two-step form: (1) email + password + CAPTCHA, (2) the code we email. `admin` switches to the dedicated admin door. */
export function SignInForm({ admin = false }: { admin?: boolean }) {
  const { reload } = useAuth()
  const toast = useToast()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [captcha, setCaptcha] = useState({ captcha_id: '', captcha_answer: '' })
  const [nonce, setNonce] = useState(0)
  const [challenge, setChallenge] = useState<Challenge | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const step1 = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setError(null)
    try { setChallenge(await auth.login({ email, password, ...captcha }, admin)); toast.info('Verification code sent. Check your email.') }
    catch (err) { setError(err as Error); toast.error((err as Error).message); setNonce((n) => n + 1) }   // a CAPTCHA is single-use: always fetch a fresh one
    finally { setBusy(false) }
  }
  const step2 = async (code: string) => {
    if (!challenge) return
    setBusy(true); setError(null)
    try { await auth.loginVerify(challenge.challenge_id, code, admin); setPassword(''); await reload(); toast.success('Signed in. Welcome back!'); navigate('/hero') }
    catch (err) { setError(err as Error); toast.error((err as Error).message) }
    finally { setBusy(false) }
  }

  return (
    <>
      <p className="auth__step">{challenge ? 'Step 2 of 2: verify it is you' : 'Step 1 of 2: your credentials'}</p>
      {!challenge ? (
        <form className="auth-form" onSubmit={step1}>
          <Field label="Email"><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" maxLength={254} required autoFocus={canAutoFocus()} /></Field>
          <PasswordField label="Password" value={password} onChange={setPassword} autoComplete="current-password" />
          <Captcha nonce={nonce} onChange={setCaptcha} />
          <ErrorNote error={error} />
          <Button type="submit" variant="primary" busy={busy}>Continue</Button>
        </form>
      ) : (
        <OtpStep message={challenge.message} busy={busy} error={error} onSubmit={step2}
          onResend={async () => { await auth.resend(challenge.challenge_id); toast.success('A new code is on its way.') }}
          onBack={() => { setChallenge(null); setError(null); setNonce((n) => n + 1) }} />
      )}
    </>
  )
}

export function SignInPage({ admin = false }: { admin?: boolean }) {
  const footer = admin
    ? <a href="#/signin">← Back to the regular sign-in</a>
    : <><a href="#/signup">Create an account</a><a href="#/forgot">Forgot password?</a><a href="#/admin-login">Administrator sign-in</a></>
  return (
    <AuthLayout variant={admin ? 'admin' : 'user'} title={admin ? 'Administrator sign-in' : 'Sign in'} footer={footer}>
      <SignInForm admin={admin} />
    </AuthLayout>
  )
}
