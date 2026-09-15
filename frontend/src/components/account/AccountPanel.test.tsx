import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot } from '../../mocks/fixtures'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import { AccountPanel } from './AccountPanel'
import { Positions } from './Positions'

beforeEach(() => {
  useGameStore.getState().reset()
  useDerivedStore.getState().reset()
})

describe('계좌', () => {
  it('현금·총자산·목표와 진행률을 보여준다', () => {
    useGameStore.getState().applySnapshot(
      baseSnapshot({ cash: 1_500_000, equity: 2_000_000 }),
      1,
    )
    render(<AccountPanel />)
    expect(screen.getByText('1,500,000원')).toBeInTheDocument()
    expect(screen.getByText('2,000,000원')).toBeInTheDocument()
    // 진행은 현금으로 잰다: 1,500,000 / 3,000,000 = 50%
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50')
  })

  it('사서 오르기만 하면 진행바가 안 움직인다 — 그게 현금 목표의 요점이다', () => {
    useGameStore.getState().applySnapshot(
      baseSnapshot({ cash: 0, equity: 2_900_000 }),
      1,
    )
    render(<AccountPanel />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0')
  })

  it('남은 분석 횟수를 항상 보여준다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot({ analyses_left: 3 }), 1)
    render(<AccountPanel />)
    expect(screen.getByText('3 / 5')).toBeInTheDocument()
  })
})

describe('보유', () => {
  it('서버가 평단을 모른다고 하면 손익을 — 로 둔다', () => {
    const snap = baseSnapshot()
    useGameStore.getState().applySnapshot(
      { ...snap, stocks: snap.stocks.map((s) => (s.symbol === 'geno' ? { ...s, held: 3 } : s)) },
      1,
    )
    render(<Positions />)
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('서버가 준 평단으로 손익을 그린다', () => {
    const snap = baseSnapshot()
    useGameStore.getState().applySnapshot(
      {
        ...snap,
        stocks: snap.stocks.map((s) =>
          s.symbol === 'geno' ? { ...s, held: 2, price: 50_000, avg_cost: 44_707 } : s,
        ),
      },
      1,
    )
    render(<Positions />)
    expect(screen.getByText('44,707원')).toBeInTheDocument()
    expect(screen.queryByText('—')).not.toBeInTheDocument()
  })
})
