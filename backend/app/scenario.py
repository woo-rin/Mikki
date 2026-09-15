"""라운드와 시드로부터 시나리오 배분표를 만든다. 밸런스 규칙을 소유한다."""
import random

from app import config
from app.models import NewsPlan


def honest_ratio(stage: int) -> float:
    """단계가 오를수록 정직 뉴스 비율이 내려가고, 하한에서 멈춘다.

    라운드가 사라지면서 단계의 뜻이 바뀌었다 — 이제 뉴스 배치 번호다.
    한 배치가 20건이므로 긴 경주일수록 함정이 늘어난다.
    """
    ratio = config.HONEST_RATIO_START - config.HONEST_RATIO_STEP * (stage - 1)
    return max(config.HONEST_RATIO_FLOOR, ratio)


def allocate(total: int, stage: int) -> dict[str, int]:
    """total 건을 정직/과장/역방향으로 쪼갠다. 합은 항상 total 이다."""
    honest = round(total * honest_ratio(stage))
    rest = total - honest
    shares = config.EXAGGERATED_SHARE + config.REVERSED_SHARE
    exaggerated = round(rest * config.EXAGGERATED_SHARE / shares)
    return {
        "honest": honest,
        "exaggerated": exaggerated,
        "reversed": rest - exaggerated,
    }


def _impact(kind: str, surface_tone: str, rng: random.Random) -> float:
    lo, hi = config.IMPACT_RANGES[kind]
    magnitude = rng.uniform(lo, hi)
    tone_is_up = surface_tone == "positive"
    # 역방향은 표면 톤과 반대로 움직인다. 그것이 함정의 정의다.
    goes_up = (not tone_is_up) if kind == "reversed" else tone_is_up
    return magnitude if goes_up else -magnitude


def build_plans(
    total: int,
    stage: int,
    rng: random.Random,
    first_news_id: int,
    first_tick: int,
) -> list[NewsPlan]:
    """확정된 뉴스 계획 목록. 등장 시각까지 여기서 정한다."""
    kinds: list[str] = []
    for kind, count in allocate(total, stage).items():
        kinds.extend([kind] * count)
    rng.shuffle(kinds)

    symbols = list(config.STOCKS)
    interval_lo, interval_hi = config.NEWS_INTERVAL_RANGE
    ramp_lo, ramp_hi = config.RAMP_SECONDS_RANGE

    plans: list[NewsPlan] = []
    tick = first_tick
    for offset, kind in enumerate(kinds):
        tick += rng.randint(interval_lo, interval_hi)
        surface_tone = rng.choice(("positive", "negative"))
        plans.append(
            NewsPlan(
                news_id=first_news_id + offset,
                symbol=rng.choice(symbols),
                surface_tone=surface_tone,
                kind=kind,
                impact=_impact(kind, surface_tone, rng),
                ramp_seconds=rng.randint(ramp_lo, ramp_hi),
                publish_tick=tick,
            )
        )
    return plans
