import { describe, expect, it } from 'vitest'
import {
  baseSnapshot, capturedAnalyze, capturedCompanyAnalysis, capturedTrade, sampleNews,
} from '../mocks/fixtures'
import { applyBuy, emptyPosition } from '../lib/money'
import {
  HISTORY_LIMIT, appendHistory, applyCompanyAnalysisToSnapshot, applyGrindToSnapshot,
  applyTradeToSnapshot, attachAnalysis, isFresher, maxNewsId, positionRows, upsertNews,
} from './merge'

describe('가격 이력', () => {
  it('같은 tick 이 두 번 와도 한 번만 쌓인다', () => {
    const snap = baseSnapshot({ tick: 5 })
    const once = appendHistory({}, snap)
    const twice = appendHistory(once, snap)
    expect(once['hanbit']).toHaveLength(1)
    expect(twice['hanbit']).toHaveLength(1)
  })

  it('바뀐 것이 없으면 같은 객체를 돌려준다 — 헛 리렌더를 막는다', () => {
    const snap = baseSnapshot({ tick: 5 })
    const once = appendHistory({}, snap)
    expect(appendHistory(once, snap)).toBe(once)
  })

  it('tick 이 오르면 쌓인다', () => {
    let h = appendHistory({}, baseSnapshot({ tick: 1 }))
    h = appendHistory(h, baseSnapshot({ tick: 2 }))
    expect(h['hanbit']).toHaveLength(2)
  })

  it('60틱을 넘으면 오래된 것을 버린다', () => {
    let h: ReturnType<typeof appendHistory> = {}
    for (let t = 0; t < HISTORY_LIMIT + 15; t++) {
      h = appendHistory(h, baseSnapshot({ tick: t }))
    }
    expect(h['hanbit']).toHaveLength(HISTORY_LIMIT)
    expect(h['hanbit']?.[0]?.tick).toBe(15)
  })
})

describe('뉴스 누적', () => {
  it('news_id 기준으로 upsert 한다', () => {
    const first = upsertNews([], baseSnapshot({ tick: 200, news: [sampleNews()] }))
    expect(first).toHaveLength(1)

    const again = upsertNews(
      first,
      baseSnapshot({ tick: 260, news: [sampleNews({ headline: '고쳐진 제목' })] }),
    )
    expect(again).toHaveLength(1)
    expect(again[0]?.headline).toBe('고쳐진 제목')
  })

  it('수신 시각을 절대 tick 으로 고정한다', () => {
    const feed = upsertNews([], baseSnapshot({ tick: 200, news: [sampleNews()] }))
    expect(feed[0]?.publishTick).toBe(12) // 200 - 188
  })

  it('새 기사는 앞에 붙는다', () => {
    const feed = upsertNews(
      [],
      baseSnapshot({ tick: 300, news: [sampleNews({ news_id: 0 }), sampleNews({ news_id: 1 })] }),
    )
    expect(feed.map((f) => f.newsId)).toEqual([1, 0])
  })

  it('새 기사가 없으면 같은 배열을 돌려준다', () => {
    const feed = upsertNews([], baseSnapshot({ tick: 200, news: [sampleNews()] }))
    expect(upsertNews(feed, baseSnapshot({ tick: 260, news: [] }))).toBe(feed)
  })

  it('since 커서는 받은 최대 news_id 다. 아직 없으면 -1', () => {
    expect(maxNewsId([])).toBe(-1)
    const feed = upsertNews(
      [],
      baseSnapshot({ tick: 300, news: [sampleNews({ news_id: 0 }), sampleNews({ news_id: 4 })] }),
    )
    expect(maxNewsId(feed)).toBe(4)
  })
})

