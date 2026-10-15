import { useEffect, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Button, Card, ErrorNote, Field, Loading, Stat } from '../components/ui'
import { useAsync, useDebounced } from '../hooks'
import { formatINR, formatINRShort, pct } from '../lib/format'
import { savings, savingsPct } from '../lib/cost'
import { useToast } from '@/components/toast-context'

export function ThresholdPage({ onChanged }: { onChanged: () => void }) {
  const cfg = useAsync(api.config, [])
  const [threshold, setThreshold] = useState(0.25)
  const [costFp, setCostFp] = useState(150)
  const [costFn, setCostFn] = useState(2500)
  const [split, setSplit] = useState<'test' | 'val'>('test')
  const [msg, setMsg] = useState<string | null>(null)
  const [saveErr, setSaveErr] = useState<Error | null>(null)
  const toast = useToast()

  useEffect(() => {
    if (cfg.data) { setThreshold(cfg.data.threshold); setCostFp(cfg.data.cost_fp); setCostFn(cfg.data.cost_fn) }
  }, [cfg.data])

  const dt = useDebounced(threshold), dfp = useDebounced(costFp), dfn = useDebounced(costFn)
  const a = useAsync(() => api.threshold({ threshold: dt, cost_fp: dfp, cost_fn: dfn, split }), [dt, dfp, dfn, split])

  const save = async (what: 'threshold' | 'costs' | 'reset') => {
    setMsg(null); setSaveErr(null)
    try {
      if (what === 'threshold') await api.setThreshold(threshold)
      if (what === 'costs') await api.setCosts(costFp, costFn)
      if (what === 'reset') { const c = await api.setThreshold(null); setThreshold(c.threshold) }
      setMsg(what === 'threshold' ? 'Deployed threshold updated.' : what === 'costs' ? 'Business costs saved as defaults.' : 'Threshold reset to the trained value.')
      toast.success(what === 'threshold' ? 'Deployed threshold updated.' : what === 'costs' ? 'Business costs saved.' : 'Threshold reset to the trained value.')
      cfg.reload(); onChanged()
    } catch (e) { setSaveErr(e as Error); toast.error((e as Error).message) }
  }

  const d = a.data
  return (
    <div className="stack">
      <Card title="Threshold & cost explorer" subtitle="Pick the operating point by what mistakes actually cost, not by accuracy.">
        <div className="form-grid">
          <Field label={`Decision threshold: ${threshold.toFixed(2)}`} hint="Flag anything scoring at or above this">
            <input type="range" min="0.01" max="0.98" step="0.01" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />
          </Field>
          <Field label="Cost of a false alarm (₹)" hint="Support cost + lost sale + churn"><input type="number" min="1" value={costFp} onChange={(e) => setCostFp(Number(e.target.value) || 1)} /></Field>
          <Field label="Cost of missed fraud (₹)" hint="Chargeback + goods + fees"><input type="number" min="1" value={costFn} onChange={(e) => setCostFn(Number(e.target.value) || 1)} /></Field>
          <Field label="Evaluate on" hint="Test = final held-out data; Validation = data used for tuning">
            <select value={split} onChange={(e) => setSplit(e.target.value as 'test' | 'val')}><option value="test">Held-out test</option><option value="val">Validation</option></select>
          </Field>
        </div>
        <div className="btn-row">
          {d && <Button onClick={() => setThreshold(d.optimal_threshold)}>Jump to cost-optimal ({d.optimal_threshold.toFixed(2)})</Button>}
          <Button variant="primary" onClick={() => save('threshold')}>Deploy this threshold</Button>
          <Button onClick={() => save('costs')}>Save costs as defaults</Button>
          <Button variant="ghost" onClick={() => save('reset')}>Reset to trained</Button>
        </div>
        {msg && <p className="callout">{msg}</p>}
        <ErrorNote error={saveErr} />
      </Card>
      <ErrorNote error={a.error} onRetry={a.reload} />
      {!d && !a.error && <Loading />}
      {d && (
        <>
          <div className="stats">
            <Stat label="Precision" value={pct(d.metrics.precision)} hint="of flagged, truly bad" />
            <Stat label="Recall" value={pct(d.metrics.recall)} hint="of all fraud, caught" />
            <Stat label="False alarms" value={String(d.metrics.false_positives)} hint={formatINR(d.cost.cost_fp_total)} tone="medium" />
            <Stat label="Missed fraud" value={String(d.metrics.false_negatives)} hint={formatINR(d.cost.cost_fn_total)} tone="critical" />
            <Stat label="Total expected loss" value={formatINRShort(d.cost.total_cost)} tone="high" />
            <Stat label="Saved vs. no model" value={formatINRShort(savings(d.cost_if_no_model, d.cost.total_cost))} hint={`${savingsPct(d.cost_if_no_model, d.cost.total_cost).toFixed(0)}% of ${formatINRShort(d.cost_if_no_model)}`} tone="low" />
          </div>
          <Card title="Expected loss by threshold" subtitle="The lowest point is the cheapest place to operate. Flat valleys mean you can raise precision almost for free.">
            <div className="chart" style={{ height: 300 }}>
              <ResponsiveContainer>
                <LineChart data={d.sweep} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                  <XAxis dataKey="threshold" type="number" domain={[0, 1]} tickFormatter={(v: number) => v.toFixed(1)} stroke="var(--text-dim)" />
                  <YAxis tickFormatter={(v: number) => formatINRShort(v)} stroke="var(--text-dim)" width={64} />
                  <Tooltip formatter={(v) => formatINR(Number(v))} labelFormatter={(l) => `Threshold ${Number(l).toFixed(2)}`} />
                  <Line type="monotone" dataKey="total_cost" name="Expected loss" stroke="var(--risk-high)" dot={false} strokeWidth={2} />
                  <ReferenceLine x={dt} stroke="var(--text-primary)" label={{ value: 'selected', fill: 'var(--text-dim)', fontSize: 11 }} />
                  <ReferenceLine x={d.optimal_threshold} stroke="var(--risk-low)" strokeDasharray="4 4" label={{ value: 'optimal', fill: 'var(--risk-low)', fontSize: 11 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
