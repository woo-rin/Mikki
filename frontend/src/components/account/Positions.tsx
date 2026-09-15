import { signedWon, won } from '../../lib/format'
import { useGameStore } from '../../store/gameStore'
import { positionRows } from '../../store/merge'

export function Positions() {
  const snap = useGameStore((s) => s.snapshot)
  if (!snap) return null

  const rows = positionRows(snap)
  if (rows.length === 0) {
    return (
      <section className="panel">
        <h2>보유</h2>
        <p className="empty">보유한 종목이 없습니다.</p>
      </section>
    )
  }

  return (
    <section className="panel">
      <h2>보유</h2>
      <table className="grid">
        <thead>
          <tr><th>종목</th><th>수량</th><th>평단</th><th>평가손익</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol}>
              <td>{r.name}</td>
              <td className="num">{r.held}</td>
              <td className="num">{r.avg === null ? '—' : won(r.avg)}</td>
              <td
                className={`num ${
                  r.unrealized === null ? '' : r.unrealized >= 0 ? 'up' : 'down'
                }`}
              >
                {signedWon(r.unrealized)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
