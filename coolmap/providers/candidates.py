"""지도에 이름만 떠 있는 장소 → AI 추정 쉼터.

지도 타일에는 '○○하나로마트' 처럼 상호가 찍혀 있는데, 행정안전부 지정
쉼터가 아니면 앱에서는 아무 표시도 하지 않는다. 사용자 눈에는
"저기 분명 시원할 텐데 왜 안 뜨지?" 로 보인다.

그래서 그 이름표의 원본 데이터(OSM POI)를 가져와, Gemini 가 상호명과
시설 종류를 읽고 '더위·추위를 피해 잠시 머무를 수 있는 실내 공간인지'
판단한다. 맞다고 보면 추가로 하이라이트한다.

원칙
  · 공식 지정 쉼터와 절대 섞지 않는다 (official=False, ai_guess=True)
  · 애매하면 표시하지 않는다 — 헛걸음이 미표시보다 나쁘다
  · 판단은 상호 단위로 캐시한다 ('GS25 판교점' 을 매번 물어볼 이유가 없다)
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from .. import secrets
from ..geo import haversine
from ..models import CATEGORIES, COOLING, HEATING, Place
from ..paths import cache_dir
from . import overpass
from .shelters import assumed_indoor

CACHE_VERSION = 1    # _ALLOW 나 질의를 바꾸면 올린다 (오래된 셀 캐시를 버린다)

CELL = 0.01          # 약 1.1km × 0.9km — 건물 캐시와 같은 격자
MAX_CELLS = 42       # 반경 2.5km 를 덮는 데 필요한 만큼
MAX_NEW_CELLS = 6    # 한 번에 새로 요청할 셀 수 (가까운 곳부터 채운다)
FAIL_COOLDOWN = 180  # 실패한 셀 재시도 대기 (초)

SCAN_LIMIT = 140     # 한 번에 판단 대상으로 올릴 POI 수
BATCH = 25           # Gemini 한 번에 물어볼 개수
MAX_INFLIGHT = 3     # 동시에 떠 있을 배치 수
MIN_CONFIDENCE = 62  # 이 아래는 지도에 올리지 않는다
ASK_COOLDOWN = 120   # 판단 요청이 실패한 뒤 다시 물어보기까지 (초)

# 질의는 키 단위로만 건다.
#   값까지 정규식으로 거르면 문(statement)이 늘어나 공개 미러가 504 를 낸다.
#   (실제로 8종 × node/way = 16문은 응답을 못 받았고, 아래 형태는 2초에 끝났다)
# 값 선별은 아래 _ALLOW 로 이 쪽에서 한다 — 서버도 편하고, 규칙을 읽고
# 고치기도 쉽다.
_QUERY_KEYS = ("shop", "amenity", "tourism")
_QUERY_EXTRA = (
    'way["name"]["building"~"^(retail|commercial|public|civic)$"]{bbox};',
    'node["name"]["railway"="station"]{bbox};',
    'way["name"]["railway"="station"]{bbox};',
    'way["name"]["leisure"~"^(sports_centre|fitness_centre)$"]{bbox};',
    'way["name"]["office"="government"]{bbox};',
)

# 여기 없는 값은 Gemini 에게 물어보지도 않는다.
#
# 기준은 '볼일 없이 들어가 있어도 되는가'다. 편의점·카페·은행·식당은
# 구매나 용무가 사실상 전제라 뺐다. 시험 삼아 넣어 봤더니 판교역 한 구역에서만
# 카페 10곳·편의점 9곳이 잡혀 정작 쓸모 있는 마트와 도서관이 묻혔다.
# (은행은 공식 지정된 곳이 이미 무더위쉼터 데이터로 들어오므로, 지정되지
#  않은 지점까지 추정으로 띄울 이유가 없다)
_ALLOW: dict[str, set[str]] = {
    "shop": {"supermarket", "department_store", "mall", "wholesale",
             "variety_store", "books", "doityourself"},
    "amenity": {"library", "community_centre", "townhall", "social_facility",
                "arts_centre", "theatre", "cinema", "marketplace",
                "public_bath", "college", "university", "post_office"},
    "tourism": {"museum", "gallery", "aquarium"},
    "leisure": {"sports_centre"},
    "office": {"government"},
    "railway": {"station"},
    "public_transport": {"station"},
    "building": {"retail", "commercial", "public", "civic"},
}

# POI 태그에서 '무엇인가'를 뽑을 때 보는 순서.
# building 은 가장 뒤 — shop/amenity 가 있으면 그쪽이 훨씬 구체적이다.
_KIND_KEYS = ("shop", "amenity", "tourism", "leisure", "railway",
              "public_transport", "office", "building")


# ---------------------------------------------------------------------------
# Gemini 판단
# ---------------------------------------------------------------------------

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.0-flash"]

RUBRIC = """당신은 지도에 찍힌 상호를 보고 '더위·추위를 피할 수 있는 곳'을
골라내는 심사자입니다.

