import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot } from '../../mocks/fixtures'
import { useGameStore } from '../../store/gameStore'
import { TopBar } from './TopBar'

beforeEach(() => {
  useGameStore.getState().reset()
})

describe('상단 바', () => {
  it('남은 시간·현금·총자산과 두 분석 잔여를 보여준다', () => {
    useGameStore.getState().applySnapshot(
      { ...baseSnapshot(), tick: 120, seconds_left: 480 }, 1,
    )
    render(<TopBar />)
    expect(screen.getByLabelText('남은 시간')).toHaveTextContent('8:00')
    expect(screen.getByLabelText('현금')).toHaveTextContent('1,000,000원')
    expect(screen.getByLabelText('총자산')).toHaveTextContent('1,000,000원')
    expect(screen.getByLabelText('목표 자산')).toHaveTextContent('3,000,000원')
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

describe('마감 시계', () => {
  it('1분 아래면 강조한다 — 지금 팔아야 하나가 조여온다', () => {
    useGameStore.getState().applySnapshot({ ...baseSnapshot(), seconds_left: 42 }, 1)
    render(<TopBar />)
    expect(screen.getByLabelText('남은 시간')).toHaveClass('urgent')
    expect(screen.getByLabelText('남은 시간')).toHaveTextContent('0:42')
  })

  it('여유가 있으면 강조하지 않는다', () => {
    useGameStore.getState().applySnapshot({ ...baseSnapshot(), seconds_left: 300 }, 1)
    render(<TopBar />)
    expect(screen.getByLabelText('남은 시간')).not.toHaveClass('urgent')
  })
})
