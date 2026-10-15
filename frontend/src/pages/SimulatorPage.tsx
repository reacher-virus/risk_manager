import { useState } from 'react'
import { api } from '../api'
import { RiskPulse } from '../components/RiskPulse'
import { Button, Card, ErrorNote, Field, SeverityChip } from '../components/ui'
import { formatINR, pct, titleCase } from '../lib/format'
import type { PredictResult, Scenario, SimResult } from '../types'
import { useToast } from '@/components/toast-context'

const SCENARIOS: { id: Scenario; name: string; blurb: string; n: number }[] = [
  { id: 'normal', name: 'Normal shoppers', blurb: 'Regular customers buying their usual amounts. Should all be allowed.', n: 5 },
  { id: 'velocity_burst', name: 'Card testing', blurb: 'A brand-new account probes a card with rapid small purchases, then one large one.', n: 8 },
  { id: 'fraud_ring', name: 'Fraud ring', blurb: 'Many new accounts on one device spend similar amounts within minutes.', n: 8 },
  { id: 'multi_device_ring', name: 'Multi-device ring', blurb: 'Accounts rotate across several devices and cards to hide the link; only the network view exposes it.', n: 10 },
  { id: 'account_takeover', name: 'Account takeover', blurb: 'A real customer’s saved card used from a new device and region.', n: 4 },
]

export function SimulatorPage({ onOpen, onChanged }: { onOpen: (id: string) => void; onChanged: () => void }) {
  const [busy, setBusy] = useState<string | null>(null)
  const toast = useToast()
  const [err, setErr] = useState<Error | null>(null)
  const [rows, setRows] = useState<(SimResult | (PredictResult & { customer_id: string; amount: number; device_id: string }))[]>([])
  const [label, setLabel] = useState('')
  const [form, setForm] = useState({ customer_id: 'DEMO-CUST-1', amount: '4500', device_id: 'DEMO-DEV-1', payment_id: 'DEMO-PAY-1', account_age_days: '1', ip_region: 'Delhi', merchant_category: 'Electronics' })

  const run = async (s: (typeof SCENARIOS)[number]) => {
    setBusy(s.id); setErr(null)
    try { const r = await api.simulate(s.id, s.n); setRows(r.results); setLabel(s.name); onChanged(); toast.success(`${s.name}: scored ${r.results.length} transaction${r.results.length === 1 ? '' : 's'}.`) }
    catch (e) { setErr(e as Error); toast.error((e as Error).message) } finally { setBusy(null) }
  }
  const submitOne = async () => {
    setBusy('manual'); setErr(null)
    try {
      const r = await api.predict({ ...form, amount: Number(form.amount), account_age_days: Number(form.account_age_days) })
      setRows([{ ...r, customer_id: form.customer_id, amount: Number(form.amount), device_id: form.device_id }]); setLabel('Manual transaction'); onChanged(); toast.success('Transaction scored.')
    } catch (e) { setErr(e as Error); toast.error((e as Error).message) } finally { setBusy(null) }
  }
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value })

  return (
    <div className="stack">
      <Card title="Scenario simulator" subtitle="Fire realistic traffic through the live scoring pipeline. Results are stored and appear in the alert queue.">
        <div className="scenarios">
          {SCENARIOS.map((s) => (
            <div className="scenario" key={s.id}>
              <h4>{s.name}</h4><p>{s.blurb}</p>
              <Button variant="primary" busy={busy === s.id} disabled={!!busy} onClick={() => run(s)}>Run ({s.n} tx)</Button>
            </div>
          ))}
        </div>
      </Card>
      <Card title="Score a single transaction" subtitle="Calls POST /predict directly">
        <div className="form-grid">
          <Field label="Customer ID"><input value={form.customer_id} onChange={set('customer_id')} /></Field>
          <Field label="Amount (₹)"><input type="number" min="1" value={form.amount} onChange={set('amount')} /></Field>
          <Field label="Device ID"><input value={form.device_id} onChange={set('device_id')} /></Field>
          <Field label="Payment ID"><input value={form.payment_id} onChange={set('payment_id')} /></Field>
          <Field label="Account age (days)"><input type="number" min="0" value={form.account_age_days} onChange={set('account_age_days')} /></Field>
          <Field label="Region"><input value={form.ip_region} onChange={set('ip_region')} /></Field>
          <Field label="Category"><input value={form.merchant_category} onChange={set('merchant_category')} /></Field>
        </div>
        <Button variant="primary" busy={busy === 'manual'} disabled={!!busy} onClick={submitOne}>Score it</Button>
      </Card>
      <ErrorNote error={err} />
      {rows.length > 0 && (
        <Card title={`Results: ${label}`} subtitle="Watch how the score escalates as the pattern builds">
          <div className="table-wrap"><table className="table table--clickable table--stack">
            <thead><tr><th>#</th><th /><th>Customer</th><th className="num">Amount</th><th className="num">Risk</th><th>Severity</th><th>Decision</th><th>Top reason</th></tr></thead>
            <tbody>{rows.map((r, i) => (
              <tr key={r.transaction_id} tabIndex={0} onClick={() => onOpen(r.transaction_id)} onKeyDown={(e) => e.key === 'Enter' && onOpen(r.transaction_id)}>
                <td data-label="#">{i + 1}</td><td><RiskPulse score={r.risk_score} level={r.risk_level} seed={r.transaction_id} /></td>
                <td data-label="Customer">{r.customer_id}</td><td className="num mono" data-label="Amount">{formatINR(r.amount)}</td><td className="num mono" data-label="Risk">{pct(r.risk_score, 0)}</td>
                <td data-label="Severity"><SeverityChip level={r.risk_level} /></td><td data-label="Decision">{titleCase(r.decision)}</td><td data-label="Top reason">{r.reasons[0]}</td>
              </tr>))}</tbody>
          </table></div>
        </Card>
      )}
    </div>
  )
}