상호명과 OSM 시설 종류 목록을 받습니다. 각 항목이
'공식 지정 쉼터는 아니지만, 일반인이 잠시 더위나 추위를 피해 머무를 수 있는
냉난방되는 실내 공간인가'를 판단하세요.

**핵심 기준: 아무것도 사지 않고, 볼일도 없이 들어가 앉아 있어도
괜찮은 곳인가.** 여기에 해당해야 usable=true 입니다.

usable = true 로 볼 만한 곳
  · 대형마트·하나로마트·백화점·복합쇼핑몰·지하상가·대형서점
      → 매장이 넓어 둘러보는 사람과 구분되지 않고, 냉난방이 확실하다
  · 도서관·주민센터·행정복지센터·복지관·문화센터·박물관·미술관
      → 누구나 들어가도 되는 공공 공간
  · 지하철역·기차역 대합실
      → 냉난방되고 통행이 자유롭다
  · 공공 체육센터·구민회관

usable = false 로 두어야 할 곳
  · 구매나 용무가 사실상 전제인 곳 — 편의점, 카페, 식당, 주점, 은행,
    병원, 미용실, 학원. 잠깐은 되지만 '쉼터'라고 안내할 수는 없다
  · 실내가 아닌 것 — 야외 주차장, 공터, 도로, 교량, 야외 운동장
  · 외부인이 들어갈 수 없는 곳 — 사무실 전용 빌딩, 공장, 창고, 물류센터,
    학교, 유치원, 군부대, 관사, 연구소, 회원제 시설
  · 주거시설 — 아파트, 빌라, 오피스텔, 기숙사
  · 종교시설 중 상시 개방이 아닌 곳
  · 상호만으로 무엇인지 알 수 없는 곳 (예: '○○빌딩', '○○프라자',
    '○○타워' 처럼 업종을 알 수 없는 이름)

**추측으로 usable=true 를 남발하지 마세요.**
이 결과는 지도에 '여기 들어가면 시원해요' 로 표시됩니다.
사용자가 찾아갔는데 못 들어가면 그냥 안 띄운 것보다 나쁩니다.
확신이 서지 않으면 usable=false 로 두세요.

confidence 는 판단의 확신도(0~100)입니다.
전국구 브랜드처럼 무엇인지 분명하면 높게, 지역 상호라 짐작만 되면 낮게 주세요.

