import { useState } from 'react'
import { ApiError } from '../../api/client'
import { companyAnalysis } from '../../api/endpoints'
import type { Valuation } from '../../api/types'
import { eok, pct, won } from '../../lib/format'
import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import { useUiStore } from '../../store/uiStore'

/** 가격이 적정가보다 위면 up, 아래면 down. 등급 문자열은 서버의 label 을 그대로 쓴다. */
function toneOf(valuation: Valuation): string {
  if (valuation === 'severely_overvalued' || valuation === 'overvalued') return 'up'
  if (valuation === 'severely_undervalued' || valuation === 'undervalued') return 'down'
  return ''
}

export function FundamentalsPanel() {
  const snap = useGameStore((s) => s.snapshot)
  const sessionId = useGameStore((s) => s.sessionId)
  const selected = useUiStore((s) => s.selected)
  const pushToast = useUiStore((s) => s.pushToast)
  const stored = useDerivedStore((s) => s.valuations[selected])
  const [busy, setBusy] = useState(false)

  const stock = snap?.stocks.find((x) => x.symbol === selected)
  if (!snap || !stock || !sessionId) return null

  const left = snap.company_analyses_left

  // "이번 라운드에 샀는가" 의 권위는 서버다. 라운드가 넘어가면 서버가 이 값을 리셋하므로
  // 클라이언트 보관분이 남아 있어도 지난 라운드의 적정가를 보여주지 않는다.
  // 새로고침하면 반대가 된다 — 서버는 샀다고 하는데 보관분이 없다. 그때는 다시 조회하면
  // 되고, 같은 종목 재조회는 횟수를 쓰지 않는다.
  const found = stock.fundamentals_analyzed ? stored : undefined

  async function buy(): Promise<void> {
    if (!stock || !sessionId) return
    setBusy(true)
    try {
      const res = await companyAnalysis(sessionId, stock.symbol)
      // 잔여 횟수는 응답을 그대로 쓴다 — 같은 종목 재조회는 서버가 깎지 않는다.
      useGameStore.getState().applyCompanyAnalysis(res)
      useDerivedStore.getState().recordValuation(res)
    } catch (err) {
      pushToast(err instanceof ApiError ? err.message : '기업분석에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <h2>{`기업분석 · ${stock.name}`}</h2>

      <dl className="kv">
        <dt>남은 기업분석</dt>
        <dd className="num">{`${left} / 2`}</dd>
      </dl>

      {found === undefined ? (
        <>
          <p className="empty">적정가는 사야 보입니다. 재무는 라운드마다 바뀝니다.</p>
          <button
            type="button"
            className="primary"
            disabled={busy || left === 0}
            onClick={() => void buy()}
          >
            기업분석
          </button>
        </>
      ) : (
        <>
          <div className="verdict-head">
            <strong className={toneOf(found.valuation)}>{found.label}</strong>
            <span className={`num ${toneOf(found.valuation)}`}>{pct(found.gap_pct)}</span>
            {found.offline && <span className="badge">로컬</span>}
          </div>

          <dl className="kv">
            <dt>적정가</dt>
            <dd className="num">{won(found.fair_value)}</dd>
            <dt>분석 시점 가격</dt>
            <dd className="num">{won(found.current_price)}</dd>
          </dl>

          <table className="grid financials">
            <tbody>
              <tr>
                <th>분기</th>
                <td className="num">{found.financials.quarter}</td>
              </tr>
              <tr>
                <th>매출</th>
                <td className="num">{eok(found.financials.revenue)}</td>
              </tr>
              <tr>
                <th>영업이익</th>
                <td className="num">{eok(found.financials.operating_income)}</td>
              </tr>
              <tr>
                <th>순이익</th>
                <td className="num">{eok(found.financials.net_income)}</td>
              </tr>
              <tr>
                <th>EPS</th>
                <td className="num">{won(found.financials.eps)}</td>
              </tr>
              <tr>
                <th>PER</th>
                <td className="num">
                  {found.financials.per === null ? '—' : found.financials.per}
                </td>
              </tr>
              <tr>
                <th>부채비율</th>
                <td className="num">{`${found.financials.debt_ratio}%`}</td>
              </tr>
            </tbody>
          </table>

          {found.financials.per === null && (
            <p className="hint">적자 분기라 PER 대신 매출 기준(PSR)으로 적정가를 냈습니다.</p>
          )}

          <p className="commentary">{found.commentary}</p>

          <button type="button" disabled={busy} onClick={() => void buy()}>
            다시 조회
          </button>
          <p className="hint">같은 종목 재조회는 횟수를 쓰지 않습니다.</p>
        </>
      )}
    </section>
  )
}
