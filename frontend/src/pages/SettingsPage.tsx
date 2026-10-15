import { useState } from 'react'
import { api, auth } from '../api'
import { useAuth } from '../auth/context'
import { PasswordField } from '../components/PasswordField'
import { checkPassword } from '../lib/password'
import { Button, Card, ErrorNote, Field, Loading } from '../components/ui'
import { useAsync } from '../hooks'
import { formatTime } from '../lib/format'
import { useToast } from '@/components/toast-context'

export function SettingsPage({ theme, onTheme, onChanged }: { theme: string; onTheme: (t: 'dark' | 'light') => void; onChanged: () => void }) {
  const { user, signOut } = useAuth()
  const cfg = useAsync(api.config, [])
  const toast = useToast()
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<Error | null>(null)
  const [fp, setFp] = useState('')
  const [fn, setFn] = useState('')
  const [cur, setCur] = useState('')
  const [next, setNext] = useState('')
  const c = cfg.data

  const saveCosts = async () => {
    setErr(null); setMsg(null)
    try { await api.setCosts(Number(fp || c?.cost_fp), Number(fn || c?.cost_fn)); setMsg('Costs updated.'); toast.success('Business costs updated.'); cfg.reload(); onChanged() } catch (e) { setErr(e as Error); toast.error((e as Error).message) }
  }
  const changePw = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null); setMsg(null)
    try { await auth.changePassword(cur, next); setCur(''); setNext(''); toast.success('Password changed. Please sign in again.'); await signOut() } catch (e2) { setErr(e2 as Error); toast.error((e2 as Error).message) }
  }
  return (
    <div className="stack">
      <Card title="Your account" subtitle="Stored securely: your password is hashed with Argon2id and never kept in readable form.">
        <dl className="facts">
          <dt>Name</dt><dd>{user?.full_name}</dd><dt>Email</dt><dd>{user?.email}</dd><dt>Role</dt><dd>{user?.role}</dd>
          <dt>Member since</dt><dd>{user?.created_at ? formatTime(user.created_at) : 'n/a'}</dd>
        </dl>
        <div className="btn-row"><Button onClick={() => void signOut()}>Sign out</Button>
          <Button variant="danger" onClick={async () => { try { await auth.logoutAll(); await signOut() } catch (e) { setErr(e as Error) } }}>Sign out on every device</Button></div>
      </Card>
      <Card title="Change password" subtitle="You will be signed out everywhere afterwards.">
        <form className="auth-form" onSubmit={changePw}>
          <PasswordField label="Current password" value={cur} onChange={setCur} autoComplete="current-password" />
          <PasswordField label="New password" value={next} onChange={setNext} autoComplete="new-password" showRules email={user?.email} />
          <Button type="submit" variant="primary" disabled={!cur || !checkPassword(next, user?.email).every((r) => r.ok)}>Change password</Button>
        </form>
      </Card>
      <Card title="Business costs" subtitle="Used for expected-loss numbers everywhere (admin only)">
        {!c && !cfg.error ? <Loading /> : c && (
          <div className="form-grid">
            <Field label={`False-alarm cost (now ₹${c.cost_fp})`}><input type="number" min="1" placeholder={String(c.cost_fp)} value={fp} onChange={(e) => setFp(e.target.value)} /></Field>
            <Field label={`Missed-fraud cost (now ₹${c.cost_fn})`}><input type="number" min="1" placeholder={String(c.cost_fn)} value={fn} onChange={(e) => setFn(e.target.value)} /></Field>
          </div>)}
        <Button onClick={saveCosts}>Save costs</Button>
        {c && <p className="note">Deployed threshold {c.threshold.toFixed(2)} (trained value {c.trained_threshold.toFixed(2)}). Adjust it in the Threshold tab. Outcomes reach the model {c.label_delay_days} days after a transaction.</p>}
        {msg && <p className="callout" role="status">{msg}</p>}
        <ErrorNote error={err ?? cfg.error} />
      </Card>
      <Card title="Appearance">
        <div className="btn-row">
          <Button variant={theme === 'dark' ? 'primary' : 'default'} onClick={() => onTheme('dark')}>Dark</Button>
          <Button variant={theme === 'light' ? 'primary' : 'default'} onClick={() => onTheme('light')}>Light</Button>
        </div>
      </Card>
    </div>
  )
}
