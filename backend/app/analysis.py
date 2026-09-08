"""분석 해설을 확보한다. Claude 를 아는 두 파일 중 하나.

뉴스 생성과 반대로 여기서는 정답을 전부 알려준다. Claude 에게 판정을
맡기면 확실한 정답이 매번 흔들리고 가격 엔진과 어긋난다. 등급은 서버가
확정하고 Claude 는 그 판정의 근거를 기사 안에서 찾아 설명만 한다.
"""
import logging

from pydantic import BaseModel

from app import config, fallback
from app.models import NewsItem

log = logging.getLogger(__name__)

SYSTEM = """당신은 증권사 애널리스트입니다.
기사와 확정된 판정을 받고, 그 판정이 왜 그런지를 기사 안의 표현을 근거로 설명합니다.

규칙:
- 판정은 이미 정해져 있습니다. 다시 판단하거나 뒤집지 않습니다.
- 기사에 실제로 있는 표현을 근거로 삼습니다.
- 2~3문장, 건조한 애널리스트 어투로 씁니다.
- 수치나 확률을 새로 만들어내지 않습니다. 투자 권유 표현은 쓰지 않습니다.
- 회사는 모두 가상 기업입니다. 실재하는 기업·인물·기관·정책 사업의 이름을 쓰지 않습니다.
  실존 여부가 불분명하면 지어내지 말고 일반명사로 씁니다."""


class Commentary(BaseModel):
    commentary: str


def build_analysis_prompt(item: NewsItem) -> str:
    """기사 전문과 확정된 등급 라벨을 넣는다. 원시 임팩트 수치는 넣지 않는다."""
    stock = config.STOCKS[item.plan.symbol]
    label = fallback.STRENGTH_LABELS[fallback.strength_of(item.plan.impact)]
    return (
        f"회사: {stock.name} ({stock.sector})\n"
        f"헤드라인: {item.headline}\n"
        f"본문: {item.body}\n\n"
        f"확정된 판정: {label}\n\n"
        "이 판정의 근거를 기사 안의 표현에서 찾아 설명해 주세요."
    )


def fetch_commentary(item: NewsItem, client) -> tuple[str, bool]:
    """(해설, offline 여부). 어떤 실패든 로컬 문장으로 떨어진다."""
    if client is None:
        return fallback.write_commentary(item), True

    try:
        response = client.messages.parse(
            model=config.MODEL,
            max_tokens=1024,
            system=SYSTEM,
            messages=[{"role": "user", "content": build_analysis_prompt(item)}],
            thinking={"type": "adaptive"},
            output_config={"effort": config.ANALYSIS_EFFORT},
            output_format=Commentary,
        )
    except Exception:
        log.warning("분석 해설 호출 실패 — 로컬 문장으로 대체합니다.", exc_info=True)
        return fallback.write_commentary(item), True

    if getattr(response, "stop_reason", None) == "refusal":
        log.warning("분석 해설을 거절했습니다 — 로컬 문장으로 대체합니다.")
        return fallback.write_commentary(item), True

    parsed = response.parsed_output
    if parsed is None or not parsed.commentary.strip():
        log.warning("빈 해설이 돌아왔습니다 — 로컬 문장으로 대체합니다.")
        return fallback.write_commentary(item), True

    return parsed.commentary, False
