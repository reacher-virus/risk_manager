import type { ReactNode } from 'react'
import type { ApiError } from '../../api'
import type { RiskLevel, Status } from '../../types'

export function Card({ title, subtitle, actions, children, className = '' }: {
  title?: string; subtitle?: string; actions?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card__head">
          <div>
            {title && <h3 className="card__title">{title}</h3>}
            {subtitle && <p className="card__subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="card__actions">{actions}</div>}
        </header>
      )}
      <div className="card__body">{children}</div>
    </section>
  )
}

export function Stat({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: 'low' | 'medium' | 'high' | 'critical' }) {
  return (
    <div className={`stat ${tone ? `stat--${tone}` : ''}`}>
      <div className="stat__value mono">{value}</div>
      <div className="stat__label">{label}</div>
      {hint && <div className="stat__hint">{hint}</div>}
    </div>
  )
}

export function SeverityChip({ level }: { level: RiskLevel }) {
  return <span className={`chip chip--${level}`}>{level}</span>
}

export function StatusChip({ status }: { status: Status }) {
  return <span className={`chip chip--status chip--${status}`}>{status}</span>
}

export function Button({ variant = 'default', busy, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'primary' | 'danger' | 'ghost'; busy?: boolean }) {
  return <button {...p} disabled={p.disabled || busy} className={`btn btn--${variant} ${p.className ?? ''}`}>{busy ? 'Working…' : p.children}</button>
}

export const Loading = ({ label = 'Loading…' }: { label?: string }) => <div className="loading" role="status">{label}</div>

export function ErrorNote({ error, onRetry }: { error: ApiError | Error | null; onRetry?: () => void }) {
  if (!error) return null
  const status = (error as ApiError).status
  const hint = status === 0 ? 'Start the backend (see README) and retry.' : status === 401 ? 'Enter a valid API key in Settings.' : status === 403 ? 'Your role does not allow this action.' : ''
  return (
    <div className="error-note" role="alert">
      <strong>{error.message}</strong> {hint}
      {onRetry && <Button variant="ghost" onClick={onRetry}>Retry</Button>}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      {children}
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  )
}
