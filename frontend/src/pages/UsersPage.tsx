import { useState } from 'react'
import { api } from '../api'
import { Button, Card, ErrorNote, Field, Loading } from '../components/ui'
import { useAsync, useDebounced } from '../hooks'
import { formatTime } from '../lib/format'
import { useToast } from '@/components/toast-context'

export function UsersPage() {
  const [q, setQ] = useState('')
  const [role, setRole] = useState('')
  const [status, setStatus] = useState('')
  const dq = useDebounced(q, 300)
  const users = useAsync(() => api.users({ q: dq, role, status, limit: 50 }), [dq, role, status])
  const [err, setErr] = useState<Error | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const toast = useToast()

  const act = async (fn: () => Promise<unknown>, done: string) => {
    setErr(null); setMsg(null)
    try { await fn(); setMsg(done); toast.success(done); users.reload() } catch (e) { setErr(e as Error); toast.error((e as Error).message) }
  }

  return (
    <div className="stack">
      <Card title="Users" subtitle="Change access or end sessions. Administrator accounts are managed from the server console, not here.">
        <div className="filters">
          <label>Search<input value={q} onChange={(e) => setQ(e.target.value)} placeholder="name or email" maxLength={100} /></label>
          <label>Role<select value={role} onChange={(e) => setRole(e.target.value)}><option value="">All</option><option>viewer</option><option>analyst</option><option>admin</option></select></label>
          <label>Status<select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option><option>active</option><option>disabled</option></select></label>
          <span className="filters__count">{users.data?.total ?? 0} users</span>
        </div>
        <ErrorNote error={users.error ?? err} onRetry={users.reload} />
        {msg && <p className="callout" role="status">{msg}</p>}
        {!users.data && !users.error ? <Loading /> : (
          <div className="table-wrap"><table className="table table--stack">
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Last sign-in</th><th /></tr></thead>
            <tbody>{users.data?.items.map((u) => {
              const locked = u.role === 'admin'
              return (
                <tr key={u.id}>
                  <td data-label="Name">{u.full_name}</td><td className="mono" data-label="Email">{u.email}</td>
                  <td data-label="Role">{locked ? <span className="chip chip--role-admin">admin</span> : (
                    <select value={u.role} aria-label={`Role for ${u.email}`} onChange={(e) => void act(() => api.patchUser(u.id!, { role: e.target.value }), `Role updated for ${u.email}`)}>
                      <option value="viewer">viewer</option><option value="analyst">analyst</option></select>)}</td>
                  <td data-label="Status"><span className={`chip chip--status-${u.status}`}>{u.status}</span></td>
                  <td data-label="Last sign-in">{u.last_login_at ? formatTime(u.last_login_at) : 'never'}</td>
                  <td className="actions">{!locked && <>
                    <Button variant="ghost" onClick={() => void act(() => api.patchUser(u.id!, { status: u.status === 'active' ? 'disabled' : 'active' }), `${u.status === 'active' ? 'Disabled' : 'Enabled'} ${u.email}`)}>{u.status === 'active' ? 'Disable' : 'Enable'}</Button>
                    <Button variant="ghost" onClick={() => void act(() => api.revokeSessions(u.id!), `Signed ${u.email} out everywhere`)}>Sign out everywhere</Button></>}</td>
                </tr>)
            })}</tbody>
          </table></div>)}
      </Card>
      <WebhookCard />
    </div>
  )
}

function WebhookCard() {
  const current = useAsync(api.webhook, [])
  const toast = useToast()
  const [url, setUrl] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<Error | null>(null)
  const value = url ?? current.data?.url ?? ''
  const run = async (fn: () => Promise<string>) => { setErr(null); setMsg(null); try { const m = await fn(); setMsg(m); toast.success(m); current.reload() } catch (e) { setErr(e as Error); toast.error((e as Error).message) } }
  return (
    <Card title="Critical-alert webhook" subtitle="POSTs a signed JSON event when a transaction scores CRITICAL. https only; private, loopback and cloud-metadata addresses are always refused.">
      <Field label="Webhook URL" hint="Example: https://hooks.example.com/risk. Each request carries an X-Risk-Signature (HMAC-SHA256) header."><input type="url" value={value} onChange={(e) => setUrl(e.target.value)} maxLength={2048} /></Field>
      <div className="btn-row">
        <Button variant="primary" onClick={() => void run(async () => { await api.setWebhook(value || null); return value ? 'Webhook saved.' : 'Webhook removed.' })}>Save</Button>
        <Button onClick={() => void run(async () => { const r = await api.testWebhook(); return r.delivered ? `Delivered (HTTP ${r.status}).` : `Receiver answered HTTP ${r.status}.` })}>Send test event</Button>
      </div>
      {msg && <p className="callout" role="status">{msg}</p>}
      <ErrorNote error={err} />
    </Card>
  )
}
