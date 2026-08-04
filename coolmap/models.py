"""CoolMap 도메인 모델."""

from __future__ import annotations

from dataclasses import dataclass, field

COOLING = "cooling"
HEATING = "heating"

# 카테고리 키 -> (표시명, 아이콘)
CATEGORIES: dict[str, tuple[str, str]] = {
    "library": ("도서관", "book"),
    "dept": ("백화점", "bag"),
    "underground": ("지하상가", "market"),
    "subway": ("지하철역", "train"),
    "gov": ("주민센터", "gov"),
    "bank": ("은행", "bank"),
    "cafe": ("카페", "cup"),
    "cinema": ("영화관", "film"),
    "market": ("전통시장", "market"),
    "hospital": ("병원 로비", "hospital"),
    "mall": ("복합쇼핑몰", "building"),
    "center": ("복지관", "building"),
    "store": ("편의점", "bag"),
    "bookstore": ("서점", "book"),
    "museum": ("미술관", "building"),
    "park": ("야외 쉼터", "tree"),
    "senior": ("경로당·마을회관", "building"),
    "busstop": ("버스정류장", "bus"),
    "mart": ("대형마트", "cart"),
}


@dataclass
class Place:
    id: str
    name: str
    category: str
    address: str
    lat: float
    lon: float
    modes: tuple[str, ...]
    summary: str
    why: str

    # 위치 표현
    inside_mall: bool = False       # 상가/건물 내부 업소 → 지도에서 화살표 표기
    unit: str = ""                  # "지하 1층 · B-12"
    floor_hint: str = ""

    # 운영
    open_from: int = 9              # 시(hour)
    open_to: int = 21               # 24 이상이면 익일까지
    official: bool = False          # 공식 지정 무더위/한파 쉼터
    always_open: bool = False
    weekend_closed: bool = False    # 주말 휴관 (관공서·은행 등)

    # 규모 / 환경
    seats: int = 60
    capacity: int = 200
    base_crowd: float = 0.35
    indoor_cool: float = 24.0       # 냉방 모드 실내 온도
    indoor_heat: float = 22.0       # 난방 모드 실내 온도
    humidity: int = 45
    airflow: str = "양호"
    aqi: int = 30

    # 사회적 요소 (민폐도 계산용)
    purchase_required: bool = False
    staff_pressure: float = 0.2     # 0..1 직원/주변 눈치
    quiet: float = 0.5              # 0..1 정숙도

    amenities: list[str] = field(default_factory=list)

    @property
    def latlon(self) -> tuple[float, float]:
        return self.lat, self.lon

    @property
    def category_label(self) -> str:
        return CATEGORIES.get(self.category, ("기타", "pin"))[0]

    @property
    def icon(self) -> str:
        return CATEGORIES.get(self.category, ("기타", "pin"))[1]

    def indoor_temp(self, mode: str) -> float:
        return self.indoor_cool if mode == COOLING else self.indoor_heat

    def supports(self, mode: str) -> bool:
        return mode in self.modes

    def hours_label(self) -> str:
        if self.always_open:
            return "24시간 운영"
        end = self.open_to % 24
        label = f"{self.open_from:02d}:00 – {end:02d}:00"
        return label + " (주말 휴관)" if self.weekend_closed else label

    def is_open(self, hour: int, weekday: int | None = None) -> bool:
        if self.always_open:
            return True
        if self.weekend_closed and weekday is not None and weekday >= 5:
            return False
        if self.open_to <= 24:
            return self.open_from <= hour < self.open_to
        return hour >= self.open_from or hour < (self.open_to - 24)

    def closing_in(self, hour: int, minute: int = 0) -> int | None:
        """마감까지 남은 분. 24시간 운영이면 None."""
        if self.always_open or not self.is_open(hour):
            return None
        end = self.open_to if self.open_to > hour else self.open_to + 24
        return int((end - hour) * 60 - minute)


@dataclass
class Event:
    id: str
    title: str
    lat: float
    lon: float
    radius: float          # 영향 반경 (미터)
    start_hour: int
    end_hour: int
    boost: float
    modes: tuple[str, ...]
    note: str
    weekend_only: bool = False

    @property
    def latlon(self) -> tuple[float, float]:
        return self.lat, self.lon

    def active(self, hour: int, weekday: int, mode: str) -> bool:
        if mode not in self.modes:
            return False
        if self.weekend_only and weekday < 5:
            return False
        return self.start_hour <= hour < self.end_hour

    def influence(self, latlon: tuple[float, float]) -> float:
        """장소가 이벤트 영향권에 든 정도 0..1."""
        from .geo import haversine

        dist = haversine(latlon, self.latlon)
        if dist >= self.radius:
            return 0.0
        return 1.0 - (dist / self.radius) ** 1.4


@dataclass
class Weather:
    outdoor: float
    feels: float
    humidity: int
    condition: str
    alert: str
