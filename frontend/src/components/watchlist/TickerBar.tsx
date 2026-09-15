import { pct, won } from '../../lib/format'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'

/**
 * 종목 선택은 항상 보여야 한다 — 차트·주문·기업분석이 전부 선택된 종목 기준이다.
 * 세로 테이블을 가로로 눕혀 공간을 덜 먹게 한다.
 */
/**
 * 평소 대비 몇 배인가. 평소 수준이면 null — 늘 띄우면 노이즈가 되어 아무도 안 본다.
 * 거래가 없던 종목(volume_avg 0)에서 0 으로 나누지 않는다.
 */
const SURGE_MIN = 2

function surge(volume: number, avg: number): string | null {
  if (avg <= 0 || volume <= 0) return null
  const ratio = volume / avg
  return ratio >= SURGE_MIN ? ratio.toFixed(1) : null
}

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
          {surge(s.volume, s.volume_avg) && (
            <span className="tick-vol num">{`${surge(s.volume, s.volume_avg)}배`}</span>
          )}
        </button>
      ))}
    </div>
  )
}
