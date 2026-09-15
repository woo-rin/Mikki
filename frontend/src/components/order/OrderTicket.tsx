import { useState } from 'react'
import { ApiError } from '../../api/client'
import { trade } from '../../api/endpoints'
import { won } from '../../lib/format'
import { fee, maxBuyQty } from '../../lib/money'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'

export function OrderTicket() {
  const snap = useGameStore((s) => s.snapshot)
  const sessionId = useGameStore((s) => s.sessionId)
  const selected = useUiStore((s) => s.selected)
  const pushToast = useUiStore((s) => s.pushToast)

  const [side, setSide] = useState<'buy' | 'sell'>('buy')
  const [qty, setQty] = useState(1)
  const [busy, setBusy] = useState(false)

  const stock = snap?.stocks.find((s) => s.symbol === selected)
  if (!snap || !stock || !sessionId) return null

  const limit = side === 'buy' ? maxBuyQty(snap.cash, stock.price) : stock.held
  const clamped = Math.max(0, Math.min(qty, limit))
  const gross = stock.price * clamped
  const charge = fee(stock.price, clamped)
  const blocked = snap.locked || busy || clamped < 1

  async function submit(): Promise<void> {
    if (!stock || !sessionId) return
    const quoted = stock.price
    setBusy(true)
    try {
      const res = await trade(sessionId, stock.symbol, side, clamped)
      // 낙관적 UI 금지 — 화면은 이 응답만 따른다.
      useGameStore.getState().applyTrade(res)
      // 평단은 서버가 들고 있다. 다음 폴링의 avg_cost 로 들어온다.
      const gap = res.price - quoted
      const tail = gap === 0 ? '' : ` (표시가와 ${won(Math.abs(gap))} 차이)`
      pushToast(
        `${res.side === 'buy' ? '매수' : '매도'} ${res.qty}주 · 체결가 ${won(res.price)} · 수수료 ${won(res.fee)}${tail}`,
        'info',
      )
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : '주문에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <h2>{`주문 · ${stock.name}`}</h2>

      <div className="sides">
        <button type="button" className={side === 'buy' ? 'on' : ''} onClick={() => setSide('buy')}>
          매수 쪽
        </button>
        <button type="button" className={side === 'sell' ? 'on' : ''} onClick={() => setSide('sell')}>
          매도 쪽
        </button>
      </div>

      <div className="qty">
        <label htmlFor="order-qty">수량</label>
        <button type="button" aria-label="한 주 줄이기" onClick={() => setQty((q) => Math.max(1, q - 1))}>
          −
        </button>
        <input
          id="order-qty"
          type="number"
          min={1}
          max={Math.max(1, limit)}
          step={1}
          value={qty}
          onChange={(e) => setQty(Math.floor(Number(e.target.value) || 1))}
        />
        <button type="button" aria-label="한 주 늘리기" onClick={() => setQty((q) => Math.min(limit, q + 1))}>
          +
        </button>
        <button type="button" onClick={() => setQty(Math.max(1, limit))}>최대</button>
      </div>

      <dl className="kv">
        <dt>예상 금액</dt><dd className="num">{won(gross)}</dd>
        <dt>예상 수수료</dt><dd className="num">{won(charge)}</dd>
        <dt>{side === 'buy' ? '살 수 있는 최대' : '보유'}</dt><dd className="num">{`${limit}주`}</dd>
      </dl>

      <p className="hint">체결가는 서버가 정합니다. 표시가와 다를 수 있습니다.</p>

      <button type="button" className="primary" disabled={blocked} onClick={() => void submit()}>
        {side === 'buy' ? '매수' : '매도'}
      </button>
      {snap.locked && <p className="hint">{`노가다 잠금 중입니다 — ${snap.lock_remaining}초`}</p>}
    </section>
  )
}
