import './App.css'
import { AccountPanel } from './components/account/AccountPanel'
import { Positions } from './components/account/Positions'
import { ConnectionBanner } from './components/system/ConnectionBanner'
import { SessionGate } from './components/system/SessionGate'
import { Toasts } from './components/system/Toasts'
import { useGameLoop } from './hooks/useGameLoop'
import { useGameStore } from './store/gameStore'

function Board() {
  useGameLoop()
  const snap = useGameStore((s) => s.snapshot)

  return (
    <div className="board">
      <header className="topbar">
        <strong>미끼</strong>
        <span className="num">{`R${snap?.round_no ?? 1}`}</span>
        <span className="num">{`${snap?.tick ?? 0}s`}</span>
      </header>
      <div className="cols">
        <aside className="left">
          <AccountPanel />
          <Positions />
        </aside>
        <main className="right" />
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
