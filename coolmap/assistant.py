"""CoolMap Intelligence — 규칙 기반 추천 어시스턴트.

사용자의 자연어 질문을 의도로 분해한 뒤, 예측 엔진 결과를 근거로 답한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ai import CROWD_ENABLED, Analysis, analyze_all, rank
from .catalog import places_for
from .models import COOLING

QUICK_PROMPTS = [
    ("저혼잡", "지금 사람 적은 곳 알려줘", "users"),
    ("15분 휴식", "15분만 쉬어갈 곳 추천해줘", "clock"),
    ("눈치 없는 곳", "오래 있어도 눈치 안 보이는 곳", "star"),
    ("조용한 곳", "조용한 곳 추천해줘", "info"),
    ("늦게까지", "밤 9시 이후에도 여는 곳", "clock"),
]

_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("조용", "정숙", "집중", "공부", "quiet"), "quiet"),
    (("눈치", "민폐", "오래", "장시간", "부담", "free"), "free"),
    (("가까", "근처", "빨리", "제일 가까", "close"), "close"),
    (("시원", "추운", "차가", "cool", "더위", "폭염"), "cool"),
    (("따뜻", "온기", "난방", "추위", "한파", "warm"), "cool"),
]


@dataclass
class ChatReply:
    text: str
    places: list[Analysis] = field(default_factory=list)
    note: str = ""


def _open_late(a: Analysis) -> bool:
    p = a.place
    return p.always_open or p.open_to >= 22


def respond(state, query: str) -> ChatReply:
    q = query.strip()
    low = q.lower()
    hour, minute, weekday = state.now()
    mode = state.mode

    analyses = analyze_all(
        places_for(mode, origin=state.origin, radius_m=float(state.get('search_radius'))),
        mode, hour, minute, weekday, state.target_temp, origin=state.origin)
    open_now = [a for a in analyses if a.crowd.open_now]

    # --- 의도 판별 ---------------------------------------------------
    prefer = "balanced"
    for keys, key in _KEYWORDS:
        if any(k in low for k in keys):
            prefer = key
            break

    pool = open_now or analyses
    note = ""

    if any(k in low for k in ("이벤트", "행사", "축제", "붐비", "혼잡")):
        affected = [a for a in analyses if a.crowd.by_event]
        if affected:
            names = ", ".join(a.place.name for a in affected[:3])
            calm = rank([a for a in pool if not a.crowd.by_event])[:2]
            lead = ("<b>사람이 이벤트로 인해 많아요</b>"
                    if CROWD_ENABLED else "<b>행사가 진행 중</b>이라 평소보다 붐빌 수 있어요")
            alt = f"<br>대신 <b>{calm[0].place.name}</b> 쪽을 추천해요." if calm else ""
            return ChatReply(
                text=f"지금 {names} 주변은 {lead}. {affected[0].crowd.detail}{alt}",
                places=calm,
                note="행사 영향권은 지도에서 노란 원으로 표시됩니다."
                     + ("" if CROWD_ENABLED else " 실시간 혼잡도 수치는 준비 중입니다."),
            )
        return ChatReply(
            text="지금 주변에 진행 중인 대형 행사는 없어요. 혼잡도는 평소 수준입니다.",
            places=rank(pool)[:2],
        )

    if any(k in low for k in ("밤", "늦게", "9시", "10시", "야간", "심야", "새벽")):
        late = [a for a in analyses if _open_late(a)]
        pool = late or pool
        note = "22시 이후에도 운영하는 곳만 추렸어요."

    if any(k in low for k in ("15분", "잠깐", "잠시", "짧게")):
        pool = [a for a in pool if a.walk_min <= 12]
        prefer = "close"
        note = "도보 12분 이내, 짧은 휴식에 적합한 곳입니다."

    if any(k in low for k in ("무료", "공공", "공식", "지정")):
        official = [a for a in pool if a.place.official]
        pool = official or pool
        note = "공식 지정 쉼터만 추렸어요."

    if not pool:
        return ChatReply(text="조건에 맞는 쉼터를 찾지 못했어요. 조건을 조금 넓혀볼까요?")

    ranked = rank(pool, prefer=prefer)
    top = ranked[:3]
    best = top[0]

    mode_word = "시원한" if mode == COOLING else "따뜻한"
    reason_map = {
        "quiet": "정숙도가 높은 순으로 골랐어요.",
        "free": "눈치 부담(민폐도)이 가장 낮은 순입니다.",
        "close": "현재 위치에서 가까운 순입니다.",
        "cool": "실내외 온도 격차가 큰 순입니다.",
        "balanced": "쾌적도·혼잡도·민폐도를 종합했어요.",
    }

    lines = [
        f"현재 외기 {best.weather.outdoor}°C 기준으로 가장 {mode_word} 곳은 "
        f"<b>{best.place.name}</b>입니다.",
        (f"실내 {best.indoor:.1f}°C · 쾌적 {best.comfort}점 · 혼잡 {best.crowd.level} · "
         f"민폐도 {best.nuisance.score}({best.nuisance.level}), 권장 체류 {best.nuisance.stay_label}."
         if CROWD_ENABLED else
         f"실내 {best.indoor:.1f}°C · 쾌적 {best.comfort}점 · "
         f"민폐도 {best.nuisance.score}({best.nuisance.level}), 권장 체류 {best.nuisance.stay_label}."),
        reason_map.get(prefer, ""),
    ]
    if best.crowd.by_event:
        lines.insert(1, f"다만 <b>{best.crowd.headline}</b> — {best.crowd.detail}")

    return ChatReply(text="<br>".join(x for x in lines if x), places=top, note=note)


def greeting(state) -> ChatReply:
    hour, minute, weekday = state.now()
    mode = state.mode
    analyses = analyze_all(
        places_for(mode, origin=state.origin, radius_m=float(state.get('search_radius'))),
        mode, hour, minute, weekday, state.target_temp, origin=state.origin)
    ranked = rank([a for a in analyses if a.crowd.open_now] or analyses)
    w = ranked[0].weather if ranked else None
    mode_word = "폭염" if mode == COOLING else "한파"
    text = (
        f"안녕하세요. 지금 외기는 <b>{w.outdoor}°C</b>"
        f"{' (' + w.alert + ')' if w and w.alert else ''}입니다. "
        f"{mode_word} 대응 쉼터를 실시간으로 분석하고 있어요.<br>"
        f"아래 버튼을 누르거나 원하는 조건을 직접 입력해 보세요."
    )
    return ChatReply(text=text, places=ranked[:2])
