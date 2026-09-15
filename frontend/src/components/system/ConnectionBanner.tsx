import { useGameStore } from '../../store/gameStore'

export function ConnectionBanner() {
  const connected = useGameStore((s) => s.connected)
  if (connected) return null
  return (
    <div className="banner" role="status">
      연결 끊김 — 재시도 중
    </div>
  )
}
