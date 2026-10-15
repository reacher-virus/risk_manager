import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AlertTable } from '../components/AlertTable'
import { RingGraph } from '../components/RingGraph'
import { ErrorNote, SeverityChip } from '../components/ui'
import { ApiError } from '../api'
import type { Alert, RingGraph as RG } from '../types'

const alert = (over: Partial<Alert> = {}): Alert => ({
  transaction_id: 'TX1', customer_id: 'C1', amount: 5200, risk_score: 0.93, risk_level: 'CRITICAL', decision: 'HOLD_FOR_VERIFICATION',
  reasons: ['Account is only 0 day(s) old'], contributions: [], anomaly_score: 0.9, timestamp: '2026-08-01T10:00:00', source: 'test',
  status: 'NEW', label: null, ...over,
})

describe('AlertTable', () => {
  it('renders rows and opens a case on click and Enter', async () => {
    const onOpen = vi.fn()
    render(<AlertTable alerts={[alert(), alert({ transaction_id: 'TX2', risk_level: 'HIGH', risk_score: 0.4, amount: 1800 })]} onOpen={onOpen} />)
    expect(screen.getByText('TX1')).toBeInTheDocument()
    expect(screen.getByText('₹5,200')).toBeInTheDocument()
    await userEvent.click(screen.getByText('TX1'))
    expect(onOpen).toHaveBeenCalledWith('TX1')
    screen.getByText('TX2').closest('tr')!.focus()
    await userEvent.keyboard('{Enter}')
    expect(onOpen).toHaveBeenLastCalledWith('TX2')
  })
  it('shows an empty state', () => {
    render(<AlertTable alerts={[]} onOpen={() => {}} />)
    expect(screen.getByText(/queue is clear/i)).toBeInTheDocument()
  })
  it('shows analyst labels', () => {
    render(<AlertTable alerts={[alert({ label: 'FRAUD', status: 'ESCALATED' })]} onOpen={() => {}} />)
    expect(screen.getByText('FRAUD')).toBeInTheDocument()
    expect(screen.getByText('ESCALATED')).toBeInTheDocument()
  })
})

describe('ui', () => {
  it('SeverityChip carries its level class for styling', () => {
    render(<SeverityChip level="HIGH" />)
    expect(screen.getByText('HIGH')).toHaveClass('chip', 'chip--HIGH')
  })
  it('ErrorNote gives actionable hints per status', () => {
    const { rerender } = render(<ErrorNote error={new ApiError(0, 'down')} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/start the backend/i)
    rerender(<ErrorNote error={new ApiError(401, 'no key')} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/api key in settings/i)
    rerender(<ErrorNote error={new ApiError(403, 'nope')} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/role does not allow/i)
  })
  it('ErrorNote renders nothing without an error', () => {
    const { container } = render(<ErrorNote error={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('RingGraph', () => {
  it('draws one shape per node and one line per edge', () => {
    const g: RG = {
      ring_id: 'RING-1', summary: null,
      nodes: [
        { id: 'd:A', type: 'device', label: 'A', risk: 0.9, transactions: 4 },
        { id: 'c:1', type: 'customer', label: '1', risk: 0.8, transactions: 2 },
        { id: 'c:2', type: 'customer', label: '2', risk: 0.7, transactions: 2 },
        { id: 'p:X', type: 'card', label: 'X', risk: 0.6, transactions: 1 },
      ],
      edges: [{ source: 'c:1', target: 'd:A', weight: 2 }, { source: 'c:2', target: 'd:A', weight: 2 }, { source: 'c:1', target: 'p:X', weight: 1 }],
    }
    const { container } = render(<RingGraph graph={g} />)
    expect(container.querySelectorAll('g.ring-graph__node')).toHaveLength(4)
    expect(container.querySelectorAll('line')).toHaveLength(3)
    expect(screen.getByRole('img', { name: /RING-1/ })).toBeInTheDocument()
  })
})
