import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { baseSnapshot, capturedTrade } from '../../mocks/fixtures'
import { server } from '../../mocks/server'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'
import { Toasts } from '../system/Toasts'
import { OrderTicket } from './OrderTicket'

beforeEach(() => {
  useGameStore.getState().reset()
  useDerivedStore.getState().reset()
  useUiStore.setState({ selected: 'geno', toasts: [] })
  useGameStore.getState().setSession('s')
  useGameStore.getState().applySnapshot(baseSnapshot(), 1)
})

describe('주문 티켓', () => {
  it('예상 금액과 수수료를 보여준다', async () => {
    render(<><OrderTicket /><Toasts /></>)
    await userEvent.click(screen.getByRole('button', { name: '한 주 늘리기' })) // 1 → 2
    // geno 45000 × 2 = 90,000, 수수료 180
    expect(screen.getByText('90,000원')).toBeInTheDocument()
    expect(screen.getByText('180원')).toBeInTheDocument()
  })

  it('최대 버튼이 수수료를 포함한 상한을 넣는다', async () => {
    render(<><OrderTicket /><Toasts /></>)
    await userEvent.click(screen.getByRole('button', { name: '최대' }))
    // 1,000,000 / (45000 * 1.002) → 22주
    expect(screen.getByLabelText('수량')).toHaveValue(22)
  })

  it('체결 후 화면이 응답의 가격·수수료·현금을 따른다', async () => {
    render(<><OrderTicket /><Toasts /></>)
    await userEvent.click(screen.getByRole('button', { name: '한 주 늘리기' })) // 1 → 2
    await userEvent.click(screen.getByRole('button', { name: '매수' }))

    await screen.findByRole('alert')
    expect(useGameStore.getState().snapshot?.cash).toBe(capturedTrade.cash)
    // 표시가 45,000 과 체결가 44,618 의 차이를 알린다
    expect(screen.getByRole('alert')).toHaveTextContent('44,618원')
  })

  it('오류 메시지를 서버 문장 그대로 보여준다', async () => {
    server.use(
      http.post('/api/trade', () =>
        HttpResponse.json(
          { detail: { code: 'insufficient_cash', message: '현금이 부족합니다.' } },
          { status: 400 },
        ),
      ),
    )
    render(<><OrderTicket /><Toasts /></>)
    await userEvent.click(screen.getByRole('button', { name: '매수' }))
    await screen.findByRole('alert')
    expect(useUiStore.getState().toasts[0]?.text).toBe('현금이 부족합니다.')
  })

  it('잠금 중에는 주문할 수 없다', () => {
    useGameStore.getState().applySnapshot(baseSnapshot({ locked: true, lock_remaining: 90 }), 2)
    render(<><OrderTicket /><Toasts /></>)
    expect(screen.getByRole('button', { name: '매수' })).toBeDisabled()
  })
})
