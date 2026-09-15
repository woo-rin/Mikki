import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import type { TradeRow } from '../../api/types'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import type { FeedItem } from '../../store/merge'
import { NewsCard } from './NewsCard'

function item(patch: Partial<FeedItem> = {}): FeedItem {
  return {
    newsId: 1, symbol: 'geno', name: '제노셀', sector: '바이오',
    headline: '제노셀 임상 3상 중단', body: '본문', offline: false,
    publishTick: 100, analysis: null, ...patch,
  }
}

function trade(patch: Partial<TradeRow> = {}): TradeRow {
  return {
    seq: 1, tick: 110, actor: '김부장', symbol: 'geno', name: '제노셀',
    side: 'buy', qty: 15, price: 40_000, ...patch,
  }
}

beforeEach(() => {
  useGameStore.getState().reset()
  useDerivedStore.getState().reset()
  useGameStore.getState().setSession('s1')
})

describe('기사에 들어간 참가자', () => {
  it('이 기사 뒤 같은 종목에 들어간 사람을 보여준다', () => {
    useDerivedStore.setState({ trades: [trade({ actor: '김부장' })] })
    render(<NewsCard item={item()} tick={120} />)
    expect(screen.getByText(/김부장/)).toBeInTheDocument()
    expect(screen.getByText(/매수 15/)).toBeInTheDocument()
  })

  it('인과를 주장하지 않는다 — 문구가 "이후" 라고 말한다', () => {
    useDerivedStore.setState({ trades: [trade()] })
    render(<NewsCard item={item()} tick={120} />)
    expect(screen.getByText(/기사 이후/)).toBeInTheDocument()
  })

  it('다른 종목 체결은 섞이지 않는다', () => {
    useDerivedStore.setState({
      trades: [trade({ symbol: 'hanbit', name: '한빛솔리드', actor: '박선배' })],
    })
    render(<NewsCard item={item()} tick={120} />)
    expect(screen.queryByText(/박선배/)).not.toBeInTheDocument()
  })

  it('기사 전 체결은 단서가 아니다', () => {
    useDerivedStore.setState({ trades: [trade({ tick: 90 })] })
    render(<NewsCard item={item()} tick={120} />)
    expect(screen.queryByText(/기사 이후/)).not.toBeInTheDocument()
  })

  it('아무도 안 들어갔으면 그 줄 자체가 없다', () => {
    render(<NewsCard item={item()} tick={120} />)
    expect(screen.queryByText(/기사 이후/)).not.toBeInTheDocument()
  })
})
