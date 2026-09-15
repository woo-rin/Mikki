import type {
  AnalyzeResult, CompanyAnalysisResult, GrindResult, NewsItem, Snapshot, Stock, Strength,
  Symbol_, TradeResult,
} from '../api/types'
import { publishTick as toPublishTick, rampEndTick } from '../lib/derive'
import { type Position, unrealizedFor } from '../lib/money'

export interface PricePoint {
  tick: number
  price: number
}

export interface FeedAnalysis {
  strength: Strength
  label: string
  commentary: string
  /** null 이면 이미 반영이 끝난 기사다. 밴드를 그리지 않는다. */
  rampEndTick: number | null
  offline: boolean
}

export interface FeedItem {
  newsId: number
  symbol: Symbol_
  name: string
  sector: string
  headline: string
  body: string
  offline: boolean
  /** 수신 시점에 고정한 절대 tick. age_seconds 는 얼어붙으므로 쓰지 않는다. */
  publishTick: number
  analysis: FeedAnalysis | null
}

export interface PositionRow {
  symbol: Symbol_
  name: string
  held: number
  price: number
  /** null 이면 평단을 모른다 — 새로고침 후 상태 */
  avg: number | null
  unrealized: number | null
}

/**
 * 서버가 주는 history 는 가격만 있고 tick 이 없다. 마지막 값이 현재 tick 이므로
 * 거기서 거슬러 올라가며 좌표를 입힌다.
 *
 * 뉴스 마커와 램프 밴드가 tick 으로 배치되므로 이 변환 없이는 마커가 엉뚱한 데 붙는다.
 */
export function priceSeries(stock: Stock, tick: number): PricePoint[] {
  const n = stock.history.length
  return stock.history.map((price, i) => ({ tick: tick - (n - 1 - i), price }))
}

function toFeedItem(n: NewsItem, snapshotTick: number, prior: FeedItem | undefined): FeedItem {
  return {
    newsId: n.news_id,
    symbol: n.symbol,
    name: n.name,
    sector: n.sector,
    headline: n.headline,
    body: n.body,
    offline: n.offline,
    publishTick: prior?.publishTick ?? toPublishTick(snapshotTick, n.age_seconds),
    analysis: prior?.analysis ?? null,
  }
}

/** news_id 기준 upsert. 최신 기사가 앞에 온다. */
export function upsertNews(prev: FeedItem[], snap: Snapshot): FeedItem[] {
  if (snap.news.length === 0) return prev

  const byId = new Map(prev.map((f) => [f.newsId, f]))
  for (const n of snap.news) {
    byId.set(n.news_id, toFeedItem(n, snap.tick, byId.get(n.news_id)))
  }
  return [...byId.values()].sort((a, b) => b.newsId - a.newsId)
}

export function attachAnalysis(
  prev: FeedItem[],
  res: AnalyzeResult,
  currentTick: number,
): FeedItem[] {
  return prev.map((f) =>
    f.newsId === res.news_id
      ? {
          ...f,
          analysis: {
            strength: res.strength,
            label: res.label,
            commentary: res.commentary,
            rampEndTick: rampEndTick(currentTick, res.ramp_remaining),
            offline: res.offline,
          },
        }
      : f,
  )
}

/** since 커서. 아직 하나도 받지 않았으면 -1. */
export function maxNewsId(feed: FeedItem[]): number {
  return feed.reduce((max, f) => (f.newsId > max ? f.newsId : max), -1)
}

/** 순서가 뒤바뀐 폴링 응답이 새 상태를 덮는 것을 막는다. */
export function isFresher(lastSeq: number, seq: number): boolean {
  return seq > lastSeq
}

export function positionRows(
  snap: Snapshot,
  positions: Record<string, Position>,
): PositionRow[] {
  return snap.stocks
    .filter((s) => s.held > 0)
    .map((s) => {
      const pos = positions[s.symbol]
      const known = pos !== undefined && pos.qty === s.held && pos.avg !== 0
      return {
        symbol: s.symbol,
        name: s.name,
        held: s.held,
        price: s.price,
        avg: known ? (pos?.avg ?? null) : null,
        unrealized: unrealizedFor(pos, s.held, s.price),
      }
    })
}

export function applyTradeToSnapshot(snap: Snapshot, res: TradeResult): Snapshot {
  return { ...snap, cash: res.cash, equity: res.equity }
}

export function applyAnalyzeToSnapshot(snap: Snapshot, res: AnalyzeResult): Snapshot {
  return { ...snap, analyses_left: res.analyses_left }
}

/**
 * 잔여 횟수는 응답을 그대로 쓴다. 같은 종목을 다시 사면 서버가 깎지 않으므로
 * 프론트가 따로 세면 어긋난다.
 */
export function applyCompanyAnalysisToSnapshot(
  snap: Snapshot,
  res: CompanyAnalysisResult,
): Snapshot {
  return {
    ...snap,
    company_analyses_left: res.company_analyses_left,
    stocks: snap.stocks.map((s) =>
      s.symbol === res.symbol ? { ...s, fundamentals_analyzed: true } : s,
    ),
  }
}

/**
 * 보수는 **더하지 않는다.** 지급은 잠금이 끝난 뒤 다음 요청에서 이뤄지므로
 * 실제 현금 증가는 폴링 스냅샷으로 들어온다.
 */
export function applyGrindToSnapshot(snap: Snapshot, res: GrindResult): Snapshot {
  return {
    ...snap,
    locked: true,
    lock_remaining: res.lock_remaining,
    grind_count: res.grind_count,
  }
}
