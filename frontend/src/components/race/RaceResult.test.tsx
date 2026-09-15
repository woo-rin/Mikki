import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot } from '../../mocks/fixtures'
import { useGameStore } from '../../store/gameStore'
import { RaceResult } from './RaceResult'

let seq = 0

function finish(patch = {}) {
  useGameStore.getState().applySnapshot(
    {
      ...baseSnapshot(),
      status: 'finished',
      winner: '정소장',
      ranking: [
        { rank: 1, name: '정소장', cash: 1_246_074, is_player: false },
        { rank: 2, name: '강사원', cash: 1_230_422, is_player: false },
        { rank: 3, name: '나', cash: 998_806, is_player: true },
      ],
      ...patch,
    },
    ++seq,
  )
}

beforeEach(() => {
  useGameStore.getState().reset()
  useGameStore.getState().setSession('s1')
  seq = 0
})

describe('경주 결과', () => {
  it('경주 중에는 안 뜬다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot(), ++seq)
    const { container } = render(<RaceResult />)
    expect(container).toBeEmptyDOMElement()
  })

  it('끝나면 승자와 전체 순위를 보여준다', () => {
    finish()
    render(<RaceResult />)
    expect(screen.getByText('정소장 승')).toBeInTheDocument()
    const rows = screen.getAllByTestId('rank-row')
    expect(rows).toHaveLength(3)
    expect(rows[0]).toHaveTextContent('1,246,074원')
  })

  it('내 줄을 표시한다', () => {
    finish()
    render(<RaceResult />)
    const rows = screen.getAllByTestId('rank-row')
    expect(rows[2]).toHaveAttribute('data-me', 'true')
    expect(rows[0]).toHaveAttribute('data-me', 'false')
  })

  it('내가 이기면 그렇게 말한다', () => {
    finish({
      winner: 'you',
      ranking: [{ rank: 1, name: '나', cash: 3_000_000, is_player: true }],
    })
    render(<RaceResult />)
    expect(screen.getByText(/당신이 이겼습니다/)).toBeInTheDocument()
  })

  it('승자의 현금이 2위보다 적으면 먼저 도달했다고 설명한다', () => {
    finish({
      winner: '정소장',
      ranking: [
        { rank: 1, name: '정소장', cash: 3_000_000, is_player: false },
        { rank: 2, name: '강사원', cash: 4_100_000, is_player: false },
      ],
    })
    render(<RaceResult />)
    expect(screen.getByText(/목표에 먼저 도달/)).toBeInTheDocument()
  })

  it('마감으로 끝났으면 현금 1위라고 설명한다', () => {
    finish()
    render(<RaceResult />)
    expect(screen.getByText(/마감 · 현금 1위/)).toBeInTheDocument()
  })

  it('다시 하기 버튼이 있다', async () => {
    finish()
    render(<RaceResult />)
    expect(screen.getByRole('button', { name: '다시 하기' })).toBeEnabled()
  })

  it('화면 전체를 덮는다', () => {
    finish()
    render(<RaceResult />)
    const panel = screen.getByRole('dialog')
    expect(panel).toHaveAttribute('aria-modal', 'true')
  })
})
