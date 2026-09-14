import { render, screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot } from '../../mocks/fixtures'
import { server } from '../../mocks/server'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import { SESSION_KEY, SessionGate } from './SessionGate'

beforeEach(() => {
  useGameStore.getState().reset()
  useDerivedStore.getState().reset()
  sessionStorage.clear()
})

describe('세션 게이트', () => {
  it('저장된 세션이 없으면 새 게임을 시작한다', async () => {
    render(<SessionGate><div>보드</div></SessionGate>)
    expect(await screen.findByText('보드')).toBeInTheDocument()
    expect(sessionStorage.getItem(SESSION_KEY)).toBe('test-session')
  })

  it('시작 직후 뉴스가 빈 배열이어도 오류로 다루지 않는다', async () => {
    server.use(http.post('/api/game', () => HttpResponse.json(baseSnapshot({ news: [] }))))
    render(<SessionGate><div>보드</div></SessionGate>)
    expect(await screen.findByText('보드')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('세션이 사라졌으면 전용 화면을 띄우고 조용히 새 게임을 시작하지 않는다', async () => {
    sessionStorage.setItem(SESSION_KEY, 'dead')
    server.use(
      http.get('/api/state', () =>
        HttpResponse.json(
          { detail: { code: 'no_session', message: '세션을 찾을 수 없습니다.' } },
          { status: 404 },
        ),
      ),
    )
    render(<SessionGate><div>보드</div></SessionGate>)
    expect(await screen.findByRole('button', { name: '새 게임' })).toBeInTheDocument()
    expect(screen.queryByText('보드')).not.toBeInTheDocument()
  })
})
