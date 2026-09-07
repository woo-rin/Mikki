"""뉴스 문장을 확보한다. Claude 를 아는 두 파일 중 하나.

시나리오 표는 이미 확정돼 있고 Claude 는 문장만 채운다. kind 와 impact 는
프롬프트에 넣지 않는다 — 실제 임팩트를 알면 역방향 기사에 우려 표현을
흘려서 문장만 읽고 낚시를 알아채게 된다.
"""
import logging
import random
from collections.abc import Sequence

from pydantic import BaseModel

from app import config, fallback
from app.models import NewsItem, NewsPlan

log = logging.getLogger(__name__)

SYSTEM = """당신은 한국 증권 뉴스 와이어의 기자입니다.
주어진 목록의 각 항목에 대해 헤드라인 한 줄과 본문 2~3문장을 씁니다.

규칙:
- 항목 순서를 그대로 유지하고, 항목 수와 같은 개수를 반환합니다.
- tone 이 positive 면 호재로 읽히는 기사, negative 면 악재로 읽히는 기사를 씁니다.
- 회사는 모두 가상 기업입니다. 실재하는 기업·인물·정책 사업의 이름을 쓰지 않습니다.
- 실제 통신사 기사처럼 건조하게 씁니다. 투자 권유 표현은 쓰지 않습니다.
- 기사의 톤은 주어진 tone 만 따릅니다. 그 밖의 판단을 문장에 담지 않습니다."""


class NewsText(BaseModel):
    headline: str
    body: str


class NewsBatch(BaseModel):
    items: list[NewsText]


def build_news_prompt(plans: Sequence[NewsPlan]) -> str:
    """회사·업종·톤만 넣는다. kind 와 impact 는 절대 넣지 않는다."""
    lines = [f"기사 {len(plans)}건을 써 주세요.", ""]
    for index, plan in enumerate(plans, start=1):
        stock = config.STOCKS[plan.symbol]
        lines.append(
            f"{index}. 회사={stock.name} / 업종={stock.sector} / tone={plan.surface_tone}"
        )
    return "\n".join(lines)


def fetch_news(
    plans: Sequence[NewsPlan],
    rng: random.Random,
    client,
) -> list[NewsItem]:
    """Claude 로 문장을 채우고, 어떤 실패든 로컬 템플릿으로 떨어진다."""
    if client is None or not plans:
        return fallback.write_news(plans, rng)

    try:
        response = client.messages.parse(
            model=config.MODEL,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": build_news_prompt(plans)}],
            thinking={"type": "adaptive"},
            output_config={"effort": config.NEWS_EFFORT},
            output_format=NewsBatch,
        )
        if getattr(response, "stop_reason", None) == "refusal":
            raise RuntimeError("모델이 요청을 거절했습니다.")
        batch = response.parsed_output
        if batch is None or len(batch.items) != len(plans):
            raise RuntimeError("기사 개수가 요청과 다릅니다.")
    except Exception:
        log.warning("뉴스 생성 실패 — 로컬 템플릿으로 대체합니다.", exc_info=True)
        return fallback.write_news(plans, rng)

    return [
        NewsItem(plan=plan, headline=text.headline, body=text.body, offline=False)
        for plan, text in zip(plans, batch.items)
    ]
