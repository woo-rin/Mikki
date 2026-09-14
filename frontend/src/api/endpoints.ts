import { getJson, postJson } from './client'
import type { AnalyzeResult, GrindResult, Snapshot, Symbol_, TradeResult } from './types'

export function newGame(): Promise<Snapshot> {
  return postJson<Snapshot>('/api/game', {})
}

/** since 보다 큰 news_id 만 받는다. 아직 하나도 없으면 -1. */
export function getState(sessionId: string, since: number): Promise<Snapshot> {
  const q = new URLSearchParams({ session_id: sessionId, since: String(since) })
  return getJson<Snapshot>(`/api/state?${q}`)
}

export function trade(
  sessionId: string,
  symbol: Symbol_,
  side: 'buy' | 'sell',
  qty: number,
): Promise<TradeResult> {
  return postJson<TradeResult>('/api/trade', { session_id: sessionId, symbol, side, qty })
}

export function analyze(sessionId: string, newsId: number): Promise<AnalyzeResult> {
  return postJson<AnalyzeResult>('/api/analyze', { session_id: sessionId, news_id: newsId })
}

export function grind(sessionId: string): Promise<GrindResult> {
  return postJson<GrindResult>('/api/grind', { session_id: sessionId })
}

export function nextRound(sessionId: string): Promise<Snapshot> {
  return postJson<Snapshot>('/api/next-round', { session_id: sessionId })
}
