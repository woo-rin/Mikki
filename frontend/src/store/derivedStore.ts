import { create } from 'zustand'
import type { AnalyzeResult, CompanyAnalysisResult, Snapshot } from '../api/types'
import type { TradeRow } from '../api/types'
import { type FeedItem, appendTrades, attachAnalysis, upsertNews } from './merge'

/**
 * 새로고침하면 사라지는 것들만 담는다.
 * 가격 이력과 평단은 여기 없다 — 서버가 stocks[].history 와 avg_cost 로 준다 (api.md §6).
 */
interface DerivedState {
  feed: FeedItem[]
  /** 체결은 증분으로 온다(trades_since). 누적은 여기서만 한다. */
  trades: TradeRow[]
  /** 산 종목의 적정가와 등급. 스냅샷에 없으므로 여기서만 산다. */
  valuations: Record<string, CompanyAnalysisResult>
  /** 세션이 바뀐 것을 알아보기 위한 표식 */
  sessionId: string | null

  record: (snap: Snapshot) => void
  recordAnalysis: (res: AnalyzeResult, tick: number) => void
  recordValuation: (res: CompanyAnalysisResult) => void
  reset: () => void
}

export const useDerivedStore = create<DerivedState>((set) => ({
  feed: [],
  trades: [],
  valuations: {},
  sessionId: null,

  record: (snap) =>
    set((s) => {
      // 판이 바뀌면 산 적정가는 다른 게임의 것이다. 라운드가 사라졌으므로
      // 초기화 시점은 새 세션뿐이다.
      const rolled = s.sessionId !== null && s.sessionId !== snap.session_id
      return {
        feed: rolled ? upsertNews([], snap) : upsertNews(s.feed, snap),
        trades: rolled ? snap.trades : appendTrades(s.trades, snap.trades),
        valuations: rolled ? {} : s.valuations,
        sessionId: snap.session_id,
      }
    }),

  recordAnalysis: (res, tick) => set((s) => ({ feed: attachAnalysis(s.feed, res, tick) })),

  recordValuation: (res) =>
    set((s) => ({ valuations: { ...s.valuations, [res.symbol]: res } })),

  reset: () => set({ feed: [], trades: [], valuations: {}, sessionId: null }),
}))
