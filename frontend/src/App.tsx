import './App.css'
import { AccountPanel } from './components/account/AccountPanel'
import { GrindPanel } from './components/account/GrindPanel'
import { Positions } from './components/account/Positions'
import { RoundPanel } from './components/account/RoundPanel'
import { PriceChart } from './components/chart/PriceChart'
import { FundamentalsPanel } from './components/fundamentals/FundamentalsPanel'
import { NewsFeed } from './components/news/NewsFeed'
import { OrderTicket } from './components/order/OrderTicket'
import { ConnectionBanner } from './components/system/ConnectionBanner'
import { SessionGate } from './components/system/SessionGate'
import { Tabs } from './components/system/Tabs'
import { Toasts } from './components/system/Toasts'
import { TopBar } from './components/system/TopBar'
import { TickerBar } from './components/watchlist/TickerBar'
import { useGameLoop } from './hooks/useGameLoop'
import { useGameStore } from './store/gameStore'
import { useUiStore } from './store/uiStore'

/** 좌측은 한 번에 하나만 본다. */
function TabPane() {
  const tab = useUiStore((s) => s.tab)
  if (tab === 'fundamentals') return <FundamentalsPanel />
  if (tab === 'positions') {
    return (
      <>
        <AccountPanel />
        <RoundPanel />
        <Positions />
      </>
    )
  }
  return <NewsFeed />
}

export function Board() {
  // 폴링이 시장을 굴린다. 껍데기에 두어야 탭을 옮겨도 안 멈춘다.
  useGameLoop()
  const bankrupt = useGameStore((s) => s.snapshot?.bankrupt ?? false)

  return (
    <div className="board">
      <TopBar />
      <TickerBar />
      <div className="cols">
        <aside className="left">
          <Tabs />
          <TabPane />
        </aside>
        <main className="right">
          <PriceChart />
          {/* 파산하면 주문 자리를 노가다가 대체한다. 어차피 주문을 못 하고,
              탭에 묻히면 복귀 수단을 못 찾는다. */}
          {bankrupt ? <GrindPanel /> : <OrderTicket />}
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <>
      <ConnectionBanner />
      <SessionGate><Board /></SessionGate>
      <Toasts />
    </>
  )
}
