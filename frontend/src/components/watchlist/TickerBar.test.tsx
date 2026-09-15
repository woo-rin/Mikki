import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot } from '../../mocks/fixtures'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'
import { TickerBar } from './TickerBar'

beforeEach(() => {
  useGameStore.getState().reset()
  useUiStore.getState().select('hanbit')
})

describe('티커 바', () => {
  it('6종목을 가로로 보여준다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot(), 1)
    render(<TickerBar />)
    expect(screen.getAllByRole('button')).toHaveLength(6)
    expect(screen.getByText('한빛솔리드')).toBeInTheDocument()
  })

  it('누르면 선택 종목이 바뀐다 — 차트·주문·기업분석이 함께 따라간다', async () => {
    useGameStore.getState().applySnapshot(baseSnapshot(), 1)
    render(<TickerBar />)
    await userEvent.click(screen.getByRole('button', { name: /제노셀/ }))
    expect(useUiStore.getState().selected).toBe('geno')
  })

  it('선택된 종목을 표시한다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot(), 1)
    render(<TickerBar />)
    expect(screen.getByRole('button', { name: /한빛솔리드/ })).toHaveAttribute(
      'aria-pressed', 'true',
    )
  })

  it('보유 중이면 수량을 함께 보여준다', () => {
    const snap = baseSnapshot()
    useGameStore.getState().applySnapshot(
      { ...snap, stocks: snap.stocks.map((s) => s.symbol === 'geno' ? { ...s, held: 7 } : s) },
      1,
    )
    render(<TickerBar />)
    expect(screen.getByRole('button', { name: /제노셀/ })).toHaveTextContent('7주')
  })

  it('스냅샷이 없으면 아무것도 안 그린다', () => {
    const { container } = render(<TickerBar />)
    expect(container).toBeEmptyDOMElement()
  })

  it('거래량이 평소보다 튀면 배수로 알려준다', () => {
    const snap = baseSnapshot()
    useGameStore.getState().applySnapshot(
      {
        ...snap,
        stocks: snap.stocks.map((s) =>
          s.symbol === 'geno' ? { ...s, volume: 340, volume_avg: 62 } : s,
        ),
      },
      1,
    )
    render(<TickerBar />)
    expect(screen.getByRole('button', { name: /제노셀/ })).toHaveTextContent('5.5배')
  })

  it('평소 수준이면 배수를 띄우지 않는다 — 노이즈가 된다', () => {
    const snap = baseSnapshot()
    useGameStore.getState().applySnapshot(
      {
        ...snap,
        stocks: snap.stocks.map((s) =>
          s.symbol === 'geno' ? { ...s, volume: 70, volume_avg: 62 } : s,
        ),
      },
      1,
    )
    render(<TickerBar />)
    expect(screen.getByRole('button', { name: /제노셀/ })).not.toHaveTextContent('배')
  })

  it('거래가 없던 종목에서 0 으로 나누지 않는다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot(), 1)
    render(<TickerBar />)
    expect(screen.getByRole('button', { name: /제노셀/ })).not.toHaveTextContent('Infinity')
  })
})
