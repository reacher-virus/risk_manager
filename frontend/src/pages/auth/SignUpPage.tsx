import { useState } from 'react'
import { auth } from '../../api'
import { Captcha } from '../../components/Captcha'
import { OtpStep } from '../../components/OtpStep'
import { PasswordField } from '../../components/PasswordField'
import { canAutoFocus } from '../../lib/device'
import { checkPassword } from '../../lib/password'
import { Button, ErrorNote, Field } from '../../components/ui'
import type { Challenge } from '../../types'
import { AuthLayout } from './AuthLayout'
import { useToast } from '@/components/toast-context'

export function SignUpForm() {
  const toast = useToast()
  const [form, setForm] = useState({ full_name: '', email: '', password: '', confirm: '' })
  const [captcha, setCaptcha] = useState({ captcha_id: '', captcha_answer: '' })
  const [nonce, setNonce] = useState(0)
  const [challenge, setChallenge] = useState<Challenge | null>(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const set = (k: keyof typeof form) => (v: string) => setForm({ ...form, [k]: v })
  const rulesOk = checkPassword(form.password, form.email).every((r) => r.ok)
  const mismatch = form.confirm.length > 0 && form.confirm !== form.password

  const step1 = async (e: React.FormEvent) => {
    e.preventDefault()
    if (form.password !== form.confirm) { setError(new Error('The two passwords do not match')); return }
    setBusy(true); setError(null)
    try { setChallenge(await auth.signup({ email: form.email, password: form.password, full_name: form.full_name, ...captcha })); toast.info('Verification code sent. Check your email.') }
    catch (err) { setError(err as Error); toast.error((err as Error).message); setNonce((n) => n + 1) }
    finally { setBusy(false) }
  }
  const step2 = async (code: string) => {
    if (!challenge) return
    setBusy(true); setError(null)
    try { await auth.signupVerify(challenge.challenge_id, code); setForm({ full_name: '', email: '', password: '', confirm: '' }); setDone(true); toast.success('Email verified. You can sign in now.') }
    catch (err) { setError(err as Error); toast.error((err as Error).message) }
    finally { setBusy(false) }
  }

  if (done) return (
    <>
      <p className="callout">Your account is ready. For your security you now sign in with your password plus a fresh emailed code.</p>
      <a className="btn btn--primary" href="#/signin">Go to sign in →</a>
    </>
  )
  return (
    <>
      <p className="auth__step">{challenge ? 'Step 2 of 2: confirm your email' : 'Step 1 of 2: your details'}</p>
      {!challenge ? (
        <form className="auth-form" onSubmit={step1}>
          <Field label="Full name"><input value={form.full_name} onChange={(e) => set('full_name')(e.target.value)} autoComplete="name" maxLength={80} required autoFocus={canAutoFocus()} /></Field>
          <Field label="Email" hint="Use a real inbox you can open: we send a code to prove it is yours. Disposable addresses are not accepted.">
            <input type="email" value={form.email} onChange={(e) => set('email')(e.target.value)} autoComplete="email" maxLength={254} required />
          </Field>
          <PasswordField label="Password" value={form.password} onChange={set('password')} autoComplete="new-password" showRules email={form.email} />
          <PasswordField label="Confirm password" value={form.confirm} onChange={set('confirm')} autoComplete="new-password" />
          {mismatch && <p className="note" role="status">Passwords do not match yet.</p>}
          <Captcha nonce={nonce} onChange={setCaptcha} />
          <ErrorNote error={error} />
          <Button type="submit" variant="primary" busy={busy} disabled={!rulesOk || mismatch}>Send verification code</Button>
        </form>
      ) : (
        <OtpStep message={challenge.message} busy={busy} error={error} onSubmit={step2}
          onResend={async () => { await auth.resend(challenge.challenge_id); toast.success('A new code is on its way.') }}
          onBack={() => { setChallenge(null); setError(null); setNonce((n) => n + 1) }} />
      )}
    </>
  )
}

export function SignUpPage() {
  return (
    <AuthLayout title="Create your account" footer={<>Already registered? <a href="#/signin">Sign in</a></>}>
      <SignUpForm />
    </AuthLayout>
  )
}
