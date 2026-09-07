"""모든 밸런스 수치. 다른 파일에 숫자 리터럴을 두지 않는다."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Stock:
    name: str
    sector: str
    base_price: int
    volatility: float  # tick당 로그수익 표준편차


STOCKS: dict[str, Stock] = {
    "hanbit":   Stock("한빛솔리드", "반도체",  82_000, 0.0030),
    "geno":     Stock("제노셀",     "바이오",  45_000, 0.0040),
    "sungjin":  Stock("성진셀즈",   "2차전지", 61_000, 0.0030),
    "pixel":    Stock("픽셀로그",   "게임",    33_000, 0.0025),
    "taesan":   Stock("태산건영",   "건설",    18_500, 0.0015),
    "arawings": Stock("아라윙스",   "항공",    24_000, 0.0020),
}

SEED_CASH = 1_000_000
ROUND_TARGET_MULTIPLIER = 3
TRADE_FEE_RATE = 0.002
BANKRUPTCY_THRESHOLD = 100_000

ANALYSES_PER_ROUND = 5

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

IMPACT_RANGES: dict[str, tuple[float, float]] = {
    "honest":      (0.05, 0.15),
    "exaggerated": (0.00, 0.015),
    "reversed":    (0.06, 0.12),
}
RAMP_SECONDS_RANGE = (15, 40)

STRENGTH_STRONG_MIN = 0.08
STRENGTH_WEAK_MIN = 0.02

MODEL = "claude-opus-5"
NEWS_EFFORT = "medium"
ANALYSIS_EFFORT = "low"
