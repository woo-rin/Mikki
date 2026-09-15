import { useEffect, useState } from 'react'
import { useGameStore } from '../../store/gameStore'

export const SCENES = ['dig', 'carry', 'shovel'] as const
export type Scene = (typeof SCENES)[number]

/** 한 장면이 머무는 시간. 120초 잠금이면 예닐곱 바퀴 돈다. */
export const SCENE_MS = 6000

/** 곡괭이질 — 어깨를 축으로 팔과 도구가 함께 돌고, 내리친 순간에만 흙이 튄다. */
function Dig() {
  return (
    <>
      <circle cx="46" cy="24" r="9" className="worker-fill" />
      <line x1="46" y1="33" x2="46" y2="62" className="worker-ink" />
      <line x1="46" y1="62" x2="34" y2="88" className="worker-ink" />
      <line x1="46" y1="62" x2="60" y2="88" className="worker-ink" />
      <g className="swing" data-testid="tool-pick">
        <line x1="46" y1="40" x2="78" y2="30" className="worker-ink" />
        <line x1="78" y1="30" x2="96" y2="16" className="worker-tool" />
        <path d="M88 10 Q98 12 100 22" className="worker-tool" fill="none" />
      </g>
      <g className="dust">
        <circle cx="92" cy="84" r="2" />
        <circle cx="100" cy="80" r="1.5" />
        <circle cx="84" cy="80" r="1.5" />
      </g>
    </>
  )
}

/** 시멘트 나르기 — 포대를 어깨에 얹고 가로지른다. 다리가 번갈아 가고 몸이 위아래로. */
function Carry() {
  return (
    <g className="walk">
      <g className="bob">
        <rect x="52" y="14" width="26" height="15" rx="2"
          className="worker-tool-fill" data-testid="tool-bag" />
        <circle cx="42" cy="26" r="9" className="worker-fill" />
        <line x1="42" y1="35" x2="42" y2="62" className="worker-ink" />
        {/* 포대를 받친 팔 */}
        <line x1="42" y1="40" x2="56" y2="28" className="worker-ink" />
        <g className="leg-a"><line x1="42" y1="62" x2="42" y2="88" className="worker-ink" /></g>
        <g className="leg-b"><line x1="42" y1="62" x2="42" y2="88" className="worker-ink" /></g>
      </g>
    </g>
  )
}

/** 삽질 — 허리를 굽혀 퍼 올리고 옆으로 던진다. */
function Shovel() {
  return (
    <>
      <line x1="46" y1="62" x2="34" y2="88" className="worker-ink" />
      <line x1="46" y1="62" x2="60" y2="88" className="worker-ink" />
      <g className="scoop">
        <circle cx="46" cy="24" r="9" className="worker-fill" />
        <line x1="46" y1="33" x2="46" y2="62" className="worker-ink" />
        <g data-testid="tool-shovel">
          <line x1="46" y1="42" x2="84" y2="56" className="worker-tool" />
          <path d="M82 50 L96 54 L92 66 L79 61 Z" className="worker-tool-fill" />
        </g>
      </g>
      <g className="toss">
        <circle cx="70" cy="40" r="2" />
        <circle cx="78" cy="34" r="1.5" />
        <circle cx="62" cy="34" r="1.5" />
      </g>
    </>
  )
}

const RENDER: Record<Scene, () => React.JSX.Element> = {
  dig: Dig,
  carry: Carry,
  shovel: Shovel,
}

function Worker({ scene }: { scene: Scene }) {
  const Body = RENDER[scene]
  return (
    <svg
      className="worker"
      viewBox="0 0 120 100"
      data-testid="grind-scene"
      data-scene={scene}
      role="img"
      aria-hidden="true"
    >
      <line x1="10" y1="88" x2="110" y2="88" className="worker-ground" />
      <Body />
    </svg>
  )
}

/**
 * 잠금 중 화면 전체를 덮는다. **조작을 완전히 막는다** — 노가다는 자리를 비우는
 * 것이고, 돌아와 보니 시장이 변해 있는 것이 이 기능의 값이다.
 *
 * 블러 너머로 차트와 티커가 계속 움직이는 것이 보인다. 만질 수는 없고 보이기만
 * 한다 — "그동안에도 시장은 움직입니다" 를 문장이 아니라 그림으로 보여준다.
 *
 * 남은 초는 서버의 lock_remaining 을 그대로 쓴다. 클라이언트 타이머를 돌리면
 * 새로고침에 사라지고 서버와 어긋난다. 장면 순환만 클라이언트 타이머인데,
 * 그쪽은 장식이라 초기화돼도 상관없다.
 */
export function GrindOverlay() {
  const snap = useGameStore((s) => s.snapshot)
  const locked = snap?.locked ?? false
  // 인덱스가 아니라 장면 자체를 든다 — 배열 접근이 undefined 를 낼 여지를 없앤다.
  const [scene, setScene] = useState<Scene>('dig')

  useEffect(() => {
    if (!locked) return
    // 움직임을 줄여달라고 한 사람에게는 장면도 바꾸지 않는다.
    if (globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
    const id = setInterval(
      () => setScene((s) => SCENES[(SCENES.indexOf(s) + 1) % SCENES.length] ?? 'dig'),
      SCENE_MS,
    )
    return () => clearInterval(id)
  }, [locked])

  if (!snap || !locked) return null

  return (
    <div
      className="grind-overlay"
      data-testid="grind-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="노가다 중"
    >
      <div className="grind-card">
        <Worker scene={scene} />
        <p className="grind-title">노가다 중</p>
        <p className="grind-count" role="timer" aria-live="polite">
          <span className="grind-seconds num">{snap.lock_remaining}</span>
          <span className="grind-unit">초</span>
        </p>
        <p className="hint">{`${snap.grind_count}회차 · 끝나면 보수가 현금으로 들어옵니다.`}</p>
        <p className="hint">그동안에도 시장은 계속 움직입니다.</p>
      </div>
    </div>
  )
}
