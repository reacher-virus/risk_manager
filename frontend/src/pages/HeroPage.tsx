import { api } from '../api'
import { atLeast, useAuth } from '../auth/context'
import { Logo } from '../components/Logo'
import { Card, Stat } from '../components/ui'
import { useAsync } from '../hooks'
import { formatTime, titleCase } from '../lib/format'
import type { Role } from '../types'

const AREAS: { tab: string; title: string; blurb: string; min: Role }[] = [
  { tab: 'overview', title: 'Overview', blurb: 'Headline numbers: precision, recall, loss prevented, open alerts.', min: 'viewer' },
  { tab: 'alerts', title: 'Alert queue', blurb: 'Investigate the riskiest transactions with SHAP explanations.', min: 'viewer' },
  { tab: 'rings', title: 'Linked networks', blurb: 'See accounts connected through shared devices and cards.', min: 'viewer' },
  { tab: 'analytics', title: 'Analytics', blurb: 'Risk over time, segment breakdown, PR curve, confusion matrix.', min: 'viewer' },
  { tab: 'simulator', title: 'Simulator', blurb: 'Fire realistic fraud scenarios through the live pipeline.', min: 'analyst' },
  { tab: 'threshold', title: 'Threshold & cost', blurb: 'Choose the operating point by what mistakes actually cost.', min: 'viewer' },
  { tab: 'batch', title: 'Batch CSV', blurb: 'Score a file of your own transactions.', min: 'analyst' },
  { tab: 'monitoring', title: 'Monitoring', blurb: 'Drift, analyst feedback, retraining and the audit log.', min: 'viewer' },
  { tab: 'users', title: 'User management', blurb: 'Roles, access and sessions. Administrators only.', min: 'admin' },
]

/** Where everyone lands after signing in. */
export function HeroPage() {
  const { user, role, adminSession, signOut } = useAuth()
  const summary = useAsync(api.summary, [])
  const s = summary.data
  const first = (user?.full_name ?? '').split(' ')[0]
  return (
    <main className="hero">
      <header className="hero__top">
        <div className="brand"><Logo href="#/hero" size={36} /><a className="brand__name" href="#/hero">Risk Manager</a></div>
        <div className="hero__who">
          <span>{user?.email}</span> <span className={`chip chip--role-${role}`}>{role}</span>
          <button className="btn btn--ghost" onClick={() => void signOut()}>Sign out</button>
        </div>
      </header>

      <section className="hero__banner">
        <p className="hero__eyebrow">{adminSession ? 'Administrator session' : 'Signed in securely'}</p>
        <h1 className="hero__title">Welcome back{first ? `, ${first}` : ''}.</h1>
        <p className="hero__lead">Catch fraud, abusive returns and chargebacks before they cost you, and know exactly why every transaction was flagged.</p>
        <div className="btn-row"><a className="btn btn--primary" href="#/app/overview">Open the dashboard →</a>{atLeast(role, 'analyst') && <a className="btn" href="#/app/simulator">Try the simulator</a>}</div>
      </section>

      {s && (
        <div className="stats">
          <Stat label="Open alerts" value={s.open_alerts.toLocaleString('en-IN')} tone="critical" />
          <Stat label="High + critical risk" value={s.high_risk_transactions.toLocaleString('en-IN')} tone="high" />
          <Stat label="Model recall" value={`${(s.recall * 100).toFixed(1)}%`} tone="low" />
          <Stat label="Live-scored" value={s.live_scored.toLocaleString('en-IN')} />
        </div>
      )}

      <section aria-label="Where to go">
        <h2 className="hero__h2">Your workspace</h2>
        <div className="areas">
          {AREAS.filter((a) => atLeast(role, a.min)).map((a) => (
            <a key={a.tab} className="area" href={`#/app/${a.tab}`}><h3>{a.title}</h3><p>{a.blurb}</p></a>
          ))}
        </div>
      </section>

      <Card title="Your session" subtitle="What protects this sign-in">
        <dl className="facts">
          <dt>Role</dt><dd>{titleCase(role ?? '')}: access is checked on the server for every request</dd>
          <dt>Last sign-in</dt><dd>{user?.last_login_at ? formatTime(user.last_login_at) : 'This is your first sign-in'}</dd>
          <dt>Verification</dt><dd>Password + emailed one-time code</dd>
          <dt>Session</dt><dd>HttpOnly cookie (not readable by page scripts), renewed automatically, revocable at any time</dd>
        </dl>
      </Card>
    </main>
  )
}
