"""기업분석 해설을 확보한다. Claude 를 아는 세 번째 파일.

analysis.py 와 같은 규칙이다 — 판정은 서버가 확정하고 Claude 는 근거만
설명한다. Claude 가 다시 판정하면 플레이어에게 보이는 등급과 앵커가
실제로 끌어당기는 방향이 어긋난다.
"""
import logging

from pydantic import BaseModel

from app import config, fallback, fundamentals

log = logging.getLogger(__name__)

SYSTEM = """당신은 증권사 애널리스트입니다.
기업의 분기 재무와 확정된 밸류에이션 판정을 받고, 그 판정이 왜 그런지를 수치를 근거로 설명합니다.

규칙:
- 판정은 이미 정해져 있습니다. 다시 판단하거나 뒤집지 않습니다.
- 주어진 수치만 근거로 삼습니다. 없는 수치를 지어내지 않습니다.
- 2~3문장, 건조한 애널리스트 어투로 씁니다.
- 목표주가나 투자 권유 표현은 쓰지 않습니다.
- 회사는 모두 가상 기업입니다. 실재하는 기업·인물·기관의 이름을 쓰지 않습니다."""


class Commentary(BaseModel):
    commentary: str


def build_company_prompt(
    name: str, sector: str, valuation: str, gap: float, financials: dict
) -> str:
    """확정된 등급과 재무를 전부 넘긴다. 적정가 자체는 넘기지 않는다 —
    Claude 가 문장에 숫자를 흘리면 등급만 사려던 플레이어가 덤을 받는다."""
    per = financials["per"]
    per_line = f"{per}배" if per is not None else "적자로 산출 불가"
    return (
        f"회사: {name} ({sector})\n"
        f"분기: {financials['quarter']}\n"
        f"매출액: {financials['revenue']:,}원\n"
        f"영업이익: {financials['operating_income']:,}원\n"
        f"당기순이익: {financials['net_income']:,}원\n"
        f"EPS: {financials['eps']:,}원\n"
        f"PER: {per_line}\n"
        f"부채비율: {financials['debt_ratio']}%\n\n"
        f"확정된 판정: {fundamentals.VALUATION_LABELS[valuation]} "
        f"(섹터 기준 배수 대비 {gap:+.1f}%)\n\n"
        "이 판정의 근거를 위 수치에서 찾아 설명해 주세요."
    )


def fetch_commentary(
    name: str, sector: str, valuation: str, gap: float, financials: dict, client
) -> tuple[str, bool]:
    """(해설, offline 여부). 어떤 실패든 로컬 문장으로 떨어진다."""

    def _local() -> tuple[str, bool]:
        return fallback.write_company_commentary(
            name, sector, valuation, gap, financials
        ), True

    if client is None:
        return _local()

    try:
        response = client.messages.parse(
            model=config.MODEL,
            max_tokens=1024,
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": build_company_prompt(
                    name, sector, valuation, gap, financials
                ),
            }],
            thinking={"type": "adaptive"},
            output_config={"effort": config.ANALYSIS_EFFORT},
            output_format=Commentary,
        )
    except Exception:
        log.warning("기업분석 해설 호출 실패 — 로컬 문장으로 대체합니다.", exc_info=True)
        return _local()

    if getattr(response, "stop_reason", None) == "refusal":
        log.warning("기업분석 해설을 거절했습니다 — 로컬 문장으로 대체합니다.")
        return _local()

    parsed = response.parsed_output
    if parsed is None or not parsed.commentary.strip():
        log.warning("빈 기업분석 해설이 돌아왔습니다 — 로컬 문장으로 대체합니다.")
        return _local()

    return parsed.commentary, False
