"""물어보기 — 규칙 기반 대화.

mobile/src/assistant.ts 와 같은 규칙·문장을 쓴다 (한쪽을 고치면 다른 쪽도).
질문에서 '무엇을 찾는지(가까운 곳 · 열린 곳 · 밤늦게 · 오래 · 조용 · 시원/따뜻 · 공식 ·
시설 종류 · 장소 이름 · 날씨)' 를 읽어, 지금 분석된 주변 쉼터 중에서 골라 쉬운 말로 답한다.
답의 굵은 글씨는 <b>…</b>, 줄바꿈은 \\n 으로 표시한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ai import Analysis, live_weather
from .models import COOLING, HEATING
from .plain import (
    SHELTER_WORD,
    eun_neun,
    eyo,
    hour_word,
    i_ga,
    nearby,
    nearest_first,
    open_line,
    stay_line,
    temp_compare,
    walk_line,
)


@dataclass
class ChatReply:
    text: str
    places: list[Analysis] = field(default_factory=list)


def suggestions(mode: str) -> list[str]:
    """누르기만 하면 되는 질문."""
    return [
        "가장 가까운 쉼터는 어디야?",
        "지금 열려 있는 곳 알려줘",
        "가장 시원한 곳은?" if mode == COOLING else "가장 따뜻한 곳은?",
        "오래 쉬어도 되는 곳은?",
        "밤늦게까지 여는 곳은?",
        "지금 바깥 몇 도야?",
    ]


#: 질문에 나오는 말 → 시설 종류 (models.CATEGORIES)
CATEGORY_WORDS: list[tuple[tuple[str, ...], str]] = [
    (("도서관",), "library"),
    (("은행", "금고", "농협", "우체국"), "bank"),
    (("주민센터", "행정복지센터", "동사무소", "구청", "시청", "면사무소"), "gov"),
    (("경로당", "마을회관", "노인정"), "senior"),
    (("복지관",), "center"),
    (("지하철", "전철"), "subway"),
    (("편의점",), "store"),
    (("카페", "커피"), "cafe"),
    (("마트", "하나로"), "mart"),
    (("백화점",), "dept"),
    (("쇼핑몰",), "mall"),
    (("영화관", "극장"), "cinema"),
    (("병원",), "hospital"),
    (("서점", "책방"), "bookstore"),
    (("시장",), "market"),
    (("지하상가",), "underground"),
    (("미술관", "박물관"), "museum"),
    (("공원", "야외"), "park"),
    (("정류장", "버스"), "busstop"),
]


def _open_late(a: Analysis) -> bool:
    return a.place.always_open or a.place.open_to >= 22


def _named(name: str) -> str:
    """'<b>이름</b>이에요' — 조사는 굵게 하지 않는다."""
    return f"<b>{name}</b>{eyo(name)[len(name):]}"


def _by_open_then(items: list[Analysis], key) -> list[Analysis]:
    return sorted(items, key=lambda a: (not a.open_now, key(a)))


def respond(state, query: str) -> ChatReply:
    q = re.sub(r"\s+", "", query).lower()
    mode = state.mode
    hour, minute, weekday = state.now()

    def has(*words: str) -> bool:
        return any(w in q for w in words)

    def opening(a: Analysis) -> str:
        return open_line(a, hour, minute, weekday)

    if has("고마", "감사", "땡큐"):
        return ChatReply(f"천만에요. {'더위' if mode == COOLING else '추위'} 조심하세요!")
    if has("안녕", "하이") and len(q) <= 8:
        return greeting(state)

    # 날씨만 묻는 질문 ('시원한 곳' 처럼 장소를 찾는 질문은 아래에서)
    if has("날씨", "몇도", "기온", "바깥온도", "밖에온도", "덥나", "춥나") and not has("곳", "쉼터", "어디"):
        w = live_weather(mode, hour, minute, state.origin)
        alert = f" <b>{w.alert}</b>가 내려져 있어요." if w.alert else ""
        tip = "물을 자주 마시고 그늘에서 쉬세요." if mode == COOLING else "따뜻하게 입고 실내에서 쉬세요."
        return ChatReply(f"지금 바깥은 <b>{w.outdoor:.0f}°C</b>예요.{alert}\n{tip}")

    analyses = nearby(state)
    if not analyses:
        return ChatReply("주변 쉼터를 아직 찾지 못했어요. 잠시 뒤에 다시 물어봐 주세요.")

    # 장소 이름을 콕 집어 물은 경우 — "○○도서관 몇 시까지야?"
    named = sorted(
        (a for a in analyses
         if len(n := re.sub(r"\s+", "", a.place.name).lower()) >= 2 and n in q),
        key=lambda a: -len(a.place.name))
    if named:
        a = named[0]
        return ChatReply(
            f"{_named(a.place.name)}.\n{walk_line(a)} 거리예요. {opening(a)}.\n"
            f"운영 시간은 {a.place.hours_label()}이에요.", [a])

    pool = analyses
    notes: list[str] = []

    # 시설 종류
    cat = next(((words, key) for words, key in CATEGORY_WORDS if has(*words)), None)
    if cat:
        found = [a for a in pool if a.place.category == cat[1]]
        label = cat[0][0]
        if not found:
            near = nearest_first(pool)
            return ChatReply(f"주변에 {i_ga(label)} 없어요.\n"
                             f"대신 가장 가까운 쉼터는 {_named(near[0].place.name)}.", near[:3])
        pool = found

    # 조건 (여러 개를 함께 쓸 수 있다)
    if has("밤", "늦게", "야간", "새벽", "24시간", "심야"):
        late = [a for a in pool if _open_late(a)]
        if not late:
            near = nearest_first(pool)
            return ChatReply("밤 10시 넘어서까지 여는 쉼터가 주변에 없어요.\n"
                             f"가장 가까운 곳은 {_named(near[0].place.name)}. {opening(near[0])}.",
                             near[:3])
        pool = late
        notes.append("late")
    if has("열려", "열린", "지금열", "문연", "문열", "영업중", "운영중"):
        open_ = [a for a in pool if a.open_now]
        if not open_:
            near = nearest_first(pool)
            return ChatReply("지금 열려 있는 쉼터가 주변에 없어요.\n"
                             f"가장 가까운 {_named(near[0].place.name)}. {opening(near[0])}.",
                             near[:3])
        pool = open_
        notes.append("open")
    if has("공식", "무료", "공짜", "돈안", "돈없"):
        official = [a for a in pool if a.place.official]
        if official:
            pool = official
        notes.append("official")

    # 무엇을 기준으로 고를지
    warm_words = has("따뜻", "따듯", "난방", "히터", "덜추운")
    cool_words = has("시원", "에어컨", "냉방")
    warm = warm_words or (not cool_words and mode == HEATING)
    kind = "near"
    if has("오래", "눈치", "편하게", "종일", "하루", "부담"):
        kind = "long"
        ordered = _by_open_then(pool, lambda a: a.nuisance.score)
    elif has("조용", "공부", "책읽", "집중"):
        kind = "quiet"
        ordered = _by_open_then(pool, lambda a: -a.place.quiet)
    elif cool_words or warm_words:
        kind = "temp"
        ordered = _by_open_then(pool, lambda a: -a.indoor if warm else a.indoor)
    else:
        ordered = nearest_first(pool)

    best = ordered[0]
    understood = (kind != "near" or cat or notes
                  or has("가까", "근처", "주변", "어디", "쉼터", "잠깐", "잠시", "가야", "갈곳", "갈만"))
    lines: list[str] = []
    if not understood:
        lines.append("질문을 잘 알아듣지 못했어요. 가까운 쉼터를 알려 드릴게요.")

    what = cat[0][0] if cat else SHELTER_WORD[mode]
    if not best.open_now:
        lines.append("지금 열려 있는 곳이 없어서, 문 닫은 곳 중에서 골랐어요.")
    name = best.place.name
    if kind == "long":
        lines += [f"오래 머물러도 눈치가 덜 보이는 곳은 {_named(name)}.",
                  f"{stay_line(best)}. {walk_line(best)}이에요."]
    elif kind == "quiet":
        lines += [f"조용히 쉬기 좋은 곳은 {_named(name)} ({best.place.category_label}).",
                  f"{walk_line(best)}이에요."]
    elif kind == "temp":
        cmp = temp_compare(best)
        lines += [f"가장 {'따뜻한' if warm else '시원한'} 곳은 {_named(name)}.",
                  f"실내 약 {round(best.indoor)}°C{f'로 {cmp}' if cmp else '예요'}. {walk_line(best)}이에요."]
    elif "late" in notes:
        until = "24시간 열려 있어요" if best.place.always_open else f"{hour_word(best.place.open_to)}까지 열어요"
        lines += [f"밤늦게까지 여는 곳은 {_named(name)}.", f"{until}. {walk_line(best)}이에요."]
    elif "open" in notes:
        lines += [f"지금 열려 있는 {i_ga(what)} {len(pool)}곳 있어요.",
                  f"가장 가까운 곳은 {_named(name)}. {walk_line(best)}, {opening(best)}."]
    else:
        prefix = "공식 쉼터 중 " if "official" in notes else ""
        lines += [f"{prefix}가장 가까운 {eun_neun(what)} {_named(name)}.",
                  f"{walk_line(best)} 거리예요. {opening(best)}."]
    if len(ordered) > 1:
        lines.append("다른 곳도 아래에 함께 보여 드릴게요.")
    return ChatReply("\n".join(lines), ordered[:3])


def greeting(state) -> ChatReply:
    hour, minute, _ = state.now()
    w = live_weather(state.mode, hour, minute, state.origin)
    alert = f" ({w.alert})" if w.alert else ""
    return ChatReply(
        f"안녕하세요! 지금 바깥은 <b>{w.outdoor:.0f}°C</b>예요{alert}.\n"
        f"{SHELTER_WORD[state.mode]}에 대해 궁금한 걸 물어보세요.\n아래 질문을 눌러도 돼요.")
