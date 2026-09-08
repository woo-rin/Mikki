"""Claude 없이 뉴스와 해설을 만든다.

키가 없든 네트워크가 끊기든 레이트리밋이든 정책 거절이든, 전부 이 경로로
떨어진다. 테스트도 여기만 쓴다 — Claude 를 한 번도 부르지 않는다.
"""
import random
from collections.abc import Sequence

from app import config
from app.models import NewsItem, NewsPlan

STRENGTH_LABELS: dict[str, str] = {
    "up_strong": "강한 상승",
    "up_weak": "약한 상승",
    "none": "무영향",
    "down_weak": "약한 하락",
    "down_strong": "강한 하락",
}

_POSITIVE_HEADLINES = (
    "{name}, 분기 실적 시장 기대치 상회",
    "{name}, 대형 공급계약 체결 소식",
    "{name} 신규 설비 조기 가동… 출하 확대 전망",
    "{name}, 해외 인증 절차 최종 통과",
    "{name} 주요 제품 단가 인상 반영",
)
_NEGATIVE_HEADLINES = (
    "{name}, 분기 실적 시장 기대치 하회",
    "{name} 주요 고객사 발주 축소 통보",
    "{name} 생산 라인 일시 중단… 출하 지연 우려",
    "{name}, 규제 당국 현장 점검 착수",
    "{name} 원가 부담 확대로 수익성 압박",
)

_POSITIVE_BODIES = (
    "회사는 {sector} 부문 수요 회복을 근거로 제시했다. 구체적인 수치는 공개하지 않았다.",
    "업계는 {sector} 업황 개선의 신호로 보고 있으나 지속성에는 유보적인 평가가 나온다.",
    "{sector} 업종 전반의 흐름과 맞물린 결과라는 해석이 나온다.",
)
_NEGATIVE_BODIES = (
    "회사는 {sector} 부문 수요 둔화를 원인으로 들었다. 구체적인 규모는 밝히지 않았다.",
    "업계는 {sector} 업황 조정 국면의 일부로 보고 있으나 폭을 두고는 의견이 갈린다.",
    "{sector} 업종 전반의 부담이 함께 작용했다는 평가가 나온다.",
)

_COMMENTARY = {
    "up_strong": "본문의 내용은 실적에 직접 반영될 재료다. 판정: {label}. 램프가 끝나기 전이라면 아직 먹을 몫이 남아 있다.",
    "up_weak": "재료는 맞지만 규모가 작다. 판정: {label}. 수수료를 감안하면 남는 몫이 크지 않다.",
    "none": "이미 알려진 내용의 재인용이거나 규모가 미미하다. 판정: {label}. 들어갈 이유가 없다.",
    "down_weak": "표면과 달리 실제 부담이 있다. 판정: {label}. 크지 않지만 방향은 아래다.",
    "down_strong": "표면의 톤과 실제 영향이 어긋난다. 판정: {label}. 지금 들어가면 정면으로 물린다.",
}


def strength_of(impact: float) -> str:
    """임팩트 절대값으로 5단계 등급을 매긴다. 원시 수치는 밖으로 내보내지 않는다."""
    magnitude = abs(impact)
    if magnitude < config.STRENGTH_WEAK_MIN:
        return "none"
    if magnitude >= config.STRENGTH_STRONG_MIN:
        return "up_strong" if impact > 0 else "down_strong"
    return "up_weak" if impact > 0 else "down_weak"


def write_news(plans: Sequence[NewsPlan], rng: random.Random) -> list[NewsItem]:
    """계획마다 문장을 채운다. 문장은 surface_tone 만 따르고 impact 는 보지 않는다."""
    items: list[NewsItem] = []
    for plan in plans:
        stock = config.STOCKS[plan.symbol]
        positive = plan.surface_tone == "positive"
        headlines = _POSITIVE_HEADLINES if positive else _NEGATIVE_HEADLINES
        bodies = _POSITIVE_BODIES if positive else _NEGATIVE_BODIES
        items.append(
            NewsItem(
                plan=plan,
                headline=rng.choice(headlines).format(name=stock.name),
                body=rng.choice(bodies).format(sector=stock.sector),
                offline=True,
            )
        )
    return items


def write_commentary(item: NewsItem) -> str:
    """확정된 등급을 사람 말로 옮긴다. 판정은 여기서 다시 하지 않는다."""
    strength = strength_of(item.plan.impact)
    return _COMMENTARY[strength].format(label=STRENGTH_LABELS[strength])
