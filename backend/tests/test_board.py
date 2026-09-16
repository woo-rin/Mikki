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


def _post_plan(bullish=True, post_id=0, news_id=0, author="김부장"):
    return BoardPlan(
        post_id=post_id, news_id=news_id, ai_index=7, author=author,
        symbol="geno", bullish=bullish, publish_tick=40,
    )


def _news_item(news_id=0):
    return NewsItem(plan=plan(news_id=news_id), headline="제노셀 임상 3상 중단",
                    body="본문", offline=False)


# ------------------------------------------------------------ 프롬프트

def test_prompt_never_carries_insight():
    """**이 작업의 핵심이다.** 통찰력이 새면 문체로 고수를 알아채고
    AI 분석 5회가 무의미해진다."""
    prompt = board.build_board_prompt([_post_plan()], [_news_item()])
    for word in ("insight", "통찰력", "0.9", "0.22", "고수", "호구"):
        assert word not in prompt


def test_prompt_carries_the_article_and_the_author():
    prompt = board.build_board_prompt([_post_plan(author="김부장")], [_news_item()])
    assert "김부장" in prompt
    assert "제노셀 임상 3상 중단" in prompt


def test_prompt_states_the_tone_without_the_verdict():
    bull = board.build_board_prompt([_post_plan(bullish=True)], [_news_item()])
    bear = board.build_board_prompt([_post_plan(bullish=False)], [_news_item()])
    assert bull != bear
    for text in (bull, bear):
        assert "역방향" not in text and "과장" not in text


def test_system_forbids_naming_a_verdict():
    assert "판정" in board.SYSTEM or "등급" in board.SYSTEM


# ------------------------------------------------------------ 실패 경로

def test_fetch_falls_back_without_a_client():
    posts = board.fetch_posts([_post_plan()], [_news_item()], random.Random(0), None)
    assert len(posts) == 1 and posts[0].offline is True


def test_fetch_returns_nothing_for_no_plans():
    assert board.fetch_posts([], [], random.Random(0), None) == []


class _Boom:
    class messages:
        @staticmethod
        def parse(**kwargs):
            raise RuntimeError("네트워크가 죽었다")


def test_fetch_falls_back_when_the_call_raises():
    posts = board.fetch_posts([_post_plan()], [_news_item()], random.Random(0), _Boom())
    assert posts[0].offline is True


class _Refusal:
    class messages:
        @staticmethod
        def parse(**kwargs):
            return type("R", (), {"stop_reason": "refusal", "parsed_output": None})()


def test_fetch_falls_back_on_refusal():
    posts = board.fetch_posts([_post_plan()], [_news_item()], random.Random(0), _Refusal())
    assert posts[0].offline is True


class _Miscount:
    class messages:
        @staticmethod
        def parse(**kwargs):
            parsed = board.PostBatch(items=[board.PostText(body="하나뿐")])
            return type("R", (), {"stop_reason": "end_turn", "parsed_output": parsed})()


def test_fetch_falls_back_when_the_count_is_wrong():
    posts = board.fetch_posts(
        [_post_plan(post_id=0), _post_plan(post_id=1)],
        [_news_item()], random.Random(0), _Miscount(),
    )
    assert len(posts) == 2
    assert all(p.offline for p in posts)


class _Blank:
    class messages:
        @staticmethod
        def parse(**kwargs):
            parsed = board.PostBatch(items=[board.PostText(body="   ")])
            return type("R", (), {"stop_reason": "end_turn", "parsed_output": parsed})()


def test_fetch_falls_back_on_a_blank_body():
    posts = board.fetch_posts([_post_plan()], [_news_item()], random.Random(0), _Blank())
    assert posts[0].offline is True


class _Good:
    class messages:
        @staticmethod
        def parse(**kwargs):
            parsed = board.PostBatch(items=[board.PostText(body="이거 진짜 간다")])
            return type("R", (), {"stop_reason": "end_turn", "parsed_output": parsed})()


def test_fetch_returns_the_model_text_when_it_works():
    posts = board.fetch_posts([_post_plan()], [_news_item()], random.Random(0), _Good())
    assert posts[0].body == "이거 진짜 간다"
    assert posts[0].offline is False
    assert posts[0].plan.post_id == 0
