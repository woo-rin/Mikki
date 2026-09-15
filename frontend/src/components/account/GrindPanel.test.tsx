import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot } from '../../mocks/fixtures'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'
import { GrindPanel } from './GrindPanel'

beforeEach(() => {
  useGameStore.getState().reset()
  useUiStore.setState({ toasts: [] })
  useGameStore.getState().setSession('s')
})

describe('노가다', () => {
  it('평소에도 누를 수 있다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot({ bankrupt: false }), 1)
    render(<GrindPanel />)
    expect(screen.getByRole('button', { name: '노가다' })).toBeEnabled()
    expect(screen.getByRole('heading', { name: '노가다' })).toBeInTheDocument()
  })

  it('평소에는 파산 경고를 띄우지 않는다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot({ bankrupt: false }), 1)
    render(<GrindPanel />)
    expect(screen.queryByText(/10만원 아래/)).not.toBeInTheDocument()
  })

  it('잠금값이 얼마인지는 평소에도 말해준다 — 이게 노가다의 값이다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot({ bankrupt: false }), 1)
    render(<GrindPanel />)
    expect(screen.getByText(/120초간 매매와 분석이 잠깁니다/)).toBeInTheDocument()
  })

  it('파산이면 제목과 문구가 경고로 바뀐다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot({ bankrupt: true, cash: 50_000 }), 1)
    render(<GrindPanel />)
    expect(screen.getByRole('heading', { name: '파산' })).toBeInTheDocument()
    expect(screen.getByText(/매매와 분석은 계속 가능합니다/)).toBeInTheDocument()
  })

  it('보수를 현금에 즉시 더하지 않고 잠금만 건다', async () => {
    useGameStore.getState().applySnapshot(baseSnapshot({ bankrupt: true, cash: 50_000 }), 1)
    render(<GrindPanel />)
    await userEvent.click(screen.getByRole('button', { name: '노가다' }))

    await screen.findByText(/120초/)
    const snap = useGameStore.getState().snapshot
    expect(snap?.cash).toBe(50_000)
    expect(snap?.locked).toBe(true)
    expect(snap?.grind_count).toBe(1)
  })

  it('잠금 중에는 남은 시간과 회차를 보여준다', () => {
    useGameStore.getState().applySnapshot(
      baseSnapshot({ bankrupt: true, locked: true, lock_remaining: 42, grind_count: 3 }),
      1,
    )
    render(<GrindPanel />)
    expect(screen.getByText(/42초/)).toBeInTheDocument()
    expect(screen.getByText(/3회차/)).toBeInTheDocument()
  })
})
