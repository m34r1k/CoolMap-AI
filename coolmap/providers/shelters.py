"""행정안전부 재난안전데이터공유플랫폼 — 무더위쉼터 연동.

safetydata.go.kr  /V2/api/DSSP-IF-10942  (전국 약 6만 건, 위경도 포함)

- 서버 측 필터가 없어서 전량(1000건 × 61페이지)을 1회 동기화한 뒤 디스크에 캐시한다.
- 이후 실행부터는 캐시에서 즉시 로드하고, 사용자 위치 반경으로만 걸러 쓴다.
- 실패하거나 키가 없으면 데모 데이터로 폴백한다.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from .. import secrets
from ..geo import haversine
from ..models import COOLING, HEATING, Place
from ..paths import cache_dir

SERVICE_ID = "DSSP-IF-10942"
BASE = "https://www.safetydata.go.kr/V2/api"
PAGE_SIZE = 1000
CACHE_TTL = 14 * 24 * 3600      # 2주

# FCLTY_TY 코드
TY_PUBLIC = "001"    # 행정복지센터 · 주민센터 · 복지관
TY_OUTDOOR = "002"   # 야외 쉼터 · 공원 정자
TY_SENIOR = "003"    # 경로당 · 마을회관 (전체의 약 83%)
TY_BANK = "004"      # 금융기관 (새마을금고 · 농협 등)

# 유형별 기본 운영시간 (데이터에 값이 없을 때)
_DEFAULT_HOURS = {
    TY_PUBLIC: (9, 18, True),
    TY_SENIOR: (9, 18, False),
    TY_BANK: (9, 16, True),
    TY_OUTDOOR: (0, 24, False),
}

# 순서가 곧 우선순위. 이름에 여러 키워드가 겹치는 경우가 많다.
#   '(40418)참바른병원버스정류장'  → 병원이 아니라 정류장
#   '아이엠뱅크경대병원지점'        → 병원이 아니라 은행
#   '우리은행종로구청지점'          → 구청이 아니라 은행
# 따라서 '무엇에 붙어 있는가'보다 '무엇인가'를 먼저 판정한다.
_NAME_RULES = [
    # 1) 정류장 계열 — 다른 시설 이름을 달고 있는 경우가 많아 가장 먼저 본다
    (("정류장", "정류소", "승강장", "버스쉼터"), "busstop"),
    # 2) 금융 — '뱅크' 표기도 잡는다
    (("금고", "농협", "은행", "뱅크", "신협", "수협", "축협", "저축은행"), "bank"),
    # 3) 대형마트 / 편의점
    (("이마트24", "GS25", "CU편", "세븐일레븐", "편의점"), "store"),
    (("이마트", "홈플러스", "롯데마트", "코스트코", "하나로마트", "농협마트"), "mart"),
    (("도서관",), "library"),
    (("경로당", "마을회관", "노인정", "어르신", "경로복지", "사랑채"), "senior"),
    (("보건진료소", "진료소", "보건지소", "보건소", "병원", "의원"), "hospital"),
    (("복지관", "복지회관", "복지센터", "문화의집", "체육센터", "체육관", "청소년센터",
      "문화센터", "기념관", "박물관", "미술관", "문예회관", "평생학습",
      "이동노동자", "교회", "성당", "사찰"), "center"),
    (("주민센터", "행정복지센터", "구청", "시청", "군청", "면사무소", "읍사무소", "동사무소",
      "민원센터", "우체국", "청사"), "gov"),
    (("전통시장", "상가"), "market"),
    # '쉼터' 는 실내에도 흔히 붙으므로 야외 판정에서 제외한다
    (("야외", "공원", "정자", "그늘막", "파고라", "물놀이"), "park"),
]

# 냉방설비 정보가 비어 있을 때 쓰는 유형별 실내 온도 추정치
_ASSUMED_INDOOR = {
    "bank": 24.5, "gov": 24.5, "library": 24.5, "center": 25.0,
    "store": 24.0, "mart": 23.5, "hospital": 24.0, "market": 26.5,
    "senior": 26.0, "busstop": 25.5,
}


def _hhmm_to_hour(v) -> int | None:
    if not v:
        return None
    s = str(v).strip()
    if len(s) != 4 or not s.isdigit():
        return None
    h = int(s[:2])
    return h if 0 <= h <= 24 else None


def _classify(name: str, fclty_ty: str) -> str:
    for keys, cat in _NAME_RULES:
        if any(k in name for k in keys):
            return cat
    return {TY_PUBLIC: "gov", TY_OUTDOOR: "park",
            TY_SENIOR: "senior", TY_BANK: "bank"}.get(fclty_ty, "center")


def record_to_place(r: dict, mode: str) -> Place | None:
    """API 레코드 → Place. 좌표가 없으면 버린다."""
    try:
        lat = float(r["LA"])
        lon = float(r["LO"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (33.0 <= lat <= 39.5 and 124.0 <= lon <= 132.0):
        return None

    name = (r.get("RSTR_NM") or "무더위쉼터").strip()
    ty = str(r.get("FCLTY_TY") or TY_SENIOR)
    category = _classify(name, ty)

    ac = r.get("COLR_HOLD_ARCNDTN") or 0
    fan = r.get("COLR_HOLD_ELEFN") or 0

    # 버스정류장은 두 종류다.
    #  · 냉방설비가 있는 '스마트쉼터/스마트승강장' — 밀폐형 부스라 실내로 본다
    #  · 그늘막만 있는 일반 정류장 — 야외
    outdoor = ty == TY_OUTDOOR or category == "park" or (category == "busstop" and not ac)
    people = r.get("USE_PSBL_NMPR") or 0
    area = r.get("AR") or 0

    d_from, d_to, d_weekend_closed = _DEFAULT_HOURS.get(ty, (9, 18, False))
    open_from = _hhmm_to_hour(r.get("WKDAY_OPER_BEGIN_TIME"))
    open_to = _hhmm_to_hour(r.get("WKDAY_OPER_END_TIME"))
    if open_from is None:
        open_from = d_from
    if open_to is None or open_to <= open_from:
        open_to = max(d_to, open_from + 1)

    weekend_flag = r.get("CHCK_MATTER_WKEND_HDAY_OPN_AT")
    weekend_closed = (weekend_flag == "N") if weekend_flag else d_weekend_closed
    night = r.get("CHCK_MATTER_NIGHT_OPN_AT") == "Y"
    # 0000~2400 처럼 하루 전체가 적힌 경우는 상시 개방으로 본다
    always_open = (outdoor or category == "busstop"
                   or open_to - open_from >= 23
                   or (night and open_to - open_from >= 20))

    # 실내 온도는 언제나 '추정치'다.
    # 원본의 에어컨/선풍기 '대수'는 신뢰도가 낮아 수치로 쓰지 않고,
    # 냉방설비 보유 여부(있음/없음)만 참고한다.
    has_cooling = bool(ac) or bool(fan)
    if outdoor:
        indoor_cool = 29.0
    else:
        base = _ASSUMED_INDOOR.get(category, 26.0)
        indoor_cool = base - (1.0 if ac else 0.0)

    airflow = "양호" if ac else ("보통" if fan else "정보 없음")

    amenities = []
    amenities.append("냉방설비 있음" if has_cooling else "냉방설비 정보 없음")
    if area:
        amenities.append(f"{area}㎡")
    if night:
        amenities.append("야간 개방")
    if weekend_flag == "Y":
        amenities.append("주말·공휴일 개방")
    if r.get("CHCK_MATTER_STAYNG_PSBL_AT") == "Y":
        amenities.append("숙박 가능")
    amenities.append("실내 온도는 추정치")

    seats = max(4, int(people) if people else 20)
    address = (r.get("RN_DTL_ADRES") or r.get("DTL_ADRES") or "").strip()

    # 난방 모드에서는 '무더위쉼터로 지정된 실내시설'로만 취급한다 (한파쉼터 미검증)
    if mode == HEATING:
        official = False
        summary = (f"{'야외' if outdoor else '실내'} 무더위쉼터로 지정된 시설입니다. "
                   "한파쉼터 지정 여부는 별도 데이터가 필요해 확인되지 않았습니다.")
        why = "무더위쉼터 데이터 기준으로 표시한 실내시설입니다. 방문 전 운영 여부를 확인하세요."
    else:
        official = True
        if category == "busstop":
            summary = ("행정안전부 지정 무더위쉼터로 등록된 버스정류장입니다. "
                       + ("냉방설비를 갖춘 밀폐형 스마트쉼터입니다."
                          if ac else "그늘막 형태의 야외 정류장입니다."))
        else:
            summary = ("행정안전부 지정 무더위쉼터입니다. "
                       + ("냉방설비를 갖추고 있습니다." if has_cooling
                          else "냉방설비 정보는 등록되어 있지 않습니다."))
        why = "공식 지정 무더위쉼터라 무료이며, 이용에 눈치가 보이지 않습니다."

    return Place(
        id=f"H{r.get('RSTR_FCLTY_NO')}",
        name=name,
        category=category,
        address=address,
        lat=lat,
        lon=lon,
        modes=(COOLING,) if mode == COOLING else (HEATING,),
        summary=summary,
        why=why,
        # 층·호수 정보가 없으므로 화살표 대신 건물 전체를 하이라이트한다
        inside_mall=False,
        unit="",
        floor_hint="",
        open_from=open_from,
        open_to=open_to,
        official=official,
        always_open=always_open,
        weekend_closed=weekend_closed,
        seats=seats,
        capacity=max(seats, int(people) if people else 40),
        base_crowd=0.3,
        indoor_cool=indoor_cool,
        indoor_heat=23.0 if not outdoor else 5.0,
        humidity=50,
        airflow=airflow,
        aqi=28,
        purchase_required=category in ("store", "mart"),
        staff_pressure={"bank": 0.45, "store": 0.55, "mart": 0.3, "gov": 0.05,
                        "senior": 0.25, "park": 0.0, "busstop": 0.0}.get(category, 0.15),
        quiet={"library": 0.9, "gov": 0.6, "senior": 0.4, "park": 0.25,
               "bank": 0.6, "busstop": 0.15, "mart": 0.2}.get(category, 0.5),
        amenities=amenities,
    )


class ShelterProvider(QObject):
    """무더위쉼터 전량 동기화 + 반경 조회."""

    progress = Signal(int, int)     # (받은 건수, 전체)
    ready = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._records: list[dict] = []
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="shelter")
        self._file = cache_dir("shelters") / f"{SERVICE_ID}.json"
        self._syncing = False
        self._error = ""
        self._fetched_at = 0.0
        self._load_cache()

    # -- 상태 -------------------------------------------------------------
    @property
    def has_key(self) -> bool:
        return bool(secrets.get("shelter_service_key"))

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._records)

    @property
    def loaded(self) -> bool:
        return self.count > 0

    @property
    def syncing(self) -> bool:
        return self._syncing

    @property
    def error(self) -> str:
        return self._error

    @property
    def age_days(self) -> float:
        return (time.time() - self._fetched_at) / 86400 if self._fetched_at else -1

    # -- 캐시 -------------------------------------------------------------
    def _load_cache(self) -> None:
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
            with self._lock:
                self._records = raw["records"]
            self._fetched_at = raw.get("fetched_at", 0)
        except (OSError, ValueError, KeyError):
            pass

    def _save_cache(self) -> None:
        try:
            with self._lock:
                data = {"fetched_at": time.time(), "records": self._records}
            self._file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self._fetched_at = data["fetched_at"]
        except OSError:
            pass

    def stale(self) -> bool:
        return not self.loaded or (time.time() - self._fetched_at) > CACHE_TTL

    # -- 동기화 -----------------------------------------------------------
    def sync(self, force: bool = False) -> None:
        if self._syncing or not self.has_key:
            return
        if not force and not self.stale():
            return
        self._syncing = True
        self._pool.submit(self._do_sync)

    def _fetch_page(self, page: int) -> tuple[list[dict], int]:
        q = urllib.parse.urlencode({
            "serviceKey": secrets.get("shelter_service_key"),
            "returnType": "json",
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
        })
        req = urllib.request.Request(f"{BASE}/{SERVICE_ID}?{q}",
                                     headers={"User-Agent": "CoolMapAI/1.0"})
        with urllib.request.urlopen(req, timeout=45) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        if d.get("header", {}).get("resultCode") != "00":
            raise RuntimeError(d.get("header", {}).get("errorMsg", "unknown error"))
        return d.get("body") or [], int(d.get("totalCount") or 0)

    #: 캐시에 담을 필드만 남겨 용량을 줄인다
    _KEEP = ("RSTR_FCLTY_NO", "RSTR_NM", "LA", "LO", "RN_DTL_ADRES", "DTL_ADRES",
             "FCLTY_TY", "USE_PSBL_NMPR", "AR", "COLR_HOLD_ARCNDTN", "COLR_HOLD_ELEFN",
             "WKDAY_OPER_BEGIN_TIME", "WKDAY_OPER_END_TIME",
             "CHCK_MATTER_WKEND_HDAY_OPN_AT", "CHCK_MATTER_NIGHT_OPN_AT",
             "CHCK_MATTER_STAYNG_PSBL_AT")

    def _do_sync(self) -> None:
        try:
            first, total = self._fetch_page(1)
            rows = [{k: r.get(k) for k in self._KEEP if r.get(k) is not None}
                    for r in first]
            pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
            self.progress.emit(len(rows), total)

            failed: list[int] = []
            for page in range(2, pages + 1):
                body = None
                for attempt in range(3):        # 공개 API 라 간헐적으로 끊긴다
                    try:
                        body, _ = self._fetch_page(page)
                        break
                    except Exception as exc:
                        self._error = f"p{page} {type(exc).__name__}: {exc}"
                        time.sleep(0.8 * (attempt + 1))
                if body is None:
                    failed.append(page)
                    continue
                rows.extend({k: r.get(k) for k in self._KEEP if r.get(k) is not None}
                            for r in body)
                self.progress.emit(len(rows), total)
                time.sleep(0.08)      # 공공 API 배려

            if rows:
                with self._lock:
                    self._records = rows
                self._save_cache()
                # 일부 페이지가 빠졌으면 그 사실을 남긴다 (조용히 성공 처리하지 않는다)
                self._error = (f"{len(failed)}개 페이지 누락 (총 {len(rows)}/{total}건)"
                               if failed else "")
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
        finally:
            self._syncing = False
        self.ready.emit()

    # -- 조회 -------------------------------------------------------------
    def nearby(self, origin: tuple[float, float], mode: str,
               radius_m: float = 3000, limit: int = 60) -> list[Place]:
        """사용자 위치 반경 내 쉼터를 가까운 순으로."""
        with self._lock:
            records = self._records
        if not records:
            return []

        lat0, lon0 = origin
        # 위경도 사각형으로 1차 필터 (haversine 호출 최소화)
        dlat = radius_m / 111_000.0
        dlon = radius_m / 88_000.0
        near = []
        for r in records:
            try:
                la, lo = float(r["LA"]), float(r["LO"])
            except (KeyError, TypeError, ValueError):
                continue
            if abs(la - lat0) > dlat or abs(lo - lon0) > dlon:
                continue
            d = haversine((lat0, lon0), (la, lo))
            if d <= radius_m:
                near.append((d, r))

        near.sort(key=lambda x: x[0])
        places: list[Place] = []
        seen: set[str] = set()
        for _d, r in near[:limit * 2]:
            p = record_to_place(r, mode)
            if p and p.id not in seen:
                seen.add(p.id)
                places.append(p)
            if len(places) >= limit:
                break
        return places

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def clear_cache(self) -> None:
        with self._lock:
            self._records = []
        self._fetched_at = 0
        try:
            self._file.unlink()
        except OSError:
            pass
