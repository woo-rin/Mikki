import { won } from '../../lib/format'
import { useGameStore } from '../../store/gameStore'

/**
 * 나를 AI 와 같은 표에 끼워 총자산으로 줄 세운다.
 *
 * 보유 종목은 서버가 주지 않는다 — 체결 피드를 성실히 읽어 재구성하는 것이
 * 주의 깊은 플레이어의 정당한 우위다 (api.md §04).
 */
export function Leaderboard() {
  const snap = useGameStore((s) => s.snapshot)
  if (!snap) return null

  const rows = [
    ...snap.ai.map((a) => ({ id: a.id, name: a.name, cash: a.cash, equity: a.equity, me: false })),
    { id: 'you', name: '나', cash: snap.cash, equity: snap.equity, me: true },
  ].sort((a, b) => b.equity - a.equity)

  return (
    <section className="panel">
      <h2>순위</h2>
      <table className="grid">
        <thead>
          <tr><th>#</th><th>참가자</th><th>총자산</th><th>현금</th></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id} className={r.me ? 'selected' : undefined}>
              <td className="num">{i + 1}</td>
              <td data-testid="ai-name">{r.name}</td>
              <td className="num">{won(r.equity)}</td>
              <td className="num">{won(r.cash)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
