"""DART 오픈API 에서 재무를 받아 data/fundamentals.json 을 다시 만든다.

    DART_API_KEY=... python3 scripts/fetch_fundamentals.py [연도]

서버는 이 파일을 임포트하지 않는다. 분기에 한 번 손으로 돌린다.

매핑표는 이 파일 안에만 있다. 출력 JSON 에 corp_code 를 넣으면 어느
실존 기업인지 역추적되고, 그러면 가상 이름을 쓰는 의미가 사라진다.
"""
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

BASE = "https://opendart.fss.or.kr/api"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "fundamentals.json"

# 가상 심볼 → (실존 corp_code, 사람이 읽는 설명)
# corp_code 는 DART 의 corpCode.xml 에서 찾는다.
MAPPING: dict[str, tuple[str, str]] = {
    "hanbit":   ("00126380", "실존 반도체 대형주"),
    "geno":     ("00105271", "실존 바이오 중형주"),
    "sungjin":  ("00164779", "실존 2차전지 소재주"),
    "pixel":    ("00258801", "실존 게임 퍼블리셔"),
    "taesan":   ("00106641", "실존 건설 중견주"),
    "arawings": ("00113410", "실존 항공 운송주"),
}

# 분기 → DART reprt_code
REPORTS = [("Q1", "11013"), ("Q2", "11012"), ("Q3", "11014"), ("Q4", "11011")]

# 우리가 쓰는 계정명 → DART 계정명 후보 (회사마다 표기가 다르다)
ACCOUNTS = {
    "revenue": ("매출액", "수익(매출액)", "영업수익"),
    "operating_income": ("영업이익", "영업이익(손실)"),
    "net_income": ("당기순이익", "당기순이익(손실)"),
    "equity": ("자본총계",),
    "debt": ("부채총계",),
}


def _get(path: str, **params) -> dict:
    params["crtfc_key"] = os.environ["DART_API_KEY"]
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "000":
        raise RuntimeError(
            f"{path} 실패: {payload.get('status')} {payload.get('message')}"
        )
    return payload


def _amount(rows: list[dict], names: tuple[str, ...]) -> int:
    for row in rows:
        if row.get("account_nm") in names and row.get("sj_div") in ("IS", "CIS", "BS"):
            raw = (row.get("thstrm_amount") or "").replace(",", "").strip()
            if raw in ("", "-"):
                continue
            return int(raw)
    raise RuntimeError(f"계정을 찾지 못했다: {names}")


def _shares(corp_code: str, year: str) -> int:
    rows = _get("stockTotqySttus.json", corp_code=corp_code,
                bsns_year=year, reprt_code="11011")["list"]
    for row in rows:
        if row.get("se") in ("보통주", "합계"):
            raw = (row.get("istc_totqy") or "").replace(",", "").strip()
            if raw not in ("", "-"):
                return int(raw)
    raise RuntimeError("주식총수를 찾지 못했다")


def build(year: str) -> dict:
    stocks = {}
    for symbol, (corp_code, described_as) in MAPPING.items():
        shares = _shares(corp_code, year)
        quarters = []
        for suffix, reprt_code in REPORTS:
            rows = _get("fnlttSinglAcntAll.json", corp_code=corp_code,
                        bsns_year=year, reprt_code=reprt_code, fs_div="CFS")["list"]
            quarter = {"label": f"{year}{suffix}"}
            for field, names in ACCOUNTS.items():
                quarter[field] = _amount(rows, names)
            quarter["shares"] = shares
            quarters.append(quarter)
        stocks[symbol] = {"mapped_from": described_as, "quarters": quarters}
        print(f"  {symbol}: 4개 분기", file=sys.stderr)
    return stocks


def main() -> int:
    if not os.environ.get("DART_API_KEY"):
        print("DART_API_KEY 가 없다. https://opendart.fss.or.kr 에서 발급받는다.",
              file=sys.stderr)
        return 1
    year = sys.argv[1] if len(sys.argv) > 1 else "2024"
    print(f"{year}년 재무를 받는다…", file=sys.stderr)

    # 전부 성공한 뒤에야 쓴다. 중간에 죽으면 기존 파일은 그대로 남는다.
    stocks = build(year)

    OUT.write_text(
        json.dumps(
            {"generated_at": year, "source": "DART 오픈API", "stocks": stocks},
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"{OUT} 를 새로 썼다.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
