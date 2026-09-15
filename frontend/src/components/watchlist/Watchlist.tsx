import { pct, won } from '../../lib/format'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'

export function Watchlist() {
  const stocks = useGameStore((s) => s.snapshot?.stocks)
  const selected = useUiStore((s) => s.selected)
  const select = useUiStore((s) => s.select)
  if (!stocks) return null

  return (
    <section className="panel">
      <h2>종목</h2>
      <table className="grid watchlist">
        <thead>
          <tr><th>종목</th><th>현재가</th><th>등락</th><th>보유</th></tr>
        </thead>
        <tbody>
          {stocks.map((s) => (
            <tr key={s.symbol} className={s.symbol === selected ? 'selected' : undefined}>
              <td>
                <button type="button" className="row-pick" onClick={() => select(s.symbol)}>
                  <span className="name">{s.name}</span>
                  <span className="sector">{s.sector}</span>
                </button>
              </td>
              <td className="num">{won(s.price)}</td>
              <td className={`num ${s.change_pct >= 0 ? 'up' : 'down'}`}>{pct(s.change_pct)}</td>
              <td className="num">{s.held > 0 ? s.held : '·'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
