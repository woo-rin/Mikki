import { create } from 'zustand'
import type {
  AnalyzeResult, CompanyAnalysisResult, GrindResult, Snapshot, TradeResult,
} from '../api/types'
import {
  applyAnalyzeToSnapshot, applyCompanyAnalysisToSnapshot, applyGrindToSnapshot,
  applyTradeToSnapshot, isFresher,
} from './merge'

/** 서버가 준 것만 담는다. 판정을 다시 계산하지 않는다. */
interface GameState {
  sessionId: string | null
  snapshot: Snapshot | null
  lastSeq: number
  connected: boolean
  /** 서버 재시작 등으로 세션이 사라졌다. 전용 화면을 띄운다. */
  sessionGone: boolean

  setSession: (id: string | null) => void
  applySnapshot: (snap: Snapshot, seq: number) => void
  forceSnapshot: (snap: Snapshot) => void
  applyTrade: (res: TradeResult) => void
  applyAnalyze: (res: AnalyzeResult) => void
  applyCompanyAnalysis: (res: CompanyAnalysisResult) => void
  applyGrind: (res: GrindResult) => void
  setConnected: (v: boolean) => void
  setSessionGone: (v: boolean) => void
  reset: () => void
}

function initial() {
  return {
    sessionId: null,
    snapshot: null,
    lastSeq: -1,
    connected: true,
    sessionGone: false,
  }
}

export const useGameStore = create<GameState>((set) => ({
  ...initial(),

  setSession: (id) => set({ sessionId: id }),

  applySnapshot: (snap, seq) =>
    set((s) => (isFresher(s.lastSeq, seq) ? { snapshot: snap, lastSeq: seq } : {})),

  /** 시퀀스를 건드리지 않고 즉시 반영한다. 라운드 전환처럼 사용자가 일으킨 변화용. */
  forceSnapshot: (snap) => set({ snapshot: snap }),

  applyTrade: (res) =>
    set((s) => (s.snapshot ? { snapshot: applyTradeToSnapshot(s.snapshot, res) } : {})),

  applyAnalyze: (res) =>
    set((s) => (s.snapshot ? { snapshot: applyAnalyzeToSnapshot(s.snapshot, res) } : {})),

  applyCompanyAnalysis: (res) =>
    set((s) => (s.snapshot ? { snapshot: applyCompanyAnalysisToSnapshot(s.snapshot, res) } : {})),

  applyGrind: (res) =>
    set((s) => (s.snapshot ? { snapshot: applyGrindToSnapshot(s.snapshot, res) } : {})),

  setConnected: (v) => set({ connected: v }),
  setSessionGone: (v) => set({ sessionGone: v }),
  reset: () => set(initial()),
}))
