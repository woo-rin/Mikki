import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { baseSnapshot } from '../../mocks/fixtures'
import { useGameStore } from '../../store/gameStore'
import { GrindOverlay, SCENES, SCENE_MS } from './GrindOverlay'

let seq = 0

function lock(patch = {}) {
  // 폴링 시퀀스는 단조 증가여야 한다. 같은 번호로 두 번 적용하면 순서 가드가
  // 뒤엣것을 버린다 — 그게 맞는 동작이다.
  useGameStore.getState().applySnapshot(
    { ...baseSnapshot(), locked: true, lock_remaining: 87, grind_count: 1, ...patch },
    ++seq,
  )
}

beforeEach(() => {
  useGameStore.getState().reset()
  seq = 0
})

describe('노가다 오버레이', () => {
  it('잠금이 아니면 아무것도 안 그린다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot(), ++seq)
    const { container } = render(<GrindOverlay />)
    expect(container).toBeEmptyDOMElement()
  })

  it('스냅샷이 없어도 안 그린다', () => {
    const { container } = render(<GrindOverlay />)
    expect(container).toBeEmptyDOMElement()
  })

  it('잠금 중이면 남은 초를 보여준다', () => {
    lock()
    render(<GrindOverlay />)
    expect(screen.getByText('87')).toBeInTheDocument()
    expect(screen.getByText(/노가다 중/)).toBeInTheDocument()
  })

  it('남은 초는 서버 값을 그대로 쓴다 — 클라이언트 타이머를 돌리지 않는다', () => {
    lock({ lock_remaining: 12 })
    const { rerender } = render(<GrindOverlay />)
    expect(screen.getByText('12')).toBeInTheDocument()

    lock({ lock_remaining: 11 })
    rerender(<GrindOverlay />)
    expect(screen.getByText('11')).toBeInTheDocument()
  })

  it('회차를 함께 보여준다', () => {
    lock({ grind_count: 3 })
    render(<GrindOverlay />)
    expect(screen.getByText(/3회차/)).toBeInTheDocument()
  })

  it('그동안 시장이 움직인다는 것을 말한다 — 이게 노가다의 값이다', () => {
    lock()
    render(<GrindOverlay />)
    expect(screen.getByText(/시장은 계속 움직입니다/)).toBeInTheDocument()
  })

  it('화면 전체를 덮어 조작을 막는다', () => {
    lock()
    render(<GrindOverlay />)
    const overlay = screen.getByTestId('grind-overlay')
    expect(overlay).toHaveAttribute('aria-modal', 'true')
    expect(overlay).toHaveAttribute('role', 'dialog')
  })

  it('스크린리더에 진행 상황을 알린다', () => {
    lock({ lock_remaining: 42 })
    render(<GrindOverlay />)
    expect(screen.getByRole('dialog')).toHaveAccessibleName(/노가다/)
    expect(screen.getByRole('timer')).toHaveTextContent('42')
  })
})

describe('일하는 장면', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('처음에는 곡괭이질이다', () => {
    lock()
    render(<GrindOverlay />)
    expect(screen.getByTestId('grind-scene')).toHaveAttribute('data-scene', 'dig')
  })

  it('시간이 지나면 다음 장면으로 넘어간다', () => {
    lock()
    render(<GrindOverlay />)
    act(() => { vi.advanceTimersByTime(SCENE_MS) })
    expect(screen.getByTestId('grind-scene')).toHaveAttribute('data-scene', 'carry')
    act(() => { vi.advanceTimersByTime(SCENE_MS) })
    expect(screen.getByTestId('grind-scene')).toHaveAttribute('data-scene', 'shovel')
  })

  it('한 바퀴 돌면 처음으로 돌아온다', () => {
    lock()
    render(<GrindOverlay />)
    act(() => { vi.advanceTimersByTime(SCENE_MS * SCENES.length) })
    expect(screen.getByTestId('grind-scene')).toHaveAttribute('data-scene', 'dig')
  })

  it('잠금이 풀리면 타이머가 남지 않는다', () => {
    lock()
    const { unmount } = render(<GrindOverlay />)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('짐을 나를 때 다리가 둘이고 뒷다리가 먼저 그려진다', () => {
    lock()
    const { container } = render(<GrindOverlay />)
    act(() => { vi.advanceTimersByTime(SCENE_MS) })

    const legs = container.querySelectorAll('.leg-a, .leg-b')
    expect(legs).toHaveLength(2)
    // 뒷다리가 앞에 와야 앞다리에 가려진다 — 겹칠 때도 둘로 읽힌다
    expect(legs[0]).toHaveClass('leg-b')
    expect(legs[1]).toHaveClass('leg-a')
  })

  it('장면마다 다른 도구가 그려진다', () => {
    lock()
    render(<GrindOverlay />)
    expect(screen.getByTestId('tool-pick')).toBeInTheDocument()
    act(() => { vi.advanceTimersByTime(SCENE_MS) })
    expect(screen.getByTestId('tool-bag')).toBeInTheDocument()
    act(() => { vi.advanceTimersByTime(SCENE_MS) })
    expect(screen.getByTestId('tool-shovel')).toBeInTheDocument()
  })
})
