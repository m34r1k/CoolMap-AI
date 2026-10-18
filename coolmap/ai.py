"""CoolMap 예측 엔진.

- 민폐도 점수: 구매 압박, 시선, 좌석, 공식 쉼터 여부로 산출 (Gemini 결과가 있으면 그것을 쓴다)
- 쾌적 점수: 온도/습도/공기흐름/공기질 가중 합

혼잡도(사람 수) 추정은 근거 데이터가 없어 넣지 않는다.

외부 모델 호출 없이 결정론적으로 동작하므로 언제나 같은 입력 → 같은 결과.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .data import USER_HOME, distance, walk_minutes, weather_for
from .models import COOLING, HEATING, Place, Weather

NUISANCE_LEVELS = [
    (20, "매우 자연스러움", "very_low"),
    (38, "자연스러움", "low"),
    (58, "보통", "normal"),
    (76, "눈치 보임", "high"),
    (101, "매우 눈치 보임", "very_high"),
]

_BASE_STAY: dict[str, int] = {
    "library": 180, "gov": 150, "center": 150, "museum": 100, "mall": 90,
    "dept": 70, "underground": 60, "market": 60, "park": 60, "cafe": 90,
    "bookstore": 45, "hospital": 45, "cinema": 40, "subway": 30,
    "bank": 25, "store": 20,
}


# ---------------------------------------------------------------------------
# 결과 자료구조
# ---------------------------------------------------------------------------
@dataclass
class NuisanceScore:
    score: int
    level: str
    key: str
    stay_minutes: int
    factors: list[tuple[str, int]] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)
    reason: str = ""
    source: str = "rule"          # "gemini" | "rule"

    @property
    def stay_label(self) -> str:
        if self.stay_minutes >= 120:
            h, m = divmod(self.stay_minutes, 60)
            return f"{h}시간" + (f" {m}분" if m else "")
        return f"{self.stay_minutes}분"


@dataclass
class Analysis:
    place: Place
    mode: str
    weather: Weather
    open_now: bool
    nuisance: NuisanceScore
    comfort: int
    indoor: float
    feels_inside: float
    delta: float
    meters: float
    walk_min: int

    @property
    def distance_label(self) -> str:
        if self.meters >= 1000:
            return f"{self.meters / 1000:.1f}km"
        return f"{int(round(self.meters / 10) * 10)}m"


# ---------------------------------------------------------------------------
# 내부 계산
# ---------------------------------------------------------------------------
def score_nuisance(place: Place, hour: int, minute: int = 0) -> NuisanceScore:
    """민폐도: 높을수록 '오래 있으면 눈치 보이는' 장소."""
    factors: list[tuple[str, int]] = []
    score = 18.0

    if place.purchase_required:
        score += 30
        factors.append(("구매 필요", 30))

    press = int(round(place.staff_pressure * 30))
    if press:
        score += press
        factors.append(("직원·주변 시선", press))

    if place.seats < 30:
        score += 13
        factors.append(("좌석 부족", 13))
    elif place.seats < 60:
        score += 6
        factors.append(("좌석 여유 낮음", 6))

    if place.official:
        score -= 14
        factors.append(("공식 지정 쉼터", -14))

    remain = place.closing_in(hour, minute)
    if remain is not None and remain <= 45:
        score += 9
        factors.append(("마감 임박", 9))

    if place.category in ("hospital",):
        score += 8
        factors.append(("이용 목적 배려 필요", 8))

    score = int(max(3, min(97, round(score))))
    level, key = NUISANCE_LEVELS[-1][1], NUISANCE_LEVELS[-1][2]
    for limit, lbl, k in NUISANCE_LEVELS:
        if score < limit:
            level, key = lbl, k
            break

    base = _BASE_STAY.get(place.category, 60)
    stay = base * (1 - score / 165.0)
    stay = int(max(10, round(stay / 5) * 5))
    if remain is not None:
        stay = min(stay, max(10, remain))

    tips: list[str] = []
    if place.official:
        tips.append("공식 지정 쉼터입니다. 눈치 보지 말고 이용하세요.")
    if place.purchase_required:
        tips.append("음료 1잔 주문 후 이용하면 부담이 크게 줄어요.")
    if place.staff_pressure >= 0.5:
        tips.append("직원 동선을 피해 창가·구석 좌석을 이용하는 편이 좋아요.")
    if place.quiet >= 0.75:
        tips.append("정숙이 요구되는 공간이에요. 통화는 로비에서 하세요.")
    if remain is not None and remain <= 45:
        tips.append(f"마감까지 약 {remain}분 남았어요.")
    if not tips:
        tips.append("특별히 주의할 점은 없어요. 편하게 머무르셔도 됩니다.")

    return NuisanceScore(score=score, level=level, key=key, stay_minutes=stay,
                         factors=factors, tips=tips)


def comfort_score(
    place: Place,
    mode: str,
    weather: Weather,
    open_now: bool,
    target: float | None = None,
) -> int:
    indoor = place.indoor_temp(mode)
    if target is None:
        target = 24.0 if mode == COOLING else 22.0

    diff = indoor - target
    if mode == COOLING:
        # 목표보다 더 시원한 것은 관대하게, 더운 것은 엄격하게 감점
        temp_s = 100 - (abs(diff) * 7.0 if diff < 0 else diff * 11.5)
    else:
        temp_s = 100 - (abs(diff) * 11.5 if diff < 0 else diff * 7.0)

    humid_s = 100 - abs(place.humidity - 45) * 2.2
    air_s = {"우수": 96, "양호": 76, "보통": 56}.get(place.airflow, 66)
    aqi_s = 100 - place.aqi * 1.5
    total = (temp_s * 0.32 + air_s * 0.14 + humid_s * 0.13 + aqi_s * 0.15) / 0.74

    # 외기와의 격차 보너스 (쉼터로서의 가치)
    if mode == COOLING:
        total += max(0.0, min(5.0, (weather.outdoor - indoor) * 0.42))
    else:
        total += max(0.0, min(5.0, (indoor - weather.outdoor) * 0.16))

    if not open_now:
        total *= 0.55
    return int(max(0, min(100, round(total))))


def live_weather(mode: str, hour: int, minute: int, latlon: tuple[float, float] | None = None) -> Weather:
    """기상청 실황이 있으면 실데이터, 없으면 모의 곡선."""
    from . import providers

    try:
        wp = providers.weather_provider()
        lat, lon = latlon or USER_HOME
        return wp.weather(lat, lon, mode, hour, minute)
    except Exception:
        return weather_for(mode, hour, minute)


def live_sky(latlon: tuple[float, float] | None = None) -> tuple[str, str, str]:
    """(아이콘, '비가 와요', '오후 5시쯤 그칠 것 같아요'). 모르면 빈 글자 — plain.sky_line."""
    from datetime import datetime

    from . import providers
    from .plain import sky_line

    try:
        wp = providers.weather_provider()
        lat, lon = latlon or USER_HOME
        return sky_line(wp.observation(lat, lon), wp.sky(lat, lon), datetime.now())
    except Exception:
        return "", "", ""


def ai_nuisance(place: Place, mode: str, fallback: NuisanceScore) -> NuisanceScore:
    """Gemini 결과가 준비돼 있으면 그것으로, 아니면 규칙 기반 폴백."""
    from . import providers

    try:
        data = providers.nuisance_ai().get(place, mode)
    except Exception:
        data = None
    if not data:
        return fallback

    score = int(data["score"])
    level, key = NUISANCE_LEVELS[-1][1], NUISANCE_LEVELS[-1][2]
    for limit, lbl, k in NUISANCE_LEVELS:
        if score < limit:
            level, key = lbl, k
            break
    tips = list(data.get("tips") or []) or fallback.tips
    reason = data.get("reason", "")
    return NuisanceScore(
        score=score,
        level=level,
        key=key,
        stay_minutes=int(data["stay_minutes"]),
        factors=fallback.factors,
        tips=tips,
        reason=reason,
        source="gemini",
    )


def analyze(
    place: Place,
    mode: str,
    hour: int,
    minute: int = 0,
    weekday: int = 0,
    target: float | None = None,
    origin: tuple[float, float] | None = None,
) -> Analysis:
    weather = live_weather(mode, hour, minute, origin or place.latlon)
    open_now = place.is_open(hour, weekday)
    nuisance = ai_nuisance(place, mode, score_nuisance(place, hour, minute))
    comfort = comfort_score(place, mode, weather, open_now, target)
    indoor = place.indoor_temp(mode)
    # 실내 체감: 습할수록 덥게(냉방), 난방은 약간 따뜻하게 느낀다
    if mode == COOLING:
        feels = indoor + (place.humidity - 45) * 0.04
    else:
        feels = indoor + 0.4
    meters = distance(origin or USER_HOME, place.latlon)
    return Analysis(
        place=place, mode=mode, weather=weather, open_now=open_now, nuisance=nuisance,
        comfort=comfort, indoor=indoor, feels_inside=round(feels, 1),
        delta=round(abs(weather.outdoor - indoor), 1),
        meters=meters, walk_min=walk_minutes(meters),
    )


def analyze_all(
    places,
    mode: str,
    hour: int,
    minute: int = 0,
    weekday: int = 0,
    target: float | None = None,
    origin: tuple[float, float] | None = None,
) -> list[Analysis]:
    return [
        analyze(p, mode, hour, minute, weekday, target, origin)
        for p in places
        if p.supports(mode)
    ]


def rank(analyses: list[Analysis], *, prefer: str = "balanced") -> list[Analysis]:
    """추천 정렬. prefer: balanced | cool | quiet | close | free"""

    def key(a: Analysis) -> float:
        s = a.comfort
        s -= a.nuisance.score * 0.35
        s -= min(a.walk_min, 40) * 0.55
        if not a.open_now:
            s -= 60
        if prefer == "cool":
            s += (a.weather.outdoor - a.indoor) * (1.4 if a.mode == COOLING else 0)
            s += (a.indoor - a.weather.outdoor) * (0.5 if a.mode == HEATING else 0)
        elif prefer == "quiet":
            s += a.place.quiet * 26
        elif prefer == "close":
            s -= a.walk_min * 2.4
        elif prefer == "free":
            s -= a.nuisance.score * 0.75
            s += 18 if a.place.official else 0
        return -s

    return sorted(analyses, key=key)
