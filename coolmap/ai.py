"""CoolMap 예측 엔진.

- 혼잡도(사람 수) 예측: 시간대 프로필 × 요일 × 외기 × 이벤트 가중
- 민폐도 점수: 구매 압박, 시선, 혼잡, 좌석, 공식 쉼터 여부로 산출
- 쾌적 점수: 온도/습도/공기흐름/공기질/혼잡 가중 합

외부 모델 호출 없이 결정론적으로 동작하므로 언제나 같은 입력 → 같은 결과.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .data import EVENTS, USER_HOME, distance, walk_minutes, weather_for
from .models import COOLING, HEATING, Event, Place, Weather

# 카테고리별 방문 피크 (시, 가중치)
_PEAKS: dict[str, list[tuple[float, float]]] = {
    "library": [(11, 0.70), (15, 1.00), (19, 0.72)],
    "dept": [(13, 0.72), (17, 1.00), (19, 0.82)],
    "underground": [(12, 0.85), (18, 1.00)],
    "subway": [(8, 1.00), (12, 0.50), (18, 1.00)],
    "gov": [(10, 0.92), (14, 1.00)],
    "bank": [(11, 1.00), (14, 0.78)],
    "cafe": [(9, 0.62), (14, 1.00), (20, 0.72)],
    "cinema": [(15, 0.62), (20, 1.00)],
    "market": [(11, 0.90), (17, 1.00)],
    "hospital": [(10, 1.00), (14, 0.82)],
    "mall": [(14, 0.82), (18, 1.00)],
    "center": [(10, 0.92), (14, 1.00)],
    "store": [(12, 0.78), (19, 1.00), (22, 0.66)],
    "bookstore": [(15, 0.88), (19, 1.00)],
    "museum": [(11, 0.70), (14, 1.00)],
    "park": [(7, 0.58), (19, 1.00)],
}

# 주말 배수
_WEEKEND: dict[str, float] = {
    "dept": 1.30, "mall": 1.32, "cinema": 1.34, "market": 1.24, "museum": 1.28,
    "park": 1.30, "underground": 1.12, "bookstore": 1.18, "library": 1.10,
    "cafe": 1.15, "store": 1.05, "hospital": 0.72, "subway": 0.78,
    "gov": 0.10, "bank": 0.10, "center": 0.55,
}

CROWD_LEVELS = [
    (0.25, "매우 여유", "very_low"),
    (0.45, "여유", "low"),
    (0.62, "보통", "normal"),
    (0.80, "붐빔", "busy"),
    (1.01, "매우 붐빔", "very_busy"),
]

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
class CrowdForecast:
    ratio: float
    people: int
    level: str
    key: str
    headline: str
    detail: str
    event: Event | None
    event_share: float
    hourly: list[float]
    confidence: int
    open_now: bool

    @property
    def percent(self) -> int:
        return int(round(self.ratio * 100))

    @property
    def by_event(self) -> bool:
        return self.event is not None and self.event_share >= 0.08


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
    crowd: CrowdForecast
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
def _daypart(category: str, hour: float) -> float:
    """시간대 수요 계수 (0.45 ~ 1.15)."""
    peaks = _PEAKS.get(category, [(12, 1.0), (18, 0.8)])
    sigma = 2.7
    val = 0.0
    for ph, w in peaks:
        d = min(abs(hour - ph), 24 - abs(hour - ph))
        val = max(val, w * math.exp(-(d * d) / (2 * sigma * sigma)))
    return 0.45 + val * 0.70


def _weather_pull(mode: str, weather: Weather) -> float:
    """외기가 실내 쉼터 수요를 밀어 올리는 정도."""
    if mode == COOLING:
        return 1.0 + max(0.0, min(0.52, (weather.outdoor - 30.0) * 0.058))
    return 1.0 + max(0.0, min(0.52, (-weather.outdoor) * 0.048))


def _weekday_factor(category: str, weekday: int) -> float:
    if weekday >= 5:
        return _WEEKEND.get(category, 1.0)
    return 1.0


def active_events(mode: str, hour: int, weekday: int,
                  origin: tuple[float, float] | None = None,
                  within_m: float = 6000.0) -> list[Event]:
    """진행 중인 이벤트.

    origin 을 주면 그 주변 것만 남긴다. 그러지 않으면 사용자가 다른 도시에 있어도
    서울에 있는 이벤트 원이 지도에 그려진다.
    """
    live = [e for e in EVENTS if e.active(hour, weekday, mode)]
    if origin is None:
        return live
    from .geo import haversine

    return [e for e in live
            if haversine(origin, e.latlon) <= within_m + e.radius]


def _event_boost(place: Place, mode: str, hour: int, weekday: int) -> tuple[float, Event | None]:
    best = 0.0
    best_ev: Event | None = None
    for ev in active_events(mode, hour, weekday):
        infl = ev.influence(place.latlon)
        if infl <= 0:
            continue
        boost = ev.boost * infl
        if boost > best:
            best, best_ev = boost, ev
    return best, best_ev


def _raw_ratio(place: Place, mode: str, hour: int, weekday: int, weather: Weather) -> tuple[float, float, Event | None]:
    demand = _daypart(place.category, hour)
    pull = _weather_pull(mode, weather)
    if place.category == "park" and mode == COOLING and weather.outdoor >= 35:
        pull *= 0.78  # 폭염 정점에는 야외 쉼터 이용이 줄어든다
    week = _weekday_factor(place.category, weekday)
    boost, ev = _event_boost(place, mode, hour, weekday)
    ratio = place.base_crowd * demand * pull * week + boost
    return max(0.02, min(1.0, ratio)), boost, ev


def _level(ratio: float) -> tuple[str, str]:
    for limit, label, key in CROWD_LEVELS:
        if ratio < limit:
            return label, key
    return CROWD_LEVELS[-1][1], CROWD_LEVELS[-1][2]


def predict_crowd(
    place: Place,
    mode: str,
    hour: int,
    weekday: int,
    weather: Weather | None = None,
) -> CrowdForecast:
    weather = weather or weather_for(mode, hour)
    open_now = place.is_open(hour, weekday)
    ratio, boost, ev = _raw_ratio(place, mode, hour, weekday, weather)

    hourly = []
    for h in range(24):
        if not place.is_open(h, weekday):
            hourly.append(0.0)
            continue
        r, _, _ = _raw_ratio(place, mode, h, weekday, weather_for(mode, h))
        hourly.append(r)

    if not open_now:
        return CrowdForecast(
            ratio=0.0, people=0, level="운영 종료", key="closed",
            headline="지금은 운영 시간이 아니에요",
            detail=f"운영 시간 {place.hours_label()}",
            event=None, event_share=0.0, hourly=hourly, confidence=95, open_now=False,
        )

    level, key = _level(ratio)
    people = max(1, int(round(place.capacity * ratio)))
    event_share = boost / ratio if ratio > 0 else 0.0

    if boost >= 0.08 and ev is not None:
        headline = "사람이 이벤트로 인해 많아요"
        detail = f"{ev.title} ({ev.start_hour:02d}:00–{ev.end_hour:02d}:00) · {ev.note}"
    elif place.category == "subway" and hour in (7, 8, 9, 17, 18, 19):
        headline = "출퇴근 시간대라 유동 인구가 많아요"
        detail = "역사 특성상 30분 내 혼잡도가 빠르게 변합니다."
    elif _weather_pull(mode, weather) >= 1.28 and ratio >= 0.5:
        if mode == COOLING:
            headline = "폭염으로 실내 쉼터에 인원이 몰리고 있어요"
            detail = f"외기 {weather.outdoor}°C · {weather.alert or '고온 지속'} 영향"
        else:
            headline = "한파로 실내 체류 인원이 늘었어요"
            detail = f"외기 {weather.outdoor}°C · {weather.alert or '저온 지속'} 영향"
    elif ratio < 0.3:
        headline = "지금은 한산한 편이에요"
        detail = "좌석 확보가 쉬운 시간대입니다."
    else:
        headline = "평소와 비슷한 수준이에요"
        detail = f"{place.category_label} 평균 대비 {int((ratio / max(place.base_crowd, 0.01) - 1) * 100):+d}%"

    confidence = 88 + (4 if place.official else 0) - (7 if boost >= 0.08 else 0)
    confidence = max(70, min(97, confidence + (place.capacity // 700)))

    return CrowdForecast(
        ratio=ratio, people=people, level=level, key=key,
        headline=headline, detail=detail, event=ev if boost >= 0.08 else None,
        event_share=event_share, hourly=hourly, confidence=confidence, open_now=True,
    )


def score_nuisance(place: Place, crowd: CrowdForecast, hour: int, minute: int = 0) -> NuisanceScore:
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

    crowd_pen = int(round(max(0.0, crowd.ratio - 0.45) * 74))
    if crowd_pen:
        score += crowd_pen
        factors.append(("현재 혼잡도", crowd_pen))

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
    stay = base * (1 - score / 165.0) * (1.15 - crowd.ratio * 0.5)
    stay = int(max(10, round(stay / 5) * 5))
    if remain is not None:
        stay = min(stay, max(10, remain))

    tips: list[str] = []
    if place.official:
        tips.append("공식 지정 쉼터입니다. 눈치 보지 말고 이용하세요.")
    if place.purchase_required:
        tips.append("음료 1잔 주문 후 이용하면 부담이 크게 줄어요.")
    if crowd.ratio >= 0.7:
        tips.append("좌석 경쟁이 심한 시간대예요. 1인석 위주로 찾아보세요.")
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
    crowd: CrowdForecast,
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
    crowd_s = 100 - crowd.ratio * 95

    if CROWD_ENABLED:
        total = (temp_s * 0.32 + crowd_s * 0.26 + air_s * 0.14
                 + humid_s * 0.13 + aqi_s * 0.15)
    else:
        # 혼잡도 비활성 — 해당 가중치를 제외하고 정규화 (쾌적 점수가 미공개 값에 의존하지 않도록)
        total = (temp_s * 0.32 + air_s * 0.14 + humid_s * 0.13 + aqi_s * 0.15) / 0.74

    # 외기와의 격차 보너스 (쉼터로서의 가치)
    if mode == COOLING:
        total += max(0.0, min(5.0, (weather.outdoor - indoor) * 0.42))
    else:
        total += max(0.0, min(5.0, (indoor - weather.outdoor) * 0.16))

    if not crowd.open_now:
        total *= 0.55
    return int(max(0, min(100, round(total))))


#: 혼잡도(사람 수) 예측은 실데이터 확보 전까지 비활성 — UI 에서 'Coming Soon' 표시
CROWD_ENABLED = False


def live_weather(mode: str, hour: int, minute: int, latlon: tuple[float, float] | None = None) -> Weather:
    """기상청 실황이 있으면 실데이터, 없으면 모의 곡선."""
    from . import providers

    try:
        wp = providers.weather_provider()
        lat, lon = latlon or USER_HOME
        return wp.weather(lat, lon, mode, hour, minute)
    except Exception:
        return weather_for(mode, hour, minute)


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
    crowd = predict_crowd(place, mode, hour, weekday, weather)
    nuisance = ai_nuisance(place, mode, score_nuisance(place, crowd, hour, minute))
    comfort = comfort_score(place, mode, weather, crowd, target)
    indoor = place.indoor_temp(mode)
    # 실내 체감: 혼잡할수록 체감 온도가 올라간다(냉방)/내려간다(난방)
    if mode == COOLING:
        feels = indoor + crowd.ratio * 2.4 + (place.humidity - 45) * 0.04
    else:
        feels = indoor - crowd.ratio * 0.6 + 0.4
    meters = distance(origin or USER_HOME, place.latlon)
    return Analysis(
        place=place, mode=mode, weather=weather, crowd=crowd, nuisance=nuisance,
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
        if CROWD_ENABLED:
            s -= a.crowd.ratio * 22
        s -= min(a.walk_min, 40) * 0.55
        if not a.crowd.open_now:
            s -= 60
        if prefer == "cool":
            s += (a.weather.outdoor - a.indoor) * (1.4 if a.mode == COOLING else 0)
            s += (a.indoor - a.weather.outdoor) * (0.5 if a.mode == HEATING else 0)
        elif prefer == "quiet":
            s += a.place.quiet * 26
            if CROWD_ENABLED:
                s -= a.crowd.ratio * 24
        elif prefer == "close":
            s -= a.walk_min * 2.4
        elif prefer == "free":
            s -= a.nuisance.score * 0.75
            s += 18 if a.place.official else 0
        return -s

    return sorted(analyses, key=key)
