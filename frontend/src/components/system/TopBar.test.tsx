import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot } from '../../mocks/fixtures'
import { useGameStore } from '../../store/gameStore'
import { TopBar } from './TopBar'

beforeEach(() => {
  useGameStore.getState().reset()
})

describe('상단 바', () => {
  it('라운드·경과·현금·총자산과 두 분석 잔여를 보여준다', () => {
    useGameStore.getState().applySnapshot({ ...baseSnapshot(), tick: 120 }, 1)
    render(<TopBar />)
    expect(screen.getByText('R1')).toBeInTheDocument()
    expect(screen.getByText('120s')).toBeInTheDocument()
    expect(screen.getByText('1,000,000원')).toBeInTheDocument()
    expect(screen.getByLabelText('남은 AI 분석')).toHaveTextContent('5')
    expect(screen.getByLabelText('남은 기업분석')).toHaveTextContent('2')
  })

  it('목표에 닿으면 배너가 뜬다 — 탭에 묻히면 안 되는 정보다', () => {
    useGameStore.getState().applySnapshot(
      { ...baseSnapshot(), goal_reached: true }, 1,
    )
    render(<TopBar />)
    expect(screen.getByText(/목표 달성/)).toBeInTheDocument()
  })

  it('목표 전에는 배너가 없다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot(), 1)
    render(<TopBar />)
    expect(screen.queryByText(/목표 달성/)).not.toBeInTheDocument()
  })

  it('스냅샷이 없으면 아무것도 안 그린다', () => {
    const { container } = render(<TopBar />)
    expect(container).toBeEmptyDOMElement()
  })
})
