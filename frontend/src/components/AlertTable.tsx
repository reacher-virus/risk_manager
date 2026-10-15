import type { Alert } from '../types'
import { formatINR, formatTime, pct } from '../lib/format'
import { Empty, SeverityChip, StatusChip } from './ui'
import { RiskPulse } from './RiskPulse'

export function AlertTable({ alerts, onOpen, compact = false }: { alerts: Alert[]; onOpen: (id: string) => void; compact?: boolean }) {
  if (!alerts.length) return <Empty>No alerts match these filters — the queue is clear.</Empty>
  return (
    <div className="table-wrap">
      <table className="table table--clickable table--stack">
        <thead>
          <tr><th /><th>Transaction</th><th>Customer</th><th className="num">Amount</th><th className="num">Risk</th><th>Severity</th>
            {!compact && <><th>Status</th><th>Source</th><th>Time</th></>}</tr>
        </thead>
        <tbody>
          {alerts.map((a) => (
            <tr key={a.transaction_id} tabIndex={0} onClick={() => onOpen(a.transaction_id)} onKeyDown={(e) => e.key === 'Enter' && onOpen(a.transaction_id)}>
              <td><RiskPulse score={a.risk_score} level={a.risk_level} seed={a.transaction_id} /></td>
              <td className="mono" data-label="Transaction">{a.transaction_id}</td>
              <td data-label="Customer">{a.customer_id}</td>
              <td className="num mono" data-label="Amount">{formatINR(a.amount)}</td>
              <td className="num mono" data-label="Risk">{pct(a.risk_score, 0)}</td>
              <td data-label="Severity"><SeverityChip level={a.risk_level} /></td>
              {!compact && <>
                <td data-label="Status"><StatusChip status={a.status} />{a.label && <span className={`chip chip--label chip--${a.label}`}>{a.label}</span>}</td>
                <td data-label="Source">{a.source}</td>
                <td data-label="Time">{formatTime(a.timestamp)}</td>
              </>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
