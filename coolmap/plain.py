"""화면에 보여 줄 쉬운 말.

점수·영어·전문 용어 대신 누구나 바로 알아듣는 문장으로 바꾼다.
mobile/src/plain.ts 와 같은 문장을 쓴다 — 한쪽을 고치면 다른 쪽도 고친다.
"""

from __future__ import annotations

from urllib.parse import quote

from .ai import Analysis
from .models import COOLING

MODE_TITLE = {COOLING: "더위 피하기", "heating": "추위 피하기"}
SHELTER_WORD = {COOLING: "무더위쉼터", "heating": "한파쉼터"}

#: AI 추정 쉼터는 이만큼(m) 더 먼 것처럼 친다. 비슷한 거리면 공식 쉼터를 먼저 권하고,
#: AI 추정 쉼터는 확실히 더 가까울 때만 앞에 온다 (공식 쉼터가 아니고 운영 여부도 추정이라서).
AI_GUESS_PENALTY_M = 300


def hour_word(h: int) -> str:
    """0~24시 → '오전 9시', '오후 6시', '밤 12시'."""
    x = h % 24
    if x == 0:
        return "밤 12시"
    if x < 12:
        return f"오전 {x}시"
    if x == 12:
        return "낮 12시"
    return f"오후 {x - 12}시"


def open_line(a: Analysis, hour: int, minute: int, weekday: int) -> str:
    """지금 열려 있는지와 언제까지인지."""
    p = a.place
    if p.always_open:
        return "24시간 열려 있어요"
    if not a.open_now:
        if p.weekend_closed and weekday >= 5:
            return "주말이라 문을 닫았어요"
        return f"지금 문 닫음 · {hour_word(p.open_from)}에 열어요"
    left = p.closing_in(hour, minute)
    if left is not None and left <= 60:
        return f"곧 문 닫아요 · {left}분 남음"
    return f"지금 열려 있어요 · {hour_word(p.open_to)}까지"


def walk_line(a: Analysis) -> str:
    return f"걸어서 {max(1, a.walk_min)}분 ({a.distance_label})"


def temp_line(a: Analysis) -> str:
    return f"실내 약 {round(a.indoor)}°C"


def temp_compare(a: Analysis) -> str:
    """실내가 바깥보다 얼마나 시원한지(따뜻한지)."""
    d = round(abs(a.weather.outdoor - a.indoor))
    if d < 1:
        return "바깥과 비슷해요"
    return f"바깥보다 {d}°C {'시원해요' if a.indoor < a.weather.outdoor else '따뜻해요'}"


def stay_line(a: Analysis) -> str:
    """민폐도(눈치)를 쉬운 말로."""
    key = a.nuisance.key
    if key in ("very_low", "low"):
        return "오래 머물러도 괜찮아요"
    if key == "normal":
        return f"{a.nuisance.stay_label} 정도 쉬기 좋아요"
    return "잠깐 쉬어 가기 좋아요"


def tags(a: Analysis) -> list[tuple[str, str]]:
    """(문구, 'good'|'warn'|'mute') — 공식 쉼터 · AI 추정 · 물건 구매 필요."""
    out: list[tuple[str, str]] = []
    if a.place.official:
        out.append(("공식 쉼터", "good"))
    if a.place.ai_guess:
        out.append(("AI 추정 · 공식 아님", "warn"))
    if a.place.purchase_required:
        out.append(("물건 구매 필요", "mute"))
    return out


def nearest_first(items: list[Analysis]) -> list[Analysis]:
    """지금 열려 있는 곳 먼저, 그다음 가까운 순."""
    return sorted(items, key=lambda a: (
        not a.open_now,
        a.meters + (AI_GUESS_PENALTY_M if a.place.ai_guess else 0),
    ))


def directions_url(a: Analysis, origin: tuple[float, float] | None) -> str:
    """카카오맵 웹 길찾기 (현재 위치 → 쉼터). 구글 지도는 한국에서 도보 경로를 주지 않는다."""
    name = quote(a.place.name)
    if origin:
        here = quote("현재 위치")
        return (f"https://map.kakao.com/link/from/{here},{origin[0]},{origin[1]}"
                f"/to/{name},{a.place.lat},{a.place.lon}")
    return f"https://map.kakao.com/link/to/{name},{a.place.lat},{a.place.lon}"


def _batchim(word: str) -> bool | None:
    w = word.strip()
    if not w:
        return None
    c = ord(w[-1])
    if 0xAC00 <= c <= 0xD7A3:
        return (c - 0xAC00) % 28 != 0
    return None


def eyo(word: str) -> str:
    """받침이 있으면 '이에요', 없으면 '예요'."""
    return word + ("예요" if _batchim(word) is False else "이에요")


def eun_neun(word: str) -> str:
    return word + ("는" if _batchim(word) is False else "은")


def i_ga(word: str) -> str:
    return word + ("가" if _batchim(word) is False else "이")


def nearby(state) -> list[Analysis]:
    """설정(공식만 · 최대 도보 · AI 추정 포함)을 적용한 주변 쉼터 분석 — 홈 · 지도 · 물어보기가 같이 쓴다."""
    from .ai import analyze_all
    from .catalog import places_for

    hour, minute, weekday = state.now()
    places = places_for(state.mode, origin=state.origin,
                        radius_m=float(state.get("search_radius")),
                        include_ai=bool(state.get("ai_candidates")))
    out = analyze_all(places, state.mode, hour, minute, weekday,
                      state.target_temp, origin=state.origin)
    if state.get("only_official"):
        out = [a for a in out if a.place.official]
    return [a for a in out if a.walk_min <= int(state.get("max_walk"))]
