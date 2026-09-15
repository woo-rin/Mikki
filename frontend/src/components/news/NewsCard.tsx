import { useState } from 'react'
import { ApiError } from '../../api/client'
import { analyze } from '../../api/endpoints'
import type { Strength } from '../../api/types'
import { ageAt, rampRemainingAt } from '../../lib/derive'
import { useDerivedStore } from '../../store/derivedStore'
import { tradesForNews } from '../../store/merge'
import { useGameStore } from '../../store/gameStore'
import type { FeedItem } from '../../store/merge'
import { useUiStore } from '../../store/uiStore'

/** 판정을 산 기사에만 쓴다. 미분석 기사에는 어떤 방향 색도 주지 않는다. */
function toneOf(strength: Strength): string {
  if (strength === 'up_strong' || strength === 'up_weak') return 'up'
  if (strength === 'down_strong' || strength === 'down_weak') return 'down'
  return ''
}

export function NewsCard({ item, tick }: { item: FeedItem; tick: number }) {
  const sessionId = useGameStore((s) => s.sessionId)
  const analysesLeft = useGameStore((s) => s.snapshot?.analyses_left ?? 0)
  const pushToast = useUiStore((s) => s.pushToast)
  const trades = useDerivedStore((s) => s.trades)
  const [busy, setBusy] = useState(false)

  const age = ageAt(tick, item.publishTick)
  const a = item.analysis
  // 누가 들어갔는지가 그 자체로 단서다 — 잘 낚이는 참가자만 들어간 기사는
  // 함정일 확률이 높다. 인과를 주장하지는 않는다 (램프 길이가 비공개다).
  const reactions = tradesForNews(trades, item.symbol, item.publishTick)

  async function run(): Promise<void> {
    if (!sessionId) return
    setBusy(true)
    try {
      const res = await analyze(sessionId, item.newsId)
      useGameStore.getState().applyAnalyze(res)
      // 램프의 기준점은 응답을 받은 순간의 최신 tick 이다.
      const now = useGameStore.getState().snapshot?.tick ?? tick
      useDerivedStore.getState().recordAnalysis(res, now)
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : '분석에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="news" data-testid={`news-${item.newsId}`}>
      <div className="news-head">
        <span className="news-sym">{item.name}</span>
        <span className="news-age num">{`${age}초 전`}</span>
        {item.offline && <span className="badge">로컬</span>}
      </div>

      <h3>{item.headline}</h3>
      <p className="news-body">{item.body}</p>

      {reactions.length > 0 && (
        <p className="reactions">
          <span className="reactions-key">기사 이후</span>
          {reactions.map((t) => (
            <span key={t.seq} className="reaction">
              {`${t.actor} ${t.side === 'buy' ? '매수' : '매도'} ${t.qty}`}
            </span>
          ))}
        </p>
      )}

      {a === null ? (
        <div className="news-foot">
          <span className="badge muted">미분석</span>
          <button type="button" disabled={busy || analysesLeft === 0} onClick={() => void run()}>
            {busy ? '분석 중…' : '분석'}
          </button>
        </div>
      ) : (
        <div className="verdict">
          <div className="verdict-head">
            <strong className={toneOf(a.strength)}>{a.label}</strong>
            <span className="num">
              {a.rampEndTick === null
                ? '이미 반영됨'
                : `남은 창 ${rampRemainingAt(tick, a.rampEndTick)}초`}
            </span>
            {a.offline && <span className="badge">로컬</span>}
          </div>
          <p className="commentary">{a.commentary}</p>
        </div>
      )}
    </article>
  )
}
