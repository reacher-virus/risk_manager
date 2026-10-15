import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAsync } from '../hooks'
import { formatINR, formatTime, pct, titleCase } from '../lib/format'
import { RiskPulse } from './RiskPulse'
import { Button, ErrorNote, Loading, SeverityChip, StatusChip } from './ui'
import { useToast } from '@/components/toast-context'

export function AlertDetail({ txId, onClose, onChanged, onOpenRing }: {
  txId: string; onClose: () => void; onChanged: () => void; onOpenRing: (ringId: string) => void
}) {
  const d = useAsync(() => api.alert(txId), [txId])
  const toast = useToast()
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<Error | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const submit = async (data: { action?: string; label?: string }) => {
    setBusy(true); setErr(null)
    try { await api.review(txId, { ...data, note: note || undefined }); setNote(''); d.reload(); onChanged(); toast.success(data.action ? `Decision saved: ${data.action.toLowerCase()}` : `Feedback saved: ${data.label === 'FRAUD' ? 'confirmed fraud' : 'marked legitimate'}`) }
    catch (e) { setErr(e as Error); toast.error((e as Error).message) } finally { setBusy(false) }
  }

  const a = d.data
  const maxC = a ? Math.max(...a.contributions.map((c) => Math.abs(c.contribution)), 1e-9) : 1
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-label={`Alert ${txId}`} onClick={(e) => e.stopPropagation()}>
        <header className="drawer__head">
          <div>
            <h2 className="mono">{txId}</h2>
            {a && <p>{a.customer_id} · {formatINR(a.amount)} · {formatTime(a.timestamp)} · <em>{a.source}</em></p>}
          </div>
          <Button variant="ghost" onClick={onClose} aria-label="Close">✕</Button>
        </header>
        <ErrorNote error={d.error} onRetry={d.reload} />
        {!a && !d.error && <Loading />}
        {a && (
          <div className="drawer__body">
            <section className="detail-score">
              <RiskPulse score={a.risk_score} level={a.risk_level} seed={a.transaction_id} bars={13} />
              <div className="detail-score__num mono">{pct(a.risk_score, 1)}</div>
              <SeverityChip level={a.risk_level} /><StatusChip status={a.status} />
              {a.label && <span className={`chip chip--label chip--${a.label}`}>{a.label}</span>}
              <div className="detail-score__decision">Recommended: <strong>{titleCase(a.decision)}</strong></div>
              <div className="note">Anomaly layer: {pct(a.anomaly_score, 0)} more unusual than normal traffic</div>
            </section>

            <section>
              <h4>Why it was flagged</h4>
              <ul className="reasons">{a.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </section>

            <section>
              <h4>What pushed the score (SHAP)</h4>
              <div className="bars">
                {a.contributions.map((c) => (
                  <div className="bar-row" key={c.feature} title={`${c.feature} = ${c.value}`}>
                    <span className="bar-row__label">{c.label} <small className="mono">{Number.isInteger(c.value) ? c.value : c.value.toFixed(2)}</small></span>
                    <span className="bar-row__track">
                      <span className={`bar-row__fill ${c.contribution >= 0 ? 'bar-row__fill--up' : 'bar-row__fill--down'}`}
                        style={{ width: `${(Math.abs(c.contribution) / maxC) * 100}%` }} />
                    </span>
                    <span className="bar-row__val mono">{c.contribution >= 0 ? '+' : ''}{c.contribution.toFixed(3)}</span>
                  </div>
                ))}
              </div>
              <p className="note">Red raises risk, green lowers it. Values are the model's own attributions, not hand-written rules.</p>
            </section>

            <section>
              <h4>Details</h4>
              <dl className="facts">
                <dt>Device</dt><dd className="mono">{a.device_id}</dd>
                <dt>Payment instrument</dt><dd className="mono">{a.payment_id}</dd>
                <dt>Region</dt><dd>{a.ip_region}</dd>
                <dt>Category</dt><dd>{a.merchant_category ?? '—'}</dd>
                <dt>Account age</dt><dd>{a.account_age_days} days</dd>
                {a.ring_id && <><dt>Network</dt><dd><Button variant="ghost" onClick={() => { onClose(); onOpenRing(a.ring_id!) }}>View linked network {a.ring_id} →</Button></dd></>}
                {a.ground_truth && <><dt>Synthetic label</dt><dd>{a.ground_truth.is_fraud ? 'fraud' : 'legit'} ({a.ground_truth.fraud_pattern}) <small>— simulation ground truth, not available in production</small></dd></>}
              </dl>
            </section>

            <section>
              <h4>Customer timeline</h4>
              <div className="table-wrap"><table className="table table--tight">
                <thead><tr><th>Time</th><th className="num">Amount</th><th className="num">Risk</th><th>Device</th><th>Region</th></tr></thead>
                <tbody>{a.customer_timeline.map((t) => (
                  <tr key={t.transaction_id} className={t.transaction_id === a.transaction_id ? 'row--current' : ''}>
                    <td>{formatTime(t.timestamp)}</td><td className="num mono">{formatINR(t.amount)}</td>
                    <td className="num mono">{pct(t.risk_score, 0)}</td><td className="mono">{t.device_id}</td><td>{t.ip_region}</td>
                  </tr>))}</tbody>
              </table></div>
            </section>

            <section>
              <h4>Accounts sharing a device or card ({a.related_accounts.length})</h4>
              {a.related_accounts.length === 0 ? <p className="note">None — this looks like an isolated customer.</p> : (
                <ul className="related">{a.related_accounts.map((r) => (
                  <li key={r.customer_id}><span className="mono">{r.customer_id}</span> · via {r.shared_via.join(' + ')} · {r.transactions} tx · max risk {pct(r.max_risk, 0)}</li>))}</ul>
              )}
            </section>

            <section className="review">
              <h4>Your decision</h4>
              <textarea placeholder="Optional note for the audit trail…" value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} />
              <div className="review__row">
                <Button variant="primary" busy={busy} onClick={() => submit({ action: 'APPROVE' })}>Approve</Button>
                <Button busy={busy} onClick={() => submit({ action: 'HOLD' })}>Hold for verification</Button>
                <Button variant="danger" busy={busy} onClick={() => submit({ action: 'ESCALATE' })}>Escalate</Button>
              </div>
              <div className="review__row">
                <span className="note">Feedback for retraining:</span>
                <Button busy={busy} onClick={() => submit({ label: 'FRAUD' })}>Confirm fraud</Button>
                <Button busy={busy} onClick={() => submit({ label: 'LEGIT' })}>Mark legitimate</Button>
              </div>
              <ErrorNote error={err} />
              {a.review_history.length > 0 && (
                <ul className="history">{a.review_history.map((h, i) => (
                  <li key={i}><strong>{h.action ?? ''}{h.action && h.label ? ' + ' : ''}{h.label ?? ''}</strong> by {h.actor} · {formatTime(h.at)}{h.note && <em> — {h.note}</em>}</li>))}</ul>
              )}
            </section>
          </div>
        )}
      </aside>
    </div>
  )
}
