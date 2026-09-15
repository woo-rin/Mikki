import { create } from 'zustand'
import type { AnalyzeResult, CompanyAnalysisResult, Snapshot, TradeResult } from '../api/types'
import { type Position, applyBuy, applySell, emptyPosition } from '../lib/money'
import { type FeedItem, attachAnalysis, upsertNews } from './merge'

/**
 * 새로고침하면 사라지는 것들만 담는다.
 * 가격 이력은 여기 없다 — 서버가 stocks[].history 로 준다 (api.md §6).
 */
interface DerivedState {
  feed: FeedItem[]
  positions: Record<string, Position>
  /** 산 종목의 적정가와 등급. 스냅샷에 없으므로 여기서만 산다. */
  valuations: Record<string, CompanyAnalysisResult>
  /** 라운드가 바뀐 것을 알아보기 위한 표식 */
  roundNo: number | null

  record: (snap: Snapshot) => void
  recordFill: (res: TradeResult) => void
  recordAnalysis: (res: AnalyzeResult, tick: number) => void
  recordValuation: (res: CompanyAnalysisResult) => void
  reset: () => void
}

export const useDerivedStore = create<DerivedState>((set) => ({
  feed: [],
  positions: {},
  valuations: {},
  roundNo: null,

  record: (snap) =>
    set((s) => {
      // 라운드 N 은 N분기 실적을 본다. 라운드가 넘어가면 적정가가 움직이므로
      // 지난 라운드에 산 값은 틀린 정보다. 서버도 fundamentals_analyzed 를 리셋한다.
      const rolled = s.roundNo !== null && s.roundNo !== snap.round_no
      return {
        feed: upsertNews(s.feed, snap),
        valuations: rolled ? {} : s.valuations,
        roundNo: snap.round_no,
      }
    }),

  recordFill: (res) =>
    set((s) => {
      const prev = s.positions[res.symbol] ?? emptyPosition()
      const next =
        res.side === 'buy'
          ? applyBuy(prev, res.price, res.qty)
          : applySell(prev, res.price, res.qty)
      return { positions: { ...s.positions, [res.symbol]: next } }
    }),

  recordAnalysis: (res, tick) => set((s) => ({ feed: attachAnalysis(s.feed, res, tick) })),

  recordValuation: (res) =>
    set((s) => ({ valuations: { ...s.valuations, [res.symbol]: res } })),

  reset: () => set({ feed: [], positions: {}, valuations: {}, roundNo: null }),
}))
