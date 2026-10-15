import type { ReactNode } from 'react'
import { SiteFooter } from '@/components/SiteFooter'
import { SiteHeader } from '@/components/SiteHeader'
import { SITE, mailto } from '@/lib/site'

function Doc({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="site">
      <SiteHeader />
      <main className="legal">
        <h1>{title}</h1>
        <p className="note">Last updated: October 2026. This describes what the software in this project actually does. It is a project template, not legal advice: have it reviewed before you rely on it commercially.</p>
        {children}
        <p>Questions? Write to <a href={mailto(title)}>{SITE.email}</a>.</p>
      </main>
      <SiteFooter />
    </div>
  )
}

export function PrivacyPage() {
  return (
    <Doc title="Privacy Policy">
      <h2>What we store</h2>
      <ul>
        <li><strong>Account:</strong> your name, email address and a one-way Argon2id hash of your password (never the password itself), your role, and sign-in times.</li>
        <li><strong>Security records:</strong> the IP address and browser type of each sign-in, failed-attempt counters, and an audit log of actions such as reviewing an alert or changing a setting.</li>
        <li><strong>Work you do in the app:</strong> transactions you score, review decisions and notes you write.</li>
      </ul>
      <h2>Cookies</h2>
      <p>Only strictly necessary cookies: a session cookie and a rotating refresh cookie (both HttpOnly, so page scripts cannot read them), a CSRF-protection token, and a cookie that remembers you dismissed the cookie notice. There is no advertising, tracking or analytics cookie.</p>
      <h2>Email</h2>
      <p>We email you only to verify your address, send sign-in codes, deliver password-reset links and confirm a password change. Plain-text messages, nothing promotional.</p>
      <h2>Sharing</h2>
      <p>We do not sell or share your data. If an administrator configures an alert webhook, details of CRITICAL alerts are sent to the address they chose.</p>
      <h2>Your choices</h2>
      <p>You can sign out of every device at any time from Settings. To see, correct or delete your data, email the address below and we will act on it.</p>
    </Doc>
  )
}

export function TermsPage() {
  return (
    <Doc title="Terms of Service">
      <h2>Using the service</h2>
      <ul>
        <li>Risk Manager is a <strong>defense-only</strong> tool. Do not use it to commit fraud, evade detection, probe other people's systems or collect data you are not entitled to.</li>
        <li>Keep your credentials and one-time codes private. You are responsible for activity under your account.</li>
        <li>Do not attempt to disrupt the service or bypass its security controls.</li>
      </ul>
      <h2>No guarantees</h2>
      <ul>
        <li>Scores and recommendations support human decisions; they are not guarantees. Metrics shown in the app and on this site come from <strong>synthetic data</strong> and do not predict results on your transactions.</li>
        <li>The service is provided "as is", without warranties of any kind, to the extent the law allows.</li>
      </ul>
      <h2>Accounts</h2>
      <p>Accounts may be suspended or removed if these terms are broken or to protect other users. We may change these terms; continued use means you accept the changes.</p>
    </Doc>
  )
}
