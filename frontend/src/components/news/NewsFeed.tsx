import { useDerivedStore } from '../../store/derivedStore'
import { useGameStore } from '../../store/gameStore'
import { NewsCard } from './NewsCard'

export function NewsFeed() {
  const tick = useGameStore((s) => s.snapshot?.tick ?? 0)
  const feed = useDerivedStore((s) => s.feed)

  return (
    <section className="panel">
      <h2>뉴스</h2>
      {feed.length === 0 ? (
        // 시작 직후 빈 배열은 정상이다 (api.md §3). 오류로 다루지 않는다.
        <p className="empty">첫 기사를 기다리는 중…</p>
      ) : (
        <div className="feed">
          {feed.map((item) => (
            <NewsCard key={item.newsId} item={item} tick={tick} />
          ))}
        </div>
      )}
    </section>
  )
}
