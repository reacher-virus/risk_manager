import { api } from '../api'
import { AlertTable } from '../components/AlertTable'
import { Card, ErrorNote, Loading, Stat } from '../components/ui'
import { useAsync } from '../hooks'
import { formatINR, formatINRShort, pct } from '../lib/format'

export function OverviewPage({ onOpen, onNavigate, refreshKey }: { onOpen: (id: string) => void; onNavigate: (tab: string) => void; refreshKey: number }) {
  const summary = useAsync(api.summary, [refreshKey])
  const comparison = useAsync(api.comparison, [refreshKey])
  const metrics = useAsync(api.metrics, [refreshKey])
  const top = useAsync(() => api.alerts({ limit: 6, min_level: 'HIGH', status: 'NEW' }), [refreshKey])
  const s = summary.data

  if (summary.error) return <ErrorNote error={summary.error} onRetry={summary.reload} />
  if (!s) return <Loading />
  const c = comparison.data
  return (
    <div className="stack">
      <div className="stats">
        <Stat label="Transactions analysed (held-out test)" value={s.transactions_analyzed.toLocaleString('en-IN')} />
        <Stat label="Flagged suspicious" value={s.suspicious_transactions.toLocaleString('en-IN')} tone="medium" />
        <Stat label="High + critical" value={s.high_risk_transactions.toLocaleString('en-IN')} tone="high" />
        <Stat label="Estimated loss prevented" value={formatINRShort(s.estimated_loss_prevented)} tone="low" />
        <Stat label="Open alerts" value={s.open_alerts.toLocaleString('en-IN')} hint={`${s.live_scored} live-scored`} tone="critical" />
      </div>
      <div className="stats stats--secondary">
        <Stat label="Precision" value={pct(s.precision)} />
        <Stat label="Recall" value={pct(s.recall)} />
        <Stat label="PR-AUC" value={s.pr_auc.toFixed(3)} />
        <Stat label="False-positive rate" value={pct(s.false_positive_rate, 2)} />
        <Stat label="Decision threshold" value={s.threshold.toFixed(2)} />
      </div>
      <div className="layout-two">
        <Card title="Needs attention" subtitle="Highest-risk transactions nobody has reviewed yet"
          actions={<button className="btn btn--ghost" onClick={() => onNavigate('alerts')}>Open full queue →</button>}>
          {top.error ? <ErrorNote error={top.error} /> : top.data ? <AlertTable alerts={top.data.items} onOpen={onOpen} compact /> : <Loading />}
        </Card>
        <Card title="Rules vs. learned model" subtitle="Held-out test set, current business costs">
          {c ? (
            <table className="table table--tight">
              <thead><tr><th /><th className="num">Rules</th><th className="num">ML</th></tr></thead>
              <tbody>
                <tr><td>Precision</td><td className="num mono">{pct(c.rule_based.precision, 0)}</td><td className="num mono">{pct(c.ml_model.precision, 0)}</td></tr>
                <tr><td>Recall</td><td className="num mono">{pct(c.rule_based.recall, 0)}</td><td className="num mono">{pct(c.ml_model.recall, 0)}</td></tr>
                <tr><td>PR-AUC</td><td className="num mono">{c.rule_based.pr_auc.toFixed(2)}</td><td className="num mono">{c.ml_model.pr_auc.toFixed(2)}</td></tr>
                <tr><td>False-positive cost</td><td className="num mono">{formatINR(c.rule_based.fp_cost)}</td><td className="num mono">{formatINR(c.ml_model.fp_cost)}</td></tr>
                <tr><td>Missed-fraud cost</td><td className="num mono">{formatINR(c.rule_based.fn_cost)}</td><td className="num mono">{formatINR(c.ml_model.fn_cost)}</td></tr>
                <tr className="table__total"><td>Total expected loss</td><td className="num mono">{formatINR(c.rule_based.fp_cost + c.rule_based.fn_cost)}</td><td className="num mono">{formatINR(c.ml_model.fp_cost + c.ml_model.fn_cost)}</td></tr>
              </tbody>
            </table>
          ) : <Loading />}
          {c && <p className="callout">Expected loss is <strong>{c.cost_reduction_pct}% lower</strong> than the rule baseline.</p>}
          {metrics.data && <p className="note">{metrics.data.dataset_note}</p>}
        </Card>
      </div>
    </div>
  )
}
