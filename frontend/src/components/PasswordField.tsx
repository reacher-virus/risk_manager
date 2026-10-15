import { useState } from 'react'
import { checkPassword } from '../lib/password'

export function PasswordField({ label, value, onChange, autoComplete, showRules = false, email = '' }: {
  label: string; value: string; onChange: (v: string) => void; autoComplete: 'new-password' | 'current-password'; showRules?: boolean; email?: string
}) {
  const [show, setShow] = useState(false)
  return (
    <div className="field">
      <label className="field__label" htmlFor={`pw-${label}`}>{label}</label>
      <div className="password">
        <input id={`pw-${label}`} type={show ? 'text' : 'password'} value={value} maxLength={128} required autoComplete={autoComplete} onChange={(e) => onChange(e.target.value)} />
        <button type="button" className="btn btn--ghost" onClick={() => setShow((s) => !s)} aria-pressed={show}>{show ? 'Hide' : 'Show'}</button>
      </div>
      {showRules && value.length > 0 && (
        <ul className="rules" aria-label="Password requirements">
          {checkPassword(value, email).map((r) => <li key={r.label} className={r.ok ? 'rule rule--ok' : 'rule'}>{r.ok ? '✓' : '○'} {r.label}</li>)}
        </ul>
      )}
    </div>
  )
}
