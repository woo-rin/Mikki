import type { Tab } from '../../store/uiStore'
import { useUiStore } from '../../store/uiStore'

const TABS: ReadonlyArray<{ id: Tab; label: string }> = [
  { id: 'news', label: '뉴스' },
  { id: 'board', label: '종토방' },
  { id: 'fundamentals', label: '기업' },
  { id: 'participants', label: '참가자' },
  { id: 'positions', label: '내 포지션' },
]

export function Tabs() {
  const tab = useUiStore((s) => s.tab)
  const setTab = useUiStore((s) => s.setTab)

  return (
    <div className="tabs" role="tablist">
      {TABS.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          role="tab"
          aria-selected={tab === id}
          className={tab === id ? 'tab on' : 'tab'}
          onClick={() => setTab(id)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
