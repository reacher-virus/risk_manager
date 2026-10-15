import { useEffect, useState } from 'react'
import { Button, ErrorNote, Field } from './ui'

/** Second step: the 6-digit code that was emailed. Includes a resend cooldown that mirrors the server's. */
export function OtpStep({ message, busy, error, onSubmit, onResend, onBack, cooldown = 60 }: {
  message: string; busy: boolean; error: Error | null; onSubmit: (code: string) => void; onResend: () => Promise<void>; onBack: () => void; cooldown?: number
}) {
  const [code, setCode] = useState('')
  const [wait, setWait] = useState(cooldown)
  const [note, setNote] = useState<string | null>(null)
  useEffect(() => {
    if (wait <= 0) return
    const t = setTimeout(() => setWait((w) => w - 1), 1000)
    return () => clearTimeout(t)
  }, [wait])

  const resend = async () => {
    setNote(null)
    try { await onResend(); setWait(cooldown); setNote('A new code is on its way.') } catch (e) { setNote((e as Error).message) }
  }
  return (
    <form className="auth-form" onSubmit={(e) => { e.preventDefault(); onSubmit(code) }}>
      <p className="callout">{message}</p>
      <Field label="6-digit verification code" hint="Check your inbox (and spam). The code expires in 10 minutes and works once.">
        <input className="otp" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" autoFocus required value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} aria-label="6-digit verification code" />
      </Field>
      <ErrorNote error={error} />
      <div className="btn-row">
        <Button type="submit" variant="primary" busy={busy} disabled={code.length !== 6}>Verify</Button>
        <Button type="button" variant="ghost" disabled={wait > 0} onClick={resend}>{wait > 0 ? `Resend code in ${wait}s` : 'Resend code'}</Button>
        <Button type="button" variant="ghost" onClick={onBack}>← Back</Button>
      </div>
      {note && <p className="note" role="status">{note}</p>}
    </form>
  )
}
