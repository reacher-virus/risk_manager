import { useEffect, useState } from 'react'
import { api } from '../api'
import { Button, Card, ErrorNote, Loading, Stat } from '../components/ui'
import { useAsync } from '../hooks'
import { formatTime, pct } from '../lib/format'
import { useToast } from '@/components/toast-context'

export function MonitoringPage({ onChanged, refreshKey }: { onChanged: () => void; refreshKey: number }) {
  const m = useAsync(api.monitoring, [refreshKey])
  const audit = useAsync(() => api.audit(60), [refreshKey])
  const [err, setErr] = useState<Error | null>(null)
  const [polling, setPolling] = useState(false)
  const toast = useToast()
  const state = m.data?.retrain.state

  const start = async () => {
    setErr(null)
    try { await api.retrain(); setPolling(true); m.reload(); toast.info('Retraining started. This can take a minute or two.') } catch (e) { setErr(e as Error); toast.error((e as Error).message) }
  }
  useEffect(() => {
    if (!polling) return
    const t = setInterval(async () => {
      try {
        const s = await api.retrainStatus()
        if (s.state !== 'running') { setPolling(false); m.reload(); audit.reload(); onChanged(); if (s.state === 'failed') toast.error(s.message ?? 'Retraining failed.'); else toast.success(s.message ?? 'Retraining finished. The new model is live.') }
      } catch { setPolling(false) }
    }, 2500)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [polling])

  if (m.error) return <ErrorNote error={m.error} onRetry={m.reload} />
  if (!m.data) return <Loading />
  const d = m.data
  return (
    <div className="stack">
      <div className="stats">
        <Stat label="Score drift (PSI)" value={d.score_psi.toFixed(3)} hint={d.score_status} tone={d.score_status === 'stable' ? 'low' : d.score_status === 'watch' ? 'medium' : 'critical'} />
        <Stat label="Retrain recommended" value={d.retrain_recommended ? 'Yes' : 'No'} tone={d.retrain_recommended ? 'critical' : 'low'} />
        <Stat label="Analyst-labelled cases" value={String(d.feedback.labelled_cases)} hint={`${d.feedback.confirmed_fraud} fraud · ${d.feedback.false_positives} legit`} />
        <Stat label="Analyst precision" value={d.feedback.analyst_precision === null ? '—' : pct(d.feedback.analyst_precision, 0)} hint="of reviewed alerts that were real" />
      </div>
      <div className="layout-two">
        <Card title="Feature drift" subtitle={d.window}>
          <div className="table-wrap"><table className="table table--tight">
            <thead><tr><th>Feature</th><th className="num">PSI</th><th>Status</th></tr></thead>
            <tbody>{d.features.map((f) => (
              <tr key={f.feature}><td className="mono">{f.feature}</td><td className="num mono">{f.psi.toFixed(3)}</td><td><span className={`chip chip--drift-${f.status}`}>{f.status}</span></td></tr>))}</tbody>
          </table></div>
          <p className="note">PSI &lt; 0.10 stable · 0.10–0.25 watch · &gt; 0.25 retrain.</p>
        </Card>
        <Card title="Model lifecycle" subtitle={`${d.model.name} · trained ${d.model.trained_at ? formatTime(d.model.trained_at) : 'n/a'}`}>
          <p>Analyst feedback rows in current model: <strong>{d.model.analyst_rows_in_training}</strong></p>
          <p className="note">Retraining re-fits on the original training window plus every case an analyst labelled, re-calibrates, re-selects the threshold on validation data and hot-swaps the model. The test set is never touched.</p>
          <Button variant="primary" onClick={start} busy={state === 'running' || polling}>Retrain with analyst feedback</Button>
          {d.retrain.message && <p className={d.retrain.state === 'failed' ? 'error-note' : 'callout'}>{d.retrain.state}: {d.retrain.message}</p>}
          <ErrorNote error={err} />
        </Card>
      </div>
      <Card title="Audit log" subtitle="Every score, review, config change and failed login (admin only)">
        <ErrorNote error={audit.error} />
        {audit.data && <div className="table-wrap"><table className="table table--tight table--stack">
          <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Transaction</th><th>Detail</th></tr></thead>
          <tbody>{audit.data.map((r) => (
            <tr key={r.id}><td data-label="Time">{formatTime(r.ts)}</td><td data-label="Actor">{r.actor}</td><td className="mono" data-label="Action">{r.action}</td><td className="mono" data-label="Transaction">{r.transaction_id ?? ''}</td><td className="mono small" data-label="Detail">{r.detail ? JSON.stringify(r.detail) : ''}</td></tr>))}</tbody>
        </table></div>}
      </Card>
    </div>
  )
}
