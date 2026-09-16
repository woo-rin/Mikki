import random

from app import board, config, participants
from app.models import BoardPlan, NewsItem, NewsPlan


def plan(news_id=0, symbol="geno", impact=0.10, tone="positive", publish_tick=30):
    return NewsPlan(
        news_id=news_id, symbol=symbol, surface_tone=tone, kind="honest",
        impact=impact, ramp_seconds=20, publish_tick=publish_tick,
    )


def ais(count=9):
    return participants.new_participants(count)


# ------------------------------------------------------------ 발언자 선택

def test_speaking_is_deterministic():
    """같은 시드는 같은 사람이 말한다. 재현 없이는 밸런스를 못 고친다."""
    profile = config.AI_ROSTER[0]
    args = (42, 0, profile, 7)
    assert board.speaks(*args) == board.speaks(*args)


def test_speaking_uses_a_different_seed_than_trading():
    """말한 사람이 곧 산 사람이 되면 안 된다. 말과 행동이 어긋나는 것이 읽을거리다."""
    profile = config.AI_ROSTER[0]
    same = sum(
        board.speaks(9, i, profile, n) == participants.sees_through(9, i, profile, n)
        for i in range(9)
        for n in range(40)
    )
    assert same < 9 * 40, "두 판정이 완전히 같다 — 시드 조합이 겹쳤다"


def test_heavy_bettors_speak_more_often():
    """몰빵하는 사람이 떠든다. 새 파라미터 없이 성격이 드러난다."""
    loud = max(config.AI_ROSTER, key=lambda a: a.bet_ratio)
    quiet = min(config.AI_ROSTER, key=lambda a: a.bet_ratio)
    loud_count = sum(board.speaks(3, 0, loud, n) for n in range(600))
    quiet_count = sum(board.speaks(3, 0, quiet, n) for n in range(600))
    assert loud_count > quiet_count * 1.5


def test_speaking_chance_tracks_the_bet_ratio():
    profile = config.AI_ROSTER[0]
    hits = sum(board.speaks(5, 2, profile, n) for n in range(2000))
    assert abs(hits / 2000 - profile.bet_ratio) < 0.06


# ------------------------------------------------------------ 계획 수립

def test_no_news_means_no_posts():
    assert board.build_board_plans([], ais(), 7, 0) == []


def test_speakers_are_capped():
    posts = board.build_board_plans([plan(news_id=n) for n in range(40)], ais(), 7, 0)
    per_news: dict[int, int] = {}
    for post in posts:
        per_news[post.news_id] = per_news.get(post.news_id, 0) + 1
    assert per_news, "아무도 말하지 않았다"
    assert max(per_news.values()) <= config.BOARD_MAX_SPEAKERS


def test_post_ids_continue_from_the_cursor():
    posts = board.build_board_plans([plan(news_id=n) for n in range(6)], ais(), 7, 100)
    ids = [p.post_id for p in posts]
    assert ids == list(range(100, 100 + len(ids)))


def test_a_post_carries_the_authors_view():
    """꿰뚫어 본 사람과 낚인 사람의 판단이 반영된다 — 문체가 아니라 톤으로."""
    trap = plan(impact=-0.10, tone="positive", news_id=1)
    posts = board.build_board_plans([trap], ais(), 11, 0)
    assert posts, "아무도 말하지 않았다"
    for post in posts:
        sees = participants.sees_through(
            11, post.ai_index, config.AI_ROSTER[post.ai_index], 1
        )
        assert post.bullish == (participants.view_of(trap, sees) == "bullish")


def test_posts_appear_after_the_article():
    """기사보다 먼저 반응이 뜨면 안 된다."""
    p = plan(publish_tick=60)
    for post in board.build_board_plans([p], ais(), 7, 0):
        assert post.publish_tick > p.publish_tick


def test_a_fooled_crowd_and_a_clear_eyed_one_can_disagree():
    """전원이 같은 말을 하면 여론을 읽을 이유가 없다."""
    views = set()
    for news_id in range(60):
        trap = plan(impact=-0.10, tone="positive", news_id=news_id)
        views.update(p.bullish for p in board.build_board_plans([trap], ais(), 5, 0))
    assert views == {True, False}
