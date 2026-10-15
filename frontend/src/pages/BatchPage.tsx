import { useRef, useState } from 'react'
import { api } from '../api'
import { AlertTable } from '../components/AlertTable'
import { Button, Card, ErrorNote, Stat } from '../components/ui'
import { formatINR, pct } from '../lib/format'
import type { BatchResult } from '../types'
import { useToast } from '@/components/toast-context'

const SAMPLE = 'transaction_id,customer_id,amount,device_id,payment_id,timestamp,ip_region,account_age_days,is_fraud\nT1,U1,1200,D1,P1,2026-09-01 10:00:00,Chennai,300,0\nT2,U2,5200,D9,P2,2026-09-01 10:01:00,Delhi,0,1\nT3,U3,5100,D9,P3,2026-09-01 10:02:00,Delhi,0,1\n'

export function BatchPage({ onOpen }: { onOpen: (id: string) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<BatchResult | null>(null)
  const [err, setErr] = useState<Error | null>(null)
  const toast = useToast()

  const run = async () => {
    if (!file) return
    setBusy(true); setErr(null); setRes(null)
    try { const r = await api.batch(file); setRes(r); toast.success(`Scored ${r.rows.toLocaleString('en-IN')} rows; ${r.flagged.toLocaleString('en-IN')} flagged.`) } catch (e) { setErr(e as Error); toast.error((e as Error).message) } finally { setBusy(false) }
  }
  const sample = () => {
    const url = URL.createObjectURL(new Blob([SAMPLE], { type: 'text/csv' }))
    const a = Object.assign(document.createElement('a'), { href: url, download: 'sample_transactions.csv' }); a.click(); URL.revokeObjectURL(url)
  }
  return (
    <div className="stack">
      <Card title="Score a CSV" subtitle="Upload your own transactions. Scoring is isolated from live state and nothing is stored as an alert.">
        <p>Required columns: <code>customer_id, amount, device_id</code>. Optional: <code>timestamp, payment_id, account_age_days, ip_region, merchant_category, payment_method, transaction_id, is_fraud</code>. Include <code>is_fraud</code> to get precision/recall/cost on your own data.</p>
        <div className="btn-row">
          <input ref={input} type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <Button variant="primary" busy={busy} disabled={!file} onClick={run}>Score file</Button>
          <Button variant="ghost" onClick={sample}>Download sample CSV</Button>
        </div>
        <ErrorNote error={err} />
      </Card>
      {res && (
        <>
          {res.warnings.map((w) => <p key={w} className="note">⚠ {w}</p>)}
          <div className="stats">
            <Stat label="Rows scored" value={res.rows.toLocaleString('en-IN')} />
            <Stat label="Flagged" value={res.flagged.toLocaleString('en-IN')} hint={`≥ ${res.threshold.toFixed(2)}`} tone="high" />
            {(['MEDIUM', 'HIGH', 'CRITICAL'] as const).map((l) => <Stat key={l} label={l.toLowerCase()} value={String(res.by_level[l])} />)}
            {res.metrics && <><Stat label="Precision" value={pct(res.metrics.precision)} /><Stat label="Recall" value={pct(res.metrics.recall)} /></>}
            {res.cost && <Stat label="Expected loss" value={formatINR(res.cost.total_cost)} tone="critical" />}
          </div>
          <Card title="Top alerts in this file" actions={<Button onClick={() => api.downloadBatch(res.result_id)}>Download scored CSV</Button>}>
            <AlertTable alerts={res.top_alerts} onOpen={onOpen} compact />
            <p className="note">Batch rows are not stored, so the detail drawer is only available for transactions in the live queue.</p>
          </Card>
        </>
      )}
    </div>
  )
}
