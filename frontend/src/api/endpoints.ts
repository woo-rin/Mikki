import { getJson, postJson } from './client'
import type {
  AnalyzeResult, CompanyAnalysisResult, GrindResult, Snapshot, Symbol_, TradeResult,
} from './types'

export function newGame(): Promise<Snapshot> {
  return postJson<Snapshot>('/api/game', {})
}

/**
 * since 보다 큰 news_id, tradesSince 보다 큰 체결 seq 만 받는다. 아직 없으면 -1.
 * 둘 다 증분이므로 클라이언트가 누적한다.
 */
export function getState(
  sessionId: string,
  since: number,
  tradesSince = -1,
  boardSince = -1,
): Promise<Snapshot> {
  const q = new URLSearchParams({
    session_id: sessionId,
    since: String(since),
    trades_since: String(tradesSince),
    board_since: String(boardSince),
  })
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

/**
 * 라운드당 2회. 같은 종목을 다시 부르면 서버가 횟수를 깎지 않는다 —
 * 재무는 라운드 내내 바뀌지 않으므로 같은 값을 두 번 파는 것은 함정이기 때문이다.
 */
export function companyAnalysis(
  sessionId: string,
  symbol: Symbol_,
): Promise<CompanyAnalysisResult> {
  return postJson<CompanyAnalysisResult>('/api/company-analysis', {
    session_id: sessionId,
    symbol,
  })
}

export function grind(sessionId: string): Promise<GrindResult> {
  return postJson<GrindResult>('/api/grind', { session_id: sessionId })
}