category 는 주어진 목록에서 가장 가까운 것 하나를 고르세요.
note 는 왜 그렇게 판단했는지 한국어 한 문장(40자 이내)으로 적으세요."""

SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "usable": {"type": "boolean"},
                    "category": {"type": "string", "enum": sorted(CATEGORIES)},
                    "confidence": {"type": "integer"},
                    "note": {"type": "string"},
                },
                "required": ["i", "usable", "category", "confidence", "note"],
            },
        }
    },
    "required": ["results"],
}


def _judge_key(name: str, kind: str) -> str:
    """판단 캐시 키 — 상호명 + 종류.

    지점명(판교점/서현점)이 달라도 같은 브랜드면 판단이 같지만,
    이름을 함부로 다듬으면 '○○마트'와 '○○마트타워'가 섞인다.
    그냥 이름 전체로 캐시하고, 어차피 한 번 물어보면 영구 보관한다.
    """
    return hashlib.sha1(f"{name}|{kind}".encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Place 합성
# ---------------------------------------------------------------------------

# 유형별 기본 운영시간 (OSM opening_hours 는 형식이 제각각이라 쓰지 않는다).
# 마지막 값은 '주말 휴관'. 관공서·은행만 해당한다 — 도서관·박물관은 오히려
# 주말에 열고 월요일에 쉬는 곳이 많아, 주말 휴관으로 잡으면 정작 필요한
# 토·일에 지도에서 사라진다.
_HOURS: dict[str, tuple[int, int, bool]] = {
    "mart": (10, 23, False),
    "store": (0, 24, False),
    "dept": (10, 20, False),
    "mall": (10, 22, False),
    "underground": (10, 21, False),
    "bookstore": (10, 22, False),
    "cafe": (8, 22, False),
    "cinema": (10, 24, False),
    "market": (9, 20, False),
    "subway": (5, 24, False),
    "library": (9, 21, False),
    "museum": (10, 18, False),
    "gov": (9, 18, True),
    "bank": (9, 16, True),
    "hospital": (9, 18, False),
    "center": (9, 21, False),
    "senior": (9, 18, False),
    "park": (0, 24, False),
    "busstop": (0, 24, False),
}

# 공식 쉼터에는 없는 유형이라 shelters 쪽 추정표에 빠져 있는 것들 (냉방, 난방)
_EXTRA_INDOOR: dict[str, tuple[float, float]] = {
    "dept": (23.5, 23.0),
    "mall": (24.0, 23.0),
    "underground": (25.0, 21.0),
    "bookstore": (24.5, 23.0),
    "cinema": (23.5, 23.0),
    "museum": (24.0, 23.0),
    "cafe": (24.0, 23.0),
    "subway": (25.5, 20.0),      # 대합실 기준 (승강장은 더 덥고 춥다)
    "park": (29.0, 5.0),
}


def _indoor(category: str, mode: str) -> float:
    extra = _EXTRA_INDOOR.get(category)
    if extra is not None:
        return extra[0] if mode == COOLING else extra[1]
    return assumed_indoor(category, mode)

# '구매가 사실상 전제'인 곳만. 대형마트·백화점·서점은 사지 않고 둘러봐도
# 아무도 신경 쓰지 않으므로 넣지 않는다 (넣으면 민폐도가 부당하게 뛴다).
_PURCHASE = {"store", "cafe"}

_STAFF = {"bank": 0.5, "store": 0.6, "cafe": 0.65, "mart": 0.35, "dept": 0.3,
          "mall": 0.3, "gov": 0.15, "library": 0.15, "museum": 0.25,
          "hospital": 0.5, "senior": 0.4, "subway": 0.1, "underground": 0.15,
          "park": 0.05, "busstop": 0.05}

_QUIET = {"library": 0.9, "museum": 0.8, "gov": 0.6, "bank": 0.6, "hospital": 0.7,
          "cafe": 0.4, "mart": 0.2, "store": 0.2, "market": 0.15, "subway": 0.15,
          "busstop": 0.15, "park": 0.25}


#: 이름이 같고 이 거리 안이면 같은 시설로 본다 (미터).
DUPE_M = 600.0
#: 역은 출입구·승강장·노선별로 따로 등록돼 1km 넘게 떨어져 나오기도 한다.
DUPE_M_STATION = 2500.0


def _is_dupe(poi: dict, taken: list[Place]) -> bool:
    """이미 담은 것과 같은 시설인지.

    하나의 시설이 node 와 way 로 두 번, 역이라면 노선 수만큼 더 들어온다.
    이름은 반드시 표시용 이름끼리 비교해야 한다 — 원본은 '성남',
    표시용은 '성남역' 이라 그냥 비교하면 영영 안 걸린다.
    """
    name = _display_name(poi["name"], poi.get("kind", "")).replace(" ", "")
    limit = DUPE_M_STATION if poi.get("kind", "").endswith("=station") else DUPE_M
    for p in taken:
        if p.name.replace(" ", "") == name and haversine(
                (poi["lat"], poi["lon"]), p.latlon) <= limit:
            return True
    return False


def _display_name(name: str, kind: str) -> str:
    """지도 라벨로 쓸 이름.

    역은 OSM 에 '판교', '성남' 처럼 역 이름만 들어 있어서 그대로 쓰면
    무엇인지 알 수 없다.
    """
    if kind.endswith("=station") and not name.endswith(("역", "Station", "station")):
        return f"{name}역"
    return name


def _kind_of(tags: dict) -> str:
    """'무엇인가'를 하나 뽑는다. 허용 목록에 없으면 빈 문자열."""
    for k in _KIND_KEYS:
        v = tags.get(k)
        if v and v in _ALLOW.get(k, ()):
            return f"{k}={v}"
    return ""


def _poi_to_place(poi: dict, judgment: dict, mode: str) -> Place:
    """OSM POI + AI 판단 → Place."""
    category = judgment.get("category") or "center"
    if category not in CATEGORIES:
        category = "center"
    conf = int(judgment.get("confidence", 0))
    note = (judgment.get("note") or "").strip()

    open_from, open_to, weekend_closed = _HOURS.get(category, (9, 21, False))
    always_open = open_to - open_from >= 23

    label = CATEGORIES[category][0]
    return Place(
        id=poi["id"],
        name=_display_name(poi["name"], poi.get("kind", "")),
        category=category,
        address=poi.get("addr", ""),
        lat=poi["lat"],
        lon=poi["lon"],
        modes=(mode,),
        summary=(f"지도에 표시된 상호를 보고 AI 가 추정한 {label}입니다. "
                 "공식 지정 쉼터가 아니므로 운영시간과 이용 가능 여부는 "
                 "현장에서 확인하세요."),
        why=note or "냉난방되는 실내 공간으로 판단했습니다.",
        inside_mall=False,
        open_from=open_from,
        open_to=open_to,
        official=False,
        always_open=always_open,
        weekend_closed=weekend_closed,
        ai_guess=True,
        ai_confidence=conf,
        seats=30,
        capacity=80,
        base_crowd=0.4,
        indoor_cool=_indoor(category, COOLING),
        indoor_heat=_indoor(category, HEATING),
        humidity=50,
        airflow="정보 없음",
        aqi=30,
        purchase_required=category in _PURCHASE,
        staff_pressure=_STAFF.get(category, 0.35),
        quiet=_QUIET.get(category, 0.5),
        amenities=[f"AI 추정 (확신도 {conf}%)", "공식 지정 쉼터 아님",
                   f"지도 분류: {poi.get('kind', '')}", "실내 온도는 추정치"],
    )


# ---------------------------------------------------------------------------


def _cell_of(lat: float, lon: float) -> tuple[int, int]:
    return int(math.floor(lat / CELL)), int(math.floor(lon / CELL))


def _cell_bbox(cell: tuple[int, int]) -> tuple[float, float, float, float]:
    la, lo = cell
    return la * CELL, lo * CELL, (la + 1) * CELL, (lo + 1) * CELL


def _cell_center(cell: tuple[int, int]) -> tuple[float, float]:
    s, w, n, e = _cell_bbox(cell)
    return (s + n) / 2, (w + e) / 2


def _cell_query(cell: tuple[int, int]) -> str:
    s, w, n, e = _cell_bbox(cell)
    bbox = f"({s},{w},{n},{e})"
    parts = []
    for key in _QUERY_KEYS:
        parts.append(f'node["name"]["{key}"]{bbox};')
        parts.append(f'way["name"]["{key}"]{bbox};')
    parts.extend(t.format(bbox=bbox) for t in _QUERY_EXTRA)
    return f'[out:json][timeout:50];({"".join(parts)});out center 600;'


class CandidateProvider(QObject):
    """OSM 상호 수집 + Gemini 판단 → AI 추정 쉼터."""

    updated = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._cells: dict[tuple[int, int], list[dict]] = {}
        self._pending: set[tuple[int, int]] = set()
        self._failed: dict[tuple[int, int], float] = {}
        self._judged: dict[str, dict] = {}
        self._asking: set[str] = set()
        self._inflight = 0
        self._fail_until = 0.0

        self._poi_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="poi")
        self._ai_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="poi-ai")
        self._dir = cache_dir("candidates")
        self._judge_file = self._dir / "judgments.json"
        self._enabled = True
        self._error = ""
        self._calls = 0
        self._load_judgments()

    # -- 상태 --------------------------------------------------------------
    @property
    def has_key(self) -> bool:
        return bool(secrets.gemini_key())

    @property
    def enabled(self) -> bool:
        return self._enabled and self.has_key

    def set_enabled(self, on: bool) -> None:
        self._enabled = on

    @property
    def error(self) -> str:
        return self._error

    @property
    def calls(self) -> int:
        return self._calls

    def stats(self) -> tuple[int, int]:
        """(판단한 상호 수, 그중 쉼터로 인정한 수)"""
        with self._lock:
            total = len(self._judged)
            ok = sum(1 for j in self._judged.values()
                     if j.get("usable") and j.get("confidence", 0) >= MIN_CONFIDENCE)
        return total, ok

    def busy(self) -> bool:
        with self._lock:
            return bool(self._pending) or self._inflight > 0

    # -- 판단 캐시 ---------------------------------------------------------
    def _load_judgments(self) -> None:
        try:
            data = json.loads(self._judge_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._judged = data
        except (OSError, ValueError):
            pass

    def _save_judgments(self) -> None:
        try:
            with self._lock:
                data = dict(self._judged)
            self._judge_file.write_text(json.dumps(data, ensure_ascii=False),
                                        encoding="utf-8")
        except OSError:
            pass

    # -- POI 수집 ----------------------------------------------------------
    def _cell_path(self, cell: tuple[int, int]):
        return self._dir / f"poi_{cell[0]}_{cell[1]}.json"

    def _cell_items(self, cell: tuple[int, int]) -> list[dict] | None:
        with self._lock:
            got = self._cells.get(cell)
        if got is not None:
            return got
        try:
            raw = json.loads(self._cell_path(cell).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        # 선별 규칙(_ALLOW)이 바뀌면 저장해 둔 목록도 더 이상 맞지 않는다.
        # 버전이 다르면 없는 셈 치고 다시 받는다.
        if not isinstance(raw, dict) or raw.get("v") != CACHE_VERSION:
            return None
        got = raw.get("items") or []
        with self._lock:
            self._cells[cell] = got
        return got

    def _request_cell(self, cell: tuple[int, int]) -> None:
        with self._lock:
            if cell in self._pending:
                return
            if time.time() - self._failed.get(cell, 0) < FAIL_COOLDOWN:
                return
            self._pending.add(cell)
        self._poi_pool.submit(self._fetch_cell, cell)

    def _fetch_cell(self, cell: tuple[int, int]) -> None:
        try:
            items = _parse_pois(overpass.request(_cell_query(cell)))
            try:
                self._cell_path(cell).write_text(
                    json.dumps({"v": CACHE_VERSION, "items": items},
                               ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
            with self._lock:
                self._cells[cell] = items
                self._failed.pop(cell, None)
                while len(self._cells) > MAX_CELLS * 3:
                    self._cells.pop(next(iter(self._cells)))
            self._error = ""
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            with self._lock:
                self._failed[cell] = time.time()
        finally:
            with self._lock:
                self._pending.discard(cell)
        self.updated.emit()

    # -- 조회 --------------------------------------------------------------
    def nearby(self, origin: tuple[float, float], mode: str,
               radius_m: float = 2500, limit: int = 40) -> list[Place]:
        """반경 안에서 AI 가 쉼터로 인정한 장소.

        아직 판단하지 않은 상호는 백그라운드로 물어보고, 이번 호출에서는
        빼고 돌려준다. 판단이 끝나면 updated 신호로 다시 그리게 한다.
        """
        if not self.enabled:
            return []

        lat0, lon0 = origin
        dlat = radius_m / 111_000.0
        dlon = radius_m / 88_000.0
        c0 = _cell_of(lat0 - dlat, lon0 - dlon)
        c1 = _cell_of(lat0 + dlat, lon0 + dlon)
        if (c1[0] - c0[0] + 1) * (c1[1] - c0[1] + 1) > MAX_CELLS:
            return []

        pois: list[tuple[float, dict]] = []
        missing: list[tuple[float, tuple[int, int]]] = []
        for la in range(c0[0], c1[0] + 1):
            for lo in range(c0[1], c1[1] + 1):
                cell = (la, lo)
                items = self._cell_items(cell)
                if items is None:
                    missing.append((haversine(origin, _cell_center(cell)), cell))
                    continue
                for poi in items:
                    d = haversine(origin, (poi["lat"], poi["lon"]))
                    if d <= radius_m:
                        pois.append((d, poi))

        # 가까운 구역부터, 한 번에 몇 개씩만 받는다.
        # 반경을 넓히면 구역이 수십 개가 되는데 한꺼번에 몰면
        # Overpass 에도 무례하고 정작 눈앞의 구역이 늦게 채워진다.
        missing.sort(key=lambda x: x[0])
        for _d, cell in missing[:MAX_NEW_CELLS]:
            self._request_cell(cell)

        pois.sort(key=lambda x: x[0])
        places: list[Place] = []
        unknown: list[dict] = []
        for _d, poi in pois[:SCAN_LIMIT]:
            key = _judge_key(poi["name"], poi["kind"])
            with self._lock:
                j = self._judged.get(key)
                asking = key in self._asking
            if j is None:
                if not asking:
                    unknown.append(poi)
                continue
            if not j.get("usable"):
                continue
            if int(j.get("confidence", 0)) < MIN_CONFIDENCE:
                continue
            # 같은 시설이 node 와 way 로 두 번 들어오는 일이 흔하다
            # (역·행정복지센터가 점과 건물 양쪽으로 등록돼 있다)
            if _is_dupe(poi, places):
                continue
            if len(places) < limit:
                places.append(_poi_to_place(poi, j, mode))

        if unknown:
            self._ask(unknown)
        return places

    def _ask(self, pois: list[dict]) -> None:
        """아직 판단하지 않은 상호를 배치로 물어본다."""
        # 키가 잘못됐거나 한도를 넘긴 경우, 화면을 새로 그릴 때마다 다시
        # 물어보면 계속 두들기게 된다. 실패하면 잠시 쉰다.
        if time.time() < self._fail_until:
            return
        seen: dict[str, dict] = {}
        for poi in pois:
            seen.setdefault(_judge_key(poi["name"], poi["kind"]), poi)

        batch: list[tuple[str, dict]] = []
        for key, poi in seen.items():
            with self._lock:
                if key in self._asking or key in self._judged:
                    continue
                if self._inflight >= MAX_INFLIGHT:
                    break
                self._asking.add(key)
            batch.append((key, poi))
            if len(batch) >= BATCH:
                self._submit(batch)
                batch = []
        if batch:
            self._submit(batch)

    def _submit(self, batch: list[tuple[str, dict]]) -> None:
        with self._lock:
            self._inflight += 1
        self._ai_pool.submit(self._judge, batch)

    def _judge(self, batch: list[tuple[str, dict]]) -> None:
        listing = "\n".join(
            f"{i}. 상호: {poi['name']} / 지도 분류: {poi['kind']}"
            for i, (_k, poi) in enumerate(batch)
        )
        prompt = (f"다음 {len(batch)}곳을 판단하세요. i 는 아래 번호와 같아야 합니다.\n\n"
                  f"{listing}")
        payload = {
            "systemInstruction": {"parts": [{"text": RUBRIC}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
            },
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        results = None
        for model in MODELS:
            try:
                req = urllib.request.Request(
                    API.format(model=model),
                    data=body,
                    headers={"Content-Type": "application/json",
                             "x-goog-api-key": secrets.gemini_key()},
                )
                with urllib.request.urlopen(req, timeout=90) as r:
                    raw = json.loads(r.read().decode("utf-8", "replace"))
                text = raw["candidates"][0]["content"]["parts"][0]["text"]
                results = json.loads(text).get("results") or []
                self._calls += 1
                self._error = ""
                break
            except Exception as exc:
                self._error = f"{type(exc).__name__}: {exc}"

        if results is None:
            self._fail_until = time.time() + ASK_COOLDOWN
        else:
            self._fail_until = 0.0
            with self._lock:
                for item in results:
                    try:
                        idx = int(item.get("i", -1))
                    except (TypeError, ValueError):
                        continue
                    if not 0 <= idx < len(batch):
                        continue
                    self._judged[batch[idx][0]] = {
                        "usable": bool(item.get("usable")),
                        "category": str(item.get("category") or "center"),
                        "confidence": max(0, min(100, int(item.get("confidence", 0)))),
                        "note": str(item.get("note") or "").strip()[:120],
                        # 무엇을 물어봤는지 남겨 두면 캐시를 사람이 들여다볼 수 있다
                        "name": batch[idx][1]["name"],
                    }
            self._save_judgments()

        with self._lock:
            for key, _poi in batch:
                self._asking.discard(key)
            self._inflight = max(0, self._inflight - 1)
        self.updated.emit()

    # -- 정리 --------------------------------------------------------------
    def shutdown(self) -> None:
        self._poi_pool.shutdown(wait=False, cancel_futures=True)
        self._ai_pool.shutdown(wait=False, cancel_futures=True)

    def cache_count(self) -> int:
        return len(list(self._dir.glob("poi_*.json")))

    def clear_cache(self) -> None:
        with self._lock:
            self._cells.clear()
            self._failed.clear()
            self._judged.clear()
        for p in self._dir.glob("*.json"):
            try:
                p.unlink()
            except OSError:
                pass


def _parse_pois(data: dict) -> list[dict]:
    """Overpass 응답 → {id, name, kind, lat, lon, addr}."""
    out: list[dict] = []
    seen: set[str] = set()
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name or len(name) > 60:
            continue
        if el.get("type") == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            c = el.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue

        kind = _kind_of(tags)
        if not kind:
            continue        # 식당·약국처럼 쉼터로 볼 수 없는 종류

        pid = f"G{el.get('type', 'n')[0]}{el.get('id')}"
        if pid in seen:
            continue
        seen.add(pid)

        addr = " ".join(x for x in (
            tags.get("addr:province") or tags.get("addr:city"),
            tags.get("addr:district"),
            tags.get("addr:street"),
            tags.get("addr:housenumber"),
        ) if x)
        out.append({"id": pid, "name": name, "kind": kind,
                    "lat": float(lat), "lon": float(lon), "addr": addr})
    return out
