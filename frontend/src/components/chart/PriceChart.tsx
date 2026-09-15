import { won } from '../../lib/format'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import { priceSeries } from '../../store/merge'
import { useUiStore } from '../../store/uiStore'

const W = 720
const H = 240
const PAD = 8

/** 판정을 산 기사에만 방향 색을 준다. */
function bandColor(strength: string): string {
  if (strength === 'up_strong' || strength === 'up_weak') return 'var(--up)'
  if (strength === 'down_strong' || strength === 'down_weak') return 'var(--down)'
  return 'var(--ink-3)'
}

export function PriceChart() {
  const selected = useUiStore((s) => s.selected)
  const snap = useGameStore((s) => s.snapshot)
  const feed = useDerivedStore((s) => s.feed)

  const stock = snap?.stocks.find((x) => x.symbol === selected)
  if (!snap || !stock) return null

  // 서버가 들고 있는 60틱이다. 새로고침해도 남는다.
  const series = priceSeries(stock, snap.tick)

  const first = series[0]
  const last = series[series.length - 1]
  if (series.length < 2 || first === undefined || last === undefined) {
    return (
      <section className="panel">
        <h2>{`${stock.name} · ${won(stock.price)}`}</h2>
        <p className="empty">이력을 쌓는 중…</p>
        <p className="hint">첫 tick 이 지나면 그려집니다.</p>
      </section>
    )
  }

  const t0 = first.tick
  const t1 = last.tick
  const span = Math.max(1, t1 - t0)
  const prices = series.map((p) => p.price)
  const lo = Math.min(...prices)
  const hi = Math.max(...prices)
  const range = Math.max(1, hi - lo)

  const x = (tick: number) => PAD + ((tick - t0) / span) * (W - PAD * 2)
  const y = (price: number) => PAD + (1 - (price - lo) / range) * (H - PAD * 2)

  const points = series.map((p) => `${x(p.tick).toFixed(1)},${y(p.price).toFixed(1)}`).join(' ')
  const marks = feed.filter(
    (f) => f.symbol === selected && f.publishTick >= t0 && f.publishTick <= t1,
  )

  return (
    <section className="panel">
      <h2>{`${stock.name} · ${won(stock.price)}`}</h2>
      <svg
        className="chart"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`${stock.name} 가격 추이`}
      >
        {marks.map((f) => {
          const end = f.analysis?.rampEndTick ?? null
          return (
            <g key={f.newsId}>
              {end !== null && f.analysis !== null && (
                <rect
                  data-testid={`band-${f.newsId}`}
                  x={x(f.publishTick)}
                  y={PAD}
                  width={Math.max(1, x(Math.min(end, t1)) - x(f.publishTick))}
                  height={H - PAD * 2}
                  fill={bandColor(f.analysis.strength)}
                  opacity={0.14}
                />
              )}
              <line
                data-testid={`marker-${f.newsId}`}
                x1={x(f.publishTick)}
                x2={x(f.publishTick)}
                y1={PAD}
                y2={H - PAD}
                stroke="var(--ink-3)"
                strokeWidth={1}
                strokeDasharray="3 3"
              />
            </g>
          )
        })}
        <polyline points={points} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
      </svg>
      <p className="hint">
        {`최근 ${series.length}틱 · 미분석 기사는 점선만, 분석한 기사만 남은 창을 칠합니다.`}
      </p>
    </section>
  )
}
