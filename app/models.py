"""도메인 dataclass. 로직은 담지 않는다."""
from dataclasses import dataclass, field


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
