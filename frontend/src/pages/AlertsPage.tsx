import { useState } from 'react'
import { api } from '../api'
import { AlertTable } from '../components/AlertTable'
import { Button, Card, ErrorNote, Loading } from '../components/ui'
import { useAsync } from '../hooks'

const PAGE = 15

export function AlertsPage({ onOpen, refreshKey }: { onOpen: (id: string) => void; refreshKey: number }) {
  const [level, setLevel] = useState('HIGH')
  const [status, setStatus] = useState('ALL')
  const [source, setSource] = useState('all')
  const [sort, setSort] = useState('risk')
  const [page, setPage] = useState(0)
  const [exporting, setExporting] = useState(false)
  const [exportErr, setExportErr] = useState<Error | null>(null)
  const q = { limit: PAGE, offset: page * PAGE, min_level: level, status, source, sort }
  const list = useAsync(() => api.alerts(q), [level, status, source, sort, page, refreshKey])
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(0) }

  const exportCsv = async () => {
    setExporting(true); setExportErr(null)
    try { await api.exportAlerts(q) } catch (e) { setExportErr(e as Error) } finally { setExporting(false) }
  }
  const total = list.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE))

  return (
    <Card title="Alert queue" subtitle="Investigate top to bottom; click a row for the full case"
      actions={<Button onClick={exportCsv} busy={exporting}>Export CSV</Button>}>
      <div className="filters">
        <label>Min severity
          <select value={level} onChange={(e) => reset(setLevel)(e.target.value)}>
            <option value="MEDIUM">Medium+</option><option value="HIGH">High+</option><option value="CRITICAL">Critical only</option>
          </select></label>
        <label>Status
          <select value={status} onChange={(e) => reset(setStatus)(e.target.value)}>
            {['ALL', 'NEW', 'APPROVED', 'HELD', 'ESCALATED'].map((s) => <option key={s}>{s}</option>)}
          </select></label>
        <label>Source
          <select value={source} onChange={(e) => reset(setSource)(e.target.value)}>
            <option value="all">All</option><option value="test">Held-out test</option><option value="live">Live / simulated</option>
          </select></label>
        <label>Sort
          <select value={sort} onChange={(e) => reset(setSort)(e.target.value)}>
            <option value="risk">Highest risk</option><option value="time">Most recent</option>
          </select></label>
        <span className="filters__count">{total.toLocaleString('en-IN')} alerts</span>
      </div>
      <ErrorNote error={list.error ?? exportErr} onRetry={list.reload} />
      {list.data ? <AlertTable alerts={list.data.items} onOpen={onOpen} /> : !list.error && <Loading />}
      <div className="pager">
        <Button variant="ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>← Previous</Button>
        <span>Page {page + 1} of {pages}</span>
        <Button variant="ghost" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Next →</Button>
      </div>
    </Card>
  )
}
