import { useDerivedStore } from '../../store/derivedStore'

/**
 * 세 번째 정보 레이어. 뉴스가 믿을 수 없는 기사라면 여기는 믿을 수 없는 군중이다.
 *
 * **강세·약세를 색으로 구분하지 않는다.** 색을 칠하면 문장을 읽지 않고 색만 세게
 * 되고, 그러면 아홉 명의 판단이 공짜가 되어 AI 분석 5회가 무의미해진다.
 * 누가 잘 맞히는지는 이름을 기억하며 몇 판에 걸쳐 배우는 것이다.
 */
export function BoardFeed() {
  const posts = useDerivedStore((s) => s.posts)

  return (
    <section className="panel">
      <h2>종토방</h2>
      {posts.length === 0 ? (
        <p className="empty">아직 조용합니다.</p>
      ) : (
        <ul className="board">
          {posts.map((p) => (
            <li key={p.post_id} className="post">
              <div className="post-head">
                <span data-testid="post-author" className="post-author">{p.author}</span>
                <span className="post-sym">{p.name}</span>
                <span className="post-age num">{`${p.age_seconds}초 전`}</span>
                {p.offline && <span className="badge">로컬</span>}
              </div>
              <p className="post-body">{p.body}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
