"""종토방. 누가 무엇을 말할지 정하고 문장을 확보한다.

**세 번째 정보 레이어다.** 뉴스가 믿을 수 없는 기사라면 종토방은 믿을 수 없는
군중이다. 체결 피드가 "누가 들어갔나" 를 보여준다면 여기는 "왜 들어갔다고
말하는가" 를 보여주고, 그 말이 틀릴 수 있다는 것이 요점이다.

글은 뉴스 배치에 딸려 만들어진다. AI 의 판단이 sees_through 로 뉴스 생성
시점에 이미 정해지므로, 따라잡기 요청에서 Claude 를 다시 부를 일이 없다.
"""
import logging
import random
from collections.abc import Sequence

from app import config, participants
from app.models import BoardPlan, NewsPlan

log = logging.getLogger(__name__)


def speaks(ai_seed: int, ai_index: int, profile: config.AI, news_id: int) -> bool:
    """이 AI 가 이 기사에 글을 쓰는가.

    확률은 bet_ratio 를 그대로 쓴다 — 몰빵하는 사람이 떠든다. 새 파라미터 없이
    성격이 드러나고, 잘 낚이는 쪽이 시끄러운 것이 의도한 소음이다.

    매매 판정과 **다른 시드 조합**을 쓴다. 같으면 "말한 사람이 곧 산 사람" 이
    되어 말과 행동이 어긋나는 재미가 사라진다.
    """
    roll = random.Random((ai_seed * 7919) ^ (news_id * 131) ^ (ai_index * 17)).random()
    return roll < profile.bet_ratio


def build_board_plans(
    plans: Sequence[NewsPlan],
    ais: Sequence[participants.AIState],
    ai_seed: int,
    first_post_id: int,
) -> list[BoardPlan]:
    """기사마다 누가 무엇을 말할지 확정한다. 문장은 아직 없다."""
    posts: list[BoardPlan] = []
    post_id = first_post_id

    for plan in plans:
        spoken = 0
        for index, ai in enumerate(ais):
            if spoken >= config.BOARD_MAX_SPEAKERS:
                break
            if not speaks(ai_seed, index, ai.profile, plan.news_id):
                continue
            sees = participants.sees_through(ai_seed, index, ai.profile, plan.news_id)
            posts.append(
                BoardPlan(
                    post_id=post_id,
                    news_id=plan.news_id,
                    ai_index=index,
                    author=ai.profile.name,
                    symbol=plan.symbol,
                    bullish=participants.view_of(plan, sees) == "bullish",
                    # 반응 시각은 체결과 같은 무렵이다.
                    publish_tick=plan.publish_tick + ai.profile.reaction_ticks,
                )
            )
            post_id += 1
            spoken += 1

    return posts
