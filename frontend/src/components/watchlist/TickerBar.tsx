import { pct, won } from '../../lib/format'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'

/**
 * 종목 선택은 항상 보여야 한다 — 차트·주문·기업분석이 전부 선택된 종목 기준이다.
 * 세로 테이블을 가로로 눕혀 공간을 덜 먹게 한다.
 */
export function TickerBar() {
  const stocks = useGameStore((s) => s.snapshot?.stocks)
  const selected = useUiStore((s) => s.selected)
  const select = useUiStore((s) => s.select)
  if (!stocks) return null

  return (
    <div className="ticker">
      {stocks.map((s) => (
        <button
          key={s.symbol}
          type="button"
          aria-pressed={s.symbol === selected}
          className={s.symbol === selected ? 'tick on' : 'tick'}
          onClick={() => select(s.symbol)}
        >
          <span className="tick-name">{s.name}</span>
          <span className="tick-price num">{won(s.price)}</span>
          <span className={`tick-chg num ${s.change_pct >= 0 ? 'up' : 'down'}`}>
            {pct(s.change_pct)}
          </span>
          {s.held > 0 && <span className="tick-held num">{`${s.held}주`}</span>}
        </button>
      ))}
    </div>
  )
}
