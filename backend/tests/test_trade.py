import math
import random

import pytest

from app import config
from app.engine import price_of
from app.session import (
    TradeError,
    avg_cost_of,
    buy,
    equity,
    max_affordable,
    new_session,
    sell,
)


def fresh():
    return new_session("s1", random.Random(0), started_at=0.0)


def test_new_session_starts_with_seed_cash_and_no_holdings():
    sess = fresh()
    assert sess.cash == config.SEED_CASH
    assert sess.holdings == {}
    assert equity(sess) == config.SEED_CASH
    assert sess.target == config.SEED_CASH * config.TARGET_MULTIPLIER
    assert sess.analyses_left == config.ANALYSES_PER_ROUND


def test_buy_deducts_gross_plus_fee_and_adds_shares():
    sess = fresh()
    price = price_of(sess.prices, "geno")
    result = buy(sess, "geno", 10, now=0.0)

    gross = price * 10
    fee = math.floor(gross * config.TRADE_FEE_RATE)
    assert result == {"symbol": "geno", "qty": 10, "price": price,
                      "gross": gross, "fee": fee, "side": "buy"}
    assert sess.cash == config.SEED_CASH - gross - fee
    assert sess.holdings == {"geno": 10}


def test_sell_credits_gross_minus_fee_and_removes_shares():
    sess = fresh()
    buy(sess, "geno", 10, now=0.0)
    cash_after_buy = sess.cash
    price = price_of(sess.prices, "geno")

    sell(sess, "geno", 4, now=0.0)

    gross = price * 4
    fee = math.floor(gross * config.TRADE_FEE_RATE)
    assert sess.cash == cash_after_buy + gross - fee
    assert sess.holdings == {"geno": 6}


def test_selling_the_whole_position_drops_the_symbol():
    sess = fresh()
    buy(sess, "geno", 3, now=0.0)
    sell(sess, "geno", 3, now=0.0)
    assert sess.holdings == {}


def test_fee_is_charged_on_both_sides():
    """수수료가 한쪽만 걸리면 왕복 매매가 손해가 아니게 되어 초단타 연타가 이득이 된다."""
    sess = fresh()
    buy(sess, "geno", 10, now=0.0)
    sell(sess, "geno", 10, now=0.0)
    assert sess.cash < config.SEED_CASH


def test_buy_beyond_cash_is_rejected_and_changes_nothing():
    sess = fresh()
    with pytest.raises(TradeError) as excinfo:
        buy(sess, "geno", 10_000, now=0.0)
    assert excinfo.value.code == "insufficient_cash"
    assert sess.cash == config.SEED_CASH
    assert sess.holdings == {}


def test_sell_beyond_holdings_is_rejected_and_changes_nothing():
    sess = fresh()
    buy(sess, "geno", 2, now=0.0)
    cash = sess.cash
    with pytest.raises(TradeError) as excinfo:
        sell(sess, "geno", 3, now=0.0)
    assert excinfo.value.code == "insufficient_shares"
    assert sess.holdings == {"geno": 2}
    assert sess.cash == cash


@pytest.mark.parametrize("qty", [0, -1, -50])
def test_non_positive_quantity_is_rejected(qty):
    sess = fresh()
    with pytest.raises(TradeError) as excinfo:
        buy(sess, "geno", qty, now=0.0)
    assert excinfo.value.code == "bad_quantity"


def test_unknown_symbol_is_rejected():
    sess = fresh()
    with pytest.raises(TradeError) as excinfo:
        buy(sess, "notreal", 1, now=0.0)
    assert excinfo.value.code == "unknown_symbol"


def test_max_affordable_accounts_for_the_fee():
    sess = fresh()
    price = price_of(sess.prices, "geno")
    qty = max_affordable(sess, "geno")

    cost = price * qty + math.floor(price * qty * config.TRADE_FEE_RATE)
    assert cost <= sess.cash
    over = price * (qty + 1)
    assert over + math.floor(over * config.TRADE_FEE_RATE) > sess.cash


def test_max_affordable_buy_always_succeeds():
    sess = fresh()
    buy(sess, "geno", max_affordable(sess, "geno"), now=0.0)
    assert sess.cash >= 0


def test_equity_is_cash_plus_floored_valuation():
    sess = fresh()
    buy(sess, "geno", 5, now=0.0)
    buy(sess, "pixel", 3, now=0.0)
    expected = (
        sess.cash
        + price_of(sess.prices, "geno") * 5
        + price_of(sess.prices, "pixel") * 3
    )
    assert equity(sess) == expected


# ----------------------------------------------------------------- 평단

def test_no_average_cost_before_buying():
    """0 으로 채우면 프론트가 틀린 손익을 그린다. 모르면 모른다고 한다."""
    assert avg_cost_of(fresh(), "geno") is None


def test_average_cost_includes_the_fee():
    sess = fresh()
    price = price_of(sess.prices, "geno")
    buy(sess, "geno", 10, now=0.0)

    gross = price * 10
    fee = math.floor(gross * config.TRADE_FEE_RATE)
    assert sess.cost_basis["geno"] == gross + fee
    assert avg_cost_of(sess, "geno") == (gross + fee) // 10


def test_two_buys_average_together():
    sess = fresh()
    buy(sess, "geno", 5, now=0.0)
    first = sess.cost_basis["geno"]
    buy(sess, "geno", 5, now=0.0)

    assert sess.cost_basis["geno"] > first
    assert avg_cost_of(sess, "geno") == sess.cost_basis["geno"] // 10


def test_partial_sell_keeps_the_average():
    """일부를 팔아도 남은 주식의 취득 단가는 그대로다."""
    sess = fresh()
    buy(sess, "geno", 10, now=0.0)
    before = avg_cost_of(sess, "geno")

    sell(sess, "geno", 4, now=0.0)

    assert sess.holdings["geno"] == 6
    assert avg_cost_of(sess, "geno") == pytest.approx(before, abs=1)


def test_selling_everything_clears_the_cost():
    sess = fresh()
    buy(sess, "geno", 10, now=0.0)
    sell(sess, "geno", 10, now=0.0)

    assert "geno" not in sess.cost_basis
    assert avg_cost_of(sess, "geno") is None


def test_rebuying_after_a_full_sell_starts_fresh():
    sess = fresh()
    buy(sess, "geno", 10, now=0.0)
    sell(sess, "geno", 10, now=0.0)
    buy(sess, "geno", 3, now=0.0)

    assert sess.holdings["geno"] == 3
    assert avg_cost_of(sess, "geno") == sess.cost_basis["geno"] // 3
