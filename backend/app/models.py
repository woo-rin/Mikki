"""도메인 dataclass. 로직은 담지 않는다."""
from dataclasses import dataclass


@dataclass(frozen=True)
class NewsPlan:
    """뉴스 한 건의 확정된 진실. impact 와 kind 는 절대 클라이언트로 내보내지 않는다."""
    news_id: int
    symbol: str
    surface_tone: str   # "positive" | "negative" — 플레이어가 읽는 톤
    kind: str           # "honest" | "exaggerated" | "reversed"
    impact: float       # 로그수익 총량, 부호 포함
    ramp_seconds: int
    publish_tick: int


@dataclass
class NewsItem:
    """문장이 채워진 뉴스."""
    plan: NewsPlan
    headline: str
    body: str
    analyzed: bool = False
    commentary: str = ""
    offline: bool = False   # 폴백으로 만들어졌으면 True


@dataclass(frozen=True)
class BoardPlan:
    """글 한 편의 확정된 사실. 문장이 붙기 전 단계다.

    bullish 는 절대 클라이언트로 내보내지 않는다 — 플래그로 주면 파싱 한 번에
    아홉 명의 판단이 공짜가 된다. 글의 톤으로만 드러나야 한다.
    """
    post_id: int
    news_id: int
    ai_index: int
    author: str
    symbol: str
    bullish: bool
    publish_tick: int


@dataclass
class BoardPost:
    """문장이 채워진 글."""
    plan: BoardPlan
    body: str
    offline: bool = False
