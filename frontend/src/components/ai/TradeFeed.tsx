import { won } from '../../lib/format'
import { useDerivedStore } from '../../store/derivedStore'

/**
 * 누가 무엇에 들어갔는지. **숫자가 아니라 신원을 읽는 자리다** —
 * 잘 낚이는 참가자만 들어간 기사는 함정일 확률이 높다 (api.md §04).
 */
export function TradeFeed() {
  const trades = useDerivedStore((s) => s.trades)

  return (
    <section className="panel">
      <h2>체결</h2>
      {trades.length === 0 ? (
        <p className="empty">아직 체결이 없습니다.</p>
      ) : (
        <ul className="trades">
          {trades.map((t) => (
            <li key={t.seq} className={t.actor === 'you' ? 'trade me' : 'trade'}>
              <span className="trade-tick num">{`${t.tick}s`}</span>
              <span data-testid="trade-actor" className="trade-actor">
                {t.actor === 'you' ? '나' : t.actor}
              </span>
              <span className={`trade-side ${t.side === 'buy' ? 'up' : 'down'}`}>
                {t.side === 'buy' ? '매수' : '매도'}
              </span>
              <span className="trade-sym">{t.name}</span>
              <span className="trade-qty num">{`${t.qty}주`}</span>
              <span className="trade-price num">{won(t.price)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
