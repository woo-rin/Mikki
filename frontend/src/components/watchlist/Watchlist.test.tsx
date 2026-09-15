import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot } from '../../mocks/fixtures'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'
import { Watchlist } from './Watchlist'

beforeEach(() => {
  useGameStore.getState().reset()
  useUiStore.getState().select('hanbit')
})

describe('워치리스트', () => {
  it('6종목의 이름·섹터·현재가를 보여준다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot(), 1)
    render(<Watchlist />)
    expect(screen.getAllByRole('row')).toHaveLength(7) // 헤더 + 6
    expect(screen.getByText('한빛솔리드')).toBeInTheDocument()
    expect(screen.getByText('반도체')).toBeInTheDocument()
    expect(screen.getByText('82,000원')).toBeInTheDocument()
  })

  it('등락률은 시작가 대비이고 부호로 색이 갈린다', () => {
    const snap = baseSnapshot()
    useGameStore.getState().applySnapshot(
      {
        ...snap,
        stocks: snap.stocks.map((s) =>
          s.symbol === 'hanbit' ? { ...s, price: 76_206, change_pct: -7.07 } : s,
        ),
      },
      1,
    )
    render(<Watchlist />)
    expect(screen.getByText('-7.07%')).toHaveClass('down')
  })

  it('행을 누르면 선택 종목이 바뀐다', async () => {
    useGameStore.getState().applySnapshot(baseSnapshot(), 1)
    render(<Watchlist />)
    await userEvent.click(screen.getByRole('button', { name: /제노셀/ }))
    expect(useUiStore.getState().selected).toBe('geno')
  })
})
