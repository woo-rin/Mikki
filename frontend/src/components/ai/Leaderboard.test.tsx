import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot, sampleAi } from '../../mocks/fixtures'
import { useGameStore } from '../../store/gameStore'
import { Leaderboard } from './Leaderboard'

beforeEach(() => useGameStore.getState().reset())

describe('리더보드', () => {
  it('AI 를 순위대로 보여준다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot(), 1)
    render(<Leaderboard />)
    const names = screen.getAllByTestId('ai-name').map((e) => e.textContent)
    expect(names.filter((n) => n !== '나')).toEqual(sampleAi().map((a) => a.name))
  })

  it('나도 같은 표에 끼워 총자산으로 줄 세운다', () => {
    useGameStore.getState().applySnapshot({ ...baseSnapshot(), equity: 1_500_000 }, 1)
    render(<Leaderboard />)
    const rows = screen.getAllByTestId('ai-name').map((e) => e.textContent)
    expect(rows[0]).toBe('나')
  })

  it('보유 종목은 보여주지 않는다 — 체결 피드로 읽는 것이 정당한 우위다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot(), 1)
    render(<Leaderboard />)
    expect(screen.queryByText(/제노셀|한빛솔리드/)).not.toBeInTheDocument()
  })

  it('스냅샷이 없으면 아무것도 안 그린다', () => {
    const { container } = render(<Leaderboard />)
    expect(container).toBeEmptyDOMElement()
  })
})
