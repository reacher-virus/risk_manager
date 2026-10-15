import { useEffect, useState } from 'react'
import { api } from '../api'
import { RingGraph } from '../components/RingGraph'
import { Card, Empty, ErrorNote, Loading } from '../components/ui'
import { useAsync } from '../hooks'
import { formatINRShort, formatTime, pct } from '../lib/format'

export function RingsPage({ selected, onSelect, refreshKey }: { selected: string | null; onSelect: (id: string | null) => void; refreshKey: number }) {
  const [minAccounts, setMin] = useState(3)
  const list = useAsync(() => api.rings(minAccounts), [minAccounts, refreshKey])
  const graph = useAsync(() => (selected ? api.ring(selected) : Promise.resolve(null)), [selected, refreshKey])

  useEffect(() => { if (!selected && list.data?.rings.length) onSelect(list.data.rings[0].ring_id) }, [list.data, selected, onSelect])
  const g = graph.data

  return (
    <div className="layout-two layout-two--wide-left">
      <Card title="Linked-account networks" subtitle="Accounts connected through shared devices or cards. Large, high-risk networks suggest coordinated fraud."
        actions={<label className="inline">Min accounts <input type="number" min={2} max={20} value={minAccounts} onChange={(e) => setMin(Math.max(2, Number(e.target.value) || 2))} /></label>}>
        <ErrorNote error={list.error} onRetry={list.reload} />
        {!list.data && !list.error && <Loading />}
        {list.data && (list.data.rings.length === 0 ? <Empty>No networks with {minAccounts}+ accounts.</Empty> : (
          <div className="table-wrap"><table className="table table--clickable table--stack">
            <thead><tr><th>Network</th><th className="num">Accts</th><th className="num">Devices</th><th className="num">Cards</th><th className="num">Tx</th><th className="num">Value</th><th className="num">Avg risk</th></tr></thead>
            <tbody>{list.data.rings.map((r) => (
              <tr key={r.ring_id} tabIndex={0} className={r.ring_id === selected ? 'row--current' : ''} onClick={() => onSelect(r.ring_id)} onKeyDown={(e) => e.key === 'Enter' && onSelect(r.ring_id)}>
                <td className="mono" data-label="Network">{r.ring_id}</td><td className="num" data-label="Accounts">{r.accounts}</td><td className="num" data-label="Devices">{r.devices}</td><td className="num" data-label="Cards">{r.cards}</td>
                <td className="num" data-label="Transactions">{r.transactions}</td><td className="num mono" data-label="Value">{formatINRShort(r.total_amount)}</td><td className="num mono" data-label="Avg risk">{pct(r.avg_risk, 0)}</td>
              </tr>))}</tbody>
          </table></div>))}
        <p className="note">{list.data?.total ?? 0} networks found. Legitimate households sharing a device show up here too; the risk column tells them apart from rings.</p>
      </Card>
      <Card title={selected ?? 'Network view'} subtitle="Square = device · circle = account · diamond = card · colour = risk">
        <ErrorNote error={graph.error} />
        {graph.loading && !g && <Loading />}
        {g && (<>
          <RingGraph graph={g} />
          {g.summary && <ul className="facts-inline">
            <li>{g.summary.accounts} accounts</li><li>{g.summary.devices} devices</li><li>{g.summary.cards} cards</li>
            <li>{g.summary.transactions} transactions</li><li>first seen {formatTime(g.summary.first_seen)}</li><li>last seen {formatTime(g.summary.last_seen)}</li>
            {g.summary.synthetic_fraud_rate !== undefined && <li>synthetic fraud rate {pct(g.summary.synthetic_fraud_rate, 0)}</li>}
          </ul>}
        </>)}
        {!selected && <Empty>Select a network to see how its accounts are linked.</Empty>}
      </Card>
    </div>
  )
}