describe('분석 병합', () => {
  it('해당 기사에만 붙는다', () => {
    const feed = upsertNews(
      [],
      baseSnapshot({ tick: 300, news: [sampleNews({ news_id: 0 }), sampleNews({ news_id: 1 })] }),
    )
    const next = attachAnalysis(feed, capturedAnalyze, 300)
    expect(next.find((f) => f.newsId === 0)?.analysis?.label).toBe('무영향')
    expect(next.find((f) => f.newsId === 1)?.analysis).toBeNull()
  })

  it('이미 반영된 기사는 램프 끝 tick 을 만들지 않는다', () => {
    const feed = upsertNews([], baseSnapshot({ tick: 300, news: [sampleNews()] }))
    const next = attachAnalysis(feed, capturedAnalyze, 300) // ramp_remaining 0
    expect(next[0]?.analysis?.rampEndTick).toBeNull()
  })

  it('남은 램프가 있으면 끝 tick 을 고정한다', () => {
    const feed = upsertNews([], baseSnapshot({ tick: 300, news: [sampleNews()] }))
    const next = attachAnalysis(
      feed,
      { ...capturedAnalyze, strength: 'up_strong', ramp_remaining: 40, already_priced_in: false },
      300,
    )
    expect(next[0]?.analysis?.rampEndTick).toBe(340)
  })
})

describe('시퀀스 가드', () => {
  it('더 새로운 응답만 받는다', () => {
    expect(isFresher(3, 4)).toBe(true)
    expect(isFresher(3, 3)).toBe(false)
    expect(isFresher(3, 2)).toBe(false) // 순서가 뒤바뀐 응답
  })
})

describe('보유 행', () => {
  it('보유가 없는 종목은 빠진다', () => {
    expect(positionRows(baseSnapshot(), {})).toEqual([])
  })

  it('held 는 있는데 평단이 없으면 손익이 null 이다 — 새로고침 후', () => {
    const snap = baseSnapshot({
      stocks: baseSnapshot().stocks.map((s) => (s.symbol === 'geno' ? { ...s, held: 3 } : s)),
    })
    const rows = positionRows(snap, {})
    expect(rows).toHaveLength(1)
    expect(rows[0]?.avg).toBeNull()
    expect(rows[0]?.unrealized).toBeNull()
  })

  it('평단을 알면 손익을 계산한다', () => {
    const snap = baseSnapshot({
      stocks: baseSnapshot().stocks.map((s) =>
        s.symbol === 'geno' ? { ...s, held: 3, price: 50_000 } : s,
      ),
    })
    const positions = { geno: applyBuy(emptyPosition(), 45_000, 3) } // avg 45090
    const rows = positionRows(snap, positions)
    expect(rows[0]?.avg).toBe(45_090)
    expect(rows[0]?.unrealized).toBe((50_000 - 45_090) * 3)
  })
})

describe('액션 응답 반영', () => {
  it('체결은 응답의 현금·총자산을 그대로 쓴다', () => {
    const next = applyTradeToSnapshot(baseSnapshot(), capturedTrade)
    expect(next.cash).toBe(910_586)
    expect(next.equity).toBe(999_822)
  })

  it('노가다 보수는 현금에 즉시 더해지지 않는다', () => {
    const snap = baseSnapshot({ cash: 50_000, bankrupt: true })
    const next = applyGrindToSnapshot(snap, {
      payout: 200_000, lock_remaining: 120, grind_count: 1,
    })
    expect(next.cash).toBe(50_000) // 잠금이 끝난 뒤 폴링으로 들어온다
    expect(next.locked).toBe(true)
    expect(next.lock_remaining).toBe(120)
    expect(next.grind_count).toBe(1)
  })
})

describe('기업분석 반영', () => {
  it('잔여 횟수를 응답대로 쓴다', () => {
    const next = applyCompanyAnalysisToSnapshot(baseSnapshot(), capturedCompanyAnalysis)
    expect(next.company_analyses_left).toBe(1)
  })

  it('그 종목만 분석됨으로 표시한다', () => {
    const next = applyCompanyAnalysisToSnapshot(baseSnapshot(), capturedCompanyAnalysis)
    expect(next.stocks.find((s) => s.symbol === 'geno')?.fundamentals_analyzed).toBe(true)
    expect(next.stocks.find((s) => s.symbol === 'hanbit')?.fundamentals_analyzed).toBe(false)
  })

  it('같은 종목을 다시 사면 서버가 횟수를 안 깎는다 — 응답을 그대로 믿는다', () => {
    const once = applyCompanyAnalysisToSnapshot(baseSnapshot(), capturedCompanyAnalysis)
    const twice = applyCompanyAnalysisToSnapshot(once, capturedCompanyAnalysis)
    expect(twice.company_analyses_left).toBe(1)
  })
})
