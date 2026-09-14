"""모든 밸런스 수치. 다른 파일에 숫자 리터럴을 두지 않는다."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Stock:
    name: str
    sector: str
    volatility: float  # tick당 로그수익 표준편차


STOCKS: dict[str, Stock] = {
    "hanbit":   Stock("한빛솔리드", "반도체",  0.0030),
    "geno":     Stock("제노셀",     "바이오",  0.0040),
    "sungjin":  Stock("성진셀즈",   "2차전지", 0.0030),
    "pixel":    Stock("픽셀로그",   "게임",    0.0025),
    "taesan":   Stock("태산건영",   "건설",    0.0015),
    "arawings": Stock("아라윙스",   "항공",    0.0020),
}

SEED_CASH = 1_000_000
ROUND_TARGET_MULTIPLIER = 3
TRADE_FEE_RATE = 0.002
BANKRUPTCY_THRESHOLD = 100_000

ANALYSES_PER_ROUND = 5
COMPANY_ANALYSES_PER_ROUND = 2

# 섹터 기준 배수. 실제 시장 평균에서 따왔고, 밸런스 손잡이로 쓴다.
# PER 은 흑자 분기에, PSR 은 적자 분기에 쓰인다.
SECTOR_PER: dict[str, float] = {
    "반도체": 14.0,
    "바이오": 38.0,
    "2차전지": 22.0,
    "게임": 16.0,
    "건설": 7.5,
    "항공": 11.0,
}
SECTOR_PSR: dict[str, float] = {
    "반도체": 2.2,
    "바이오": 6.5,
    "2차전지": 2.8,
    "게임": 3.0,
    "건설": 0.5,
    "항공": 1.1,
}

# 등급 경계. 양수가 고평가다.
VALUATION_SEVERE = 25.0
VALUATION_MILD = 10.0

# 시작가는 적정가 대비 이 범위에서 뽑는다. 고정 시작가를 쓰면 어느 종목이
# 고평가인지가 매판 같아서, 한 번 외운 플레이어에게 기업분석이 죽는다.
START_OFFSET_RANGE = (-0.30, 0.30)

GRIND_LOCK_SECONDS = 120
GRIND_BASE_PAYOUT = 200_000
# 0.6 을 3/5 로 둔다. 200_000 * 0.6 ** 3 은 43199.99... 가 되어 4회차 보수가
# 43,200 이 아니라 43,199 로 어긋난다. 정수 나눗셈으로 계산한다.
GRIND_DECAY_NUM = 3
GRIND_DECAY_DEN = 5

TICK_SECONDS = 1

NEWS_INTERVAL_RANGE = (12, 18)
NEWS_BATCH_SIZE = 20
NEWS_FIRST_WAIT_COUNT = 5
NEWS_REFILL_THRESHOLD = 5

# 정직 비율: 라운드마다 STEP 만큼 내려가고 FLOOR 아래로는 내려가지 않는다.
# 결과 수열 0.60 / 0.50 / 0.40 / 0.30 / 0.30 ... (스펙의 표와 하한을 함께 만족)
HONEST_RATIO_START = 0.60
HONEST_RATIO_STEP = 0.10
HONEST_RATIO_FLOOR = 0.30

# 정직이 아닌 몫을 과장 : 역방향 = 5 : 3 으로 쪼갠다.
EXAGGERATED_SHARE = 5
REVERSED_SHARE = 3

IMPACT_HONEST = (0.05, 0.15)
IMPACT_EXAGGERATED = (0.00, 0.015)
IMPACT_REVERSED = (0.06, 0.12)

# kind 로 조회하는 형태가 실제 코드가 쓰는 모양이다. 값의 출처는 위 세 상수 하나뿐이다.
IMPACT_RANGES: dict[str, tuple[float, float]] = {
    "honest": IMPACT_HONEST,
    "exaggerated": IMPACT_EXAGGERATED,
    "reversed": IMPACT_REVERSED,
}
RAMP_SECONDS_RANGE = (15, 40)

STRENGTH_STRONG_MIN = 0.08
STRENGTH_WEAK_MIN = 0.02

MODEL = "claude-opus-5"
NEWS_EFFORT = "medium"
ANALYSIS_EFFORT = "low"
