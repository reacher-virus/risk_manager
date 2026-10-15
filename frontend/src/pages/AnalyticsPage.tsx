import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Card, ErrorNote, Loading } from '../components/ui'
import { useAsync } from '../hooks'
import { pct, titleCase } from '../lib/format'

const AX = { stroke: 'var(--text-dim)', fontSize: 11 }

export function AnalyticsPage({ refreshKey }: { refreshKey: number }) {
  const [bucket, setBucket] = useState('day')
  const [by, setBy] = useState('ip_region')
  const [cmThreshold, setCmThreshold] = useState<number | undefined>(undefined)
  const ts = useAsync(() => api.timeseries(bucket), [bucket, refreshKey])
  const bd = useAsync(() => api.breakdown(by), [by, refreshKey])
  const pr = useAsync(() => api.prCurve('test'), [refreshKey])
  const cm = useAsync(() => api.confusion(cmThreshold), [cmThreshold, refreshKey])
  const c = cm.data

  return (
    <div className="stack">
      <Card title="Risk over time" subtitle="Volume vs. flagged transactions (held-out period + live traffic)"
        actions={<select value={bucket} onChange={(e) => setBucket(e.target.value)}><option value="day">Daily</option><option value="hour">Hourly</option></select>}>
        <ErrorNote error={ts.error} onRetry={ts.reload} />
        {!ts.data && !ts.error ? <Loading /> : (
          <div className="chart" style={{ height: 280 }}><ResponsiveContainer>
            <LineChart data={ts.data ?? []} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
              <XAxis dataKey="bucket" tickFormatter={(v: string) => v.slice(5, bucket === 'day' ? 10 : 13)} {...AX} />
              <YAxis yAxisId="l" {...AX} /><YAxis yAxisId="r" orientation="right" domain={[0, 1]} tickFormatter={(v: number) => pct(v, 0)} {...AX} />
              <Tooltip /><Legend />
              <Line yAxisId="l" dataKey="transactions" name="Transactions" stroke="var(--text-dim)" dot={false} />
              <Line yAxisId="l" dataKey="flagged" name="Flagged" stroke="var(--risk-high)" dot={false} strokeWidth={2} />
              <Line yAxisId="r" dataKey="mean_risk" name="Mean risk" stroke="var(--risk-critical)" dot={false} strokeDasharray="4 3" />
            </LineChart></ResponsiveContainer></div>)}
      </Card>

      <div className="layout-two">
        <Card title="Where risk concentrates" subtitle="Flag rate and (synthetic) fraud rate by segment"
          actions={<select value={by} onChange={(e) => setBy(e.target.value)}>
            <option value="ip_region">Region</option><option value="merchant_category">Category</option><option value="payment_method">Payment method</option></select>}>
          <ErrorNote error={bd.error} />
          {!bd.data && !bd.error ? <Loading /> : (
            <div className="chart" style={{ height: 300 }}><ResponsiveContainer>
              <BarChart data={bd.data ?? []} layout="vertical" margin={{ left: 24, right: 12 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                <XAxis type="number" tickFormatter={(v: number) => pct(v, 0)} {...AX} /><YAxis type="category" dataKey="name" width={96} {...AX} />
                <Tooltip formatter={(v) => pct(Number(v))} /><Legend />
                <Bar dataKey="flag_rate" name="Flag rate" fill="var(--risk-high)" />
                <Bar dataKey="synthetic_fraud_rate" name="Fraud rate (synthetic)" fill="var(--risk-critical)" />
              </BarChart></ResponsiveContainer></div>)}
        </Card>

        <Card title="Precision-recall curve" subtitle={pr.data ? `Average precision ${pr.data.average_precision.toFixed(3)} vs. ${pct(pr.data.base_rate)} base rate` : ''}>
          <ErrorNote error={pr.error} />
          {!pr.data && !pr.error ? <Loading /> : (
            <div className="chart" style={{ height: 300 }}><ResponsiveContainer>
              <LineChart data={pr.data?.points ?? []} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                <XAxis dataKey="recall" type="number" domain={[0, 1]} tickFormatter={(v: number) => v.toFixed(1)} label={{ value: 'Recall', position: 'insideBottom', offset: -2, fill: 'var(--text-dim)', fontSize: 11 }} {...AX} />
                <YAxis domain={[0, 1]} tickFormatter={(v: number) => v.toFixed(1)} {...AX} />
                <Tooltip formatter={(v) => Number(v).toFixed(3)} />
                <ReferenceLine y={pr.data?.base_rate} stroke="var(--text-faint)" strokeDasharray="4 4" />
                <Line dataKey="precision" name="Precision" stroke="var(--risk-high)" dot={false} strokeWidth={2} />
              </LineChart></ResponsiveContainer></div>)}
        </Card>
      </div>

      <Card title="Confusion matrix" subtitle="Held-out test set at the chosen threshold"
        actions={<label className="inline">Threshold <input type="number" min={0.01} max={0.99} step={0.01} placeholder="deployed" value={cmThreshold ?? ''} onChange={(e) => setCmThreshold(e.target.value ? Number(e.target.value) : undefined)} /></label>}>
        <ErrorNote error={cm.error} />
        {c ? (
          <div className="confusion">
            <div className="confusion__corner" /><div className="confusion__head">Flagged</div><div className="confusion__head">Not flagged</div>
            <div className="confusion__head">Actually fraud</div>
            <div className="confusion__cell confusion__cell--good"><strong className="mono">{c.true_positives}</strong>{titleCase('caught')}</div>
            <div className="confusion__cell confusion__cell--bad"><strong className="mono">{c.false_negatives}</strong>{titleCase('missed')}</div>
            <div className="confusion__head">Actually legit</div>
            <div className="confusion__cell confusion__cell--warn"><strong className="mono">{c.false_positives}</strong>{titleCase('false alarms')}</div>
            <div className="confusion__cell"><strong className="mono">{c.true_negatives}</strong>{titleCase('correctly allowed')}</div>
          </div>) : !cm.error && <Loading />}
        {c && <p className="note">Threshold {c.threshold.toFixed(2)} · precision {pct(c.precision)} · recall {pct(c.recall)} · false-positive rate {pct(c.false_positive_rate, 2)}</p>}
      </Card>
    </div>
  )
}
