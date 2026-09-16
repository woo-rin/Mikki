import './App.css'
import { AccountPanel } from './components/account/AccountPanel'
import { Leaderboard } from './components/ai/Leaderboard'
import { BoardFeed } from './components/board/BoardFeed'
import { TradeFeed } from './components/ai/TradeFeed'
import { GrindOverlay } from './components/account/GrindOverlay'
import { GrindPanel } from './components/account/GrindPanel'
import { Positions } from './components/account/Positions'
import { PriceChart } from './components/chart/PriceChart'
import { RaceResult } from './components/race/RaceResult'
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
function TabPane({ bankrupt }: { bankrupt: boolean }) {
  const tab = useUiStore((s) => s.tab)
  if (tab === 'board') return <BoardFeed />
  if (tab === 'fundamentals') return <FundamentalsPanel />
  if (tab === 'participants') {
    return (
      <>
        <Leaderboard />
        <TradeFeed />
      </>
    )
  }
  if (tab === 'positions') {
    return (
      <>
        <AccountPanel />
        <Positions />
        {/* 평소에는 여기 조용히 있는다. 파산하면 우측으로 끌려 나간다. */}
        {!bankrupt && <GrindPanel />}
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
          <TabPane bankrupt={bankrupt} />
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
      {/* 판 위에 덮는다. 블러 너머로 시장이 계속 움직이는 것이 보여야 한다. */}
      <GrindOverlay />
      {/* 경주가 끝나면 그 위를 덮는다. */}
      <RaceResult />
      <Toasts />
    </>
  )
}
