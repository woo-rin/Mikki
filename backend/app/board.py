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

from pydantic import BaseModel

from app import config, fallback, participants
from app.models import BoardPlan, BoardPost, NewsItem, NewsPlan

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


SYSTEM = """당신은 한국 주식 커뮤니티(종목토론방)의 여러 사용자입니다.
각 사용자가 주어진 기사에 짧게 한마디 다는 글을 씁니다.

규칙:
- 한 줄, 길어야 두 줄. 커뮤니티 말투로 씁니다. 반말과 줄임말을 써도 됩니다.
- **판정이나 등급을 말하지 않습니다.** "함정", "역방향", "과장" 같은 단어를 쓰지 않습니다.
  본 대로 느낀 대로 쓰는 것이지 분석 결과를 발표하는 것이 아닙니다.
- **샀는지 팔았는지 말하지 않습니다.** 의견만 씁니다.
- 수치나 확률을 새로 만들어내지 않습니다. 투자 권유 표현도 쓰지 않습니다.
- 회사는 모두 가상 기업입니다. 실재하는 기업·인물·기관의 이름을 쓰지 않습니다.
- 사용자마다 말투가 조금씩 다르되, 누가 더 잘 아는 사람인지는 드러나지 않게 씁니다."""


class PostText(BaseModel):
    body: str


class PostBatch(BaseModel):
    items: list[PostText]


def build_board_prompt(
    plans: Sequence[BoardPlan], news_items: Sequence[NewsItem]
) -> str:
    """작성자·종목·헤드라인·시각만 넣는다.

    **통찰력은 절대 넣지 않는다.** 알면 무의식적으로 문체에 흘려 플레이어가
    읽기만으로 누가 고수인지 알아채고, 그러면 AI 분석 5회가 무의미해진다.
    news.py 가 impact 를 안 주는 것과 같은 이유다.
    """
    headlines = {item.plan.news_id: item.headline for item in news_items}
    lines = [f"글 {len(plans)}개를 써 주세요.", ""]
    for index, plan in enumerate(plans, start=1):
        stock = config.STOCKS[plan.symbol]
        mood = "긍정적으로 본다" if plan.bullish else "회의적으로 본다"
        lines.append(
            f"{index}. 작성자={plan.author} / 종목={stock.name} / "
            f"기사=\"{headlines.get(plan.news_id, '')}\" / 시각={mood}"
        )
    return "\n".join(lines)


def _unusable(response, plans: Sequence[BoardPlan]) -> str | None:
    """응답을 쓸 수 없는 이유. 쓸 수 있으면 None.

    거절·개수 불일치·빈 문장은 버그가 아니라 예상 가능한 조건이므로 예외로
    다루지 않는다.
    """
    if getattr(response, "stop_reason", None) == "refusal":
        return "모델이 요청을 거절했습니다"
    batch = getattr(response, "parsed_output", None)
    if batch is None:
        return "빈 응답"
    if len(batch.items) != len(plans):
        return "글 개수가 요청과 다릅니다(%d != %d)" % (len(batch.items), len(plans))
    if any(not t.body.strip() for t in batch.items):
        return "빈 본문"
    return None


def fetch_posts(
    plans: Sequence[BoardPlan],
    news_items: Sequence[NewsItem],
    rng: random.Random,
    client,
) -> list[BoardPost]:
    """Claude 로 문장을 채우고, 어떤 실패든 로컬 템플릿으로 떨어진다."""
    if client is None or not plans:
        return fallback.write_posts(plans, rng)

    try:
        response = client.messages.parse(
            model=config.MODEL,
            max_tokens=8000,
            system=SYSTEM,
            messages=[
                {"role": "user", "content": build_board_prompt(plans, news_items)}
            ],
            thinking={"type": "adaptive"},
            output_config={"effort": config.NEWS_EFFORT},
            output_format=PostBatch,
        )
    except Exception:
        log.warning("종토방 생성 호출 실패 — 로컬 템플릿으로 대체합니다.", exc_info=True)
        return fallback.write_posts(plans, rng)

    reason = _unusable(response, plans)
    if reason:
        log.warning("종토방 응답을 쓸 수 없습니다(%s) — 로컬 템플릿으로 대체합니다.", reason)
        return fallback.write_posts(plans, rng)

    return [
        BoardPost(plan=plan, body=text.body, offline=False)
        for plan, text in zip(plans, response.parsed_output.items)
    ]
