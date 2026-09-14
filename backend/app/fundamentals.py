"""재무 스냅샷과 적정가. 네트워크를 모른다 — 커밋된 파일만 읽는다.

적정가는 임팩트와 같은 등급의 정답이다. 상태 스냅샷에 실으면 F12 한 번으로
기업분석이 무의미해진다. 밖으로 내보내는 곳은 기업분석 응답 하나뿐이다.
"""
import json
import math
import pathlib

from app import config

SNAPSHOT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "data" / "fundamentals.json"
)

VALUATION_LABELS: dict[str, str] = {
    "severely_overvalued": "심각한 고평가",
    "overvalued": "고평가",
    "fair": "적정",
    "undervalued": "저평가",
    "severely_undervalued": "심각한 저평가",
}

_cache: dict | None = None


def load(path: str | None = None) -> dict:
    """스냅샷을 읽는다. 기본 경로는 프로세스 수명 동안 한 번만 읽는다."""
    global _cache
    if path is not None:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if _cache is None:
        _cache = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return _cache


def quarter_of(snapshot: dict, symbol: str, round_no: int) -> dict:
    """라운드 N 은 quarters[N-1]. 라운드 수에 상한이 없으므로 마르면 마지막을 쓴다."""
    quarters = snapshot["stocks"][symbol]["quarters"]
    return quarters[min(round_no - 1, len(quarters) - 1)]


def eps(quarter: dict) -> int:
    return quarter["net_income"] // quarter["shares"]


def sps(quarter: dict) -> int:
    return quarter["revenue"] // quarter["shares"]


def fair_value(symbol: str, quarter: dict) -> int:
    """흑자면 PER, 적자면 PSR. 원 단위 내림.

    적자 성장주를 매출 기준으로 보는 것은 실제 밸류에이션 실무와 같다.
    PER 을 그대로 쓰면 음수 적정가가 나와 앵커가 가격을 0 아래로 민다.
    """
    sector = config.STOCKS[symbol].sector
    if quarter["net_income"] > 0:
        return math.floor(config.SECTOR_PER[sector] * eps(quarter))
    return math.floor(config.SECTOR_PSR[sector] * sps(quarter))


def fair_values(round_no: int) -> dict[str, int]:
    """그 라운드의 전 종목 적정가."""
    snapshot = load()
    return {
        symbol: fair_value(symbol, quarter_of(snapshot, symbol, round_no))
        for symbol in config.STOCKS
    }


def gap_pct(current_price: int, fair: int) -> float:
    """양수가 고평가다. 표시용이라 내림 규칙에서 면제된다."""
    return round((current_price - fair) / fair * 100, 1)


def valuation_of(gap: float) -> str:
    if gap >= config.VALUATION_SEVERE:
        return "severely_overvalued"
    if gap >= config.VALUATION_MILD:
        return "overvalued"
    if gap > -config.VALUATION_MILD:
        return "fair"
    if gap > -config.VALUATION_SEVERE:
        return "undervalued"
    return "severely_undervalued"


def per_of(current_price: int, quarter: dict) -> float | None:
    """적자면 None. 없는 숫자를 지어내지 않는다."""
    earnings = eps(quarter)
    if earnings <= 0:
        return None
    return round(current_price / earnings, 1)


def debt_ratio(quarter: dict) -> float:
    return round(quarter["debt"] / quarter["equity"] * 100, 1)
