import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { sampleTrades } from '../../mocks/fixtures'
import { useDerivedStore } from '../../store/derivedStore'
import { TradeFeed } from './TradeFeed'

beforeEach(() => useDerivedStore.getState().reset())

describe('체결 피드', () => {
  it('최신 체결이 위에 온다', () => {
    useDerivedStore.setState({ trades: sampleTrades().slice().reverse() })
    render(<TradeFeed />)
    const actors = screen.getAllByTestId('trade-actor').map((e) => e.textContent)
    expect(actors).toEqual(['김부장', '강사원'])
  })

  it('누가 무엇을 얼마에 샀는지 보여준다', () => {
    useDerivedStore.setState({ trades: sampleTrades() })
    render(<TradeFeed />)
    expect(screen.getByText('제노셀')).toBeInTheDocument()
    expect(screen.getByText('태산건영')).toBeInTheDocument()
    expect(screen.getByText('32,442원')).toBeInTheDocument()
    expect(screen.getByText('매도')).toBeInTheDocument()
  })

  it('아직 체결이 없으면 그렇게 말한다', () => {
    render(<TradeFeed />)
    expect(screen.getByText(/아직 체결이 없습니다/)).toBeInTheDocument()
  })
})
