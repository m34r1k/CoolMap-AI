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
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from .. import secrets
from ..geo import haversine
from ..models import COOLING, HEATING, Place
from ..paths import cache_dir

BASE = "https://www.safetydata.go.kr/V2/api"
PAGE_SIZE = 1000
CACHE_TTL = 14 * 24 * 3600      # 2주


@dataclass(frozen=True)
class Dataset:
    """쉼터 데이터셋 정의.

    무더위쉼터와 한파쉼터는 같은 플랫폼인데도 필드명이 전혀 다르다
    (RSTR_NM vs REARE_NM, LA/LO vs LAT/LOT ...). 여기서 원본 필드명을
    공통 이름으로 매핑해 두고, 나머지 로직은 공통 형태만 다룬다.
    """

    service_id: str
    secret_key: str
    mode: str
    label: str
    id_prefix: str
    fields: dict[str, str]

    @property
    def keep(self) -> tuple[str, ...]:
        return tuple(self.fields.values())


#: 행정안전부 무더위쉼터 (냉방)
HEAT_SHELTERS = Dataset(
    service_id="DSSP-IF-10942",
    secret_key="shelter_service_key",
    mode=COOLING,
    label="행정안전부 무더위쉼터",
    id_prefix="H",
    fields={
        "no": "RSTR_FCLTY_NO", "name": "RSTR_NM",
        "lat": "LA", "lon": "LO",
        "road_addr": "RN_DTL_ADRES", "addr": "DTL_ADRES",
        "type": "FCLTY_TY", "capacity": "USE_PSBL_NMPR", "area": "AR",
        "ac": "COLR_HOLD_ARCNDTN", "fan": "COLR_HOLD_ELEFN",
        "wkday_from": "WKDAY_OPER_BEGIN_TIME", "wkday_to": "WKDAY_OPER_END_TIME",
        "weekend_open": "CHCK_MATTER_WKEND_HDAY_OPN_AT",
        "night_open": "CHCK_MATTER_NIGHT_OPN_AT",
        "stay_ok": "CHCK_MATTER_STAYNG_PSBL_AT",
    },
)

#: 행정안전부 한파쉼터 (난방)
COLD_SHELTERS = Dataset(
    service_id="DSSP-IF-10804",
    secret_key="cold_shelter_service_key",
    mode=HEATING,
    label="행정안전부 한파쉼터",
    id_prefix="C",
    fields={
        "no": "REARE_FCLT_NO", "name": "REARE_NM",
        "lat": "LAT", "lon": "LOT",
        "road_addr": "RONA_DADDR", "addr": "DADDR",
        "type": "FCLT_TYPE", "capacity": "UTZTN_PSBLTY_TNOP",
        "wkday_from": "WKDY_OPER_BGNG_HR", "wkday_to": "WKDY_OPER_END_HR",
        "sat_from": "STDY_OPER_BGNG_HR", "sat_to": "STDY_OPER_END_HR",
        "sun_from": "SNDY_OPER_BGNG_HR", "sun_to": "SNDY_OPER_END_HR",
        "holiday_from": "LHLDY_OPER_BGNG_HR", "holiday_to": "LHLDY_OPER_END_HR",
        "remark": "RMRK",
    },
)

DATASETS = {COOLING: HEAT_SHELTERS, HEATING: COLD_SHELTERS}


def normalize(raw: dict, ds: Dataset) -> dict:
    """원본 레코드를 공통 필드 이름으로 변환."""
    return {canon: raw.get(src) for canon, src in ds.fields.items()}

#: 재시도해도 소용없는 응답 코드 → 즉시 중단한다.
#: 특히 22(일일 한도 초과)에서 재시도하면 남은 한도까지 갉아먹는다.
FATAL_CODES = {
    "22": "일일 요청 한도를 초과했습니다. 보통 다음 날 0시에 초기화됩니다.",
    "20": "이 키로는 해당 서비스에 접근할 수 없습니다. 활용신청이 승인됐는지 확인하세요.",
    "30": "등록되지 않은 키입니다. 발급 직후라면 1~2시간 뒤 다시 시도하세요.",
    "31": "키 사용 기간이 만료되었습니다.",
}


class ApiRefused(RuntimeError):
    """재시도가 무의미한 API 거부 (한도 초과·키 문제)."""

    def __init__(self, code: str, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"[{code}] {msg}")

    def friendly(self) -> str:
        return FATAL_CODES.get(self.code, self.msg)

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
    # '○○동행정복지센터' 는 주민센터다. 아래 center 의 '복지센터' 에 먼저 걸리지
    # 않도록 반드시 위에 둔다.
    (("행정복지센터", "주민센터", "주민자치센터"), "gov"),
    (("복지관", "복지회관", "복지센터", "문화의집", "체육센터", "체육관", "청소년센터",
      "문화센터", "기념관", "박물관", "미술관", "문예회관", "평생학습",
      "이동노동자", "교회", "성당", "사찰"), "center"),
    (("구청", "시청", "군청", "면사무소", "읍사무소", "동사무소",
      "민원센터", "우체국", "청사"), "gov"),
    (("전통시장", "상가"), "market"),
    # '쉼터' 는 실내에도 흔히 붙으므로 야외 판정에서 제외한다
    (("야외", "공원", "정자", "그늘막", "파고라", "물놀이"), "park"),
]

# 한파쉼터에는 난방설비 정보가 없어 유형만으로 추정한다
_ASSUMED_INDOOR_HEAT = {
    "senior": 24.5,   # 경로당은 대체로 따뜻하게 유지한다
    "gov": 23.0, "library": 23.0, "center": 23.5, "hospital": 23.5,
    "bank": 23.0, "mart": 22.5, "store": 22.5, "market": 21.5,
    "busstop": 18.0,  # 밀폐형 스마트쉼터 기준
}

# 냉방설비 정보가 비어 있을 때 쓰는 유형별 실내 온도 추정치
_ASSUMED_INDOOR = {
    "bank": 24.5, "gov": 24.5, "library": 24.5, "center": 25.0,
    "store": 24.0, "mart": 23.5, "hospital": 24.0, "market": 26.5,
    "senior": 26.0, "busstop": 25.5,
}


def _hhmm_to_hour(v) -> int | None:
    """'0900' / '090000' 둘 다 시(hour)로 바꾼다.

    한파쉼터는 평일은 4자리, 토·일은 6자리로 섞여 들어온다.
    """
    if not v:
        return None
    s = str(v).strip()
    if len(s) not in (4, 6) or not s.isdigit():
        return None
    h = int(s[:2])
    return h if 0 <= h <= 24 else None


def _classify(name: str, fclty_ty: str) -> str:
    for keys, cat in _NAME_RULES:
        if any(k in name for k in keys):
            return cat
    return {TY_PUBLIC: "gov", TY_OUTDOOR: "park",
            TY_SENIOR: "senior", TY_BANK: "bank"}.get(fclty_ty, "center")


def record_to_place(rec: dict, mode: str) -> Place | None:
    """정규화된 레코드 → Place. 좌표가 없으면 버린다."""
    try:
        lat = float(rec["lat"])
        lon = float(rec["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (33.0 <= lat <= 39.5 and 124.0 <= lon <= 132.0):
        return None

    cold = mode == HEATING
    name = (rec.get("name") or ("한파쉼터" if cold else "무더위쉼터")).strip()
    ty = str(rec.get("type") or TY_SENIOR)
    category = _classify(name, ty)

    ac = rec.get("ac") or 0
    fan = rec.get("fan") or 0

    # 버스정류장은 두 종류다.
    #  · 냉방설비가 있는 '스마트쉼터/스마트승강장' — 밀폐형 부스라 실내로 본다
    #  · 그늘막만 있는 일반 정류장 — 야외
    outdoor = ty == TY_OUTDOOR or category == "park" or (category == "busstop" and not ac)
    people = rec.get("capacity") or 0
    area = rec.get("area") or 0

    d_from, d_to, d_weekend_closed = _DEFAULT_HOURS.get(ty, (9, 18, False))
    open_from = _hhmm_to_hour(rec.get("wkday_from"))
    open_to = _hhmm_to_hour(rec.get("wkday_to"))
    if open_from is None:
        open_from = d_from
    if open_to is None or open_to <= open_from:
        open_to = max(d_to, open_from + 1)

    if cold:
        # 한파쉼터는 요일별 운영시간이 따로 있다 → 토·일 값이 있으면 주말도 연다
        sat = _hhmm_to_hour(rec.get("sat_to"))
        sun = _hhmm_to_hour(rec.get("sun_to"))
        weekend_closed = not (sat or sun)
        night = False
        weekend_flag = "Y" if (sat or sun) else "N"
    else:
        weekend_flag = rec.get("weekend_open")
        weekend_closed = (weekend_flag == "N") if weekend_flag else d_weekend_closed
        night = rec.get("night_open") == "Y"
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
        indoor_cool = _ASSUMED_INDOOR.get(category, 26.0) - (1.0 if ac else 0.0)
    indoor_heat = 5.0 if outdoor else _ASSUMED_INDOOR_HEAT.get(category, 23.0)

    airflow = "양호" if ac else ("보통" if fan else "정보 없음")

    amenities = []
    if cold:
        amenities.append("난방설비 정보 없음")
    else:
        amenities.append("냉방설비 있음" if has_cooling else "냉방설비 정보 없음")
    if area:
        amenities.append(f"{area}㎡")
    if night:
        amenities.append("야간 개방")
    if weekend_flag == "Y":
        amenities.append("주말·공휴일 개방")
    if rec.get("stay_ok") == "Y":
        amenities.append("숙박 가능")
    remark = (rec.get("remark") or "").strip()
    if remark:
        amenities.append(remark)
    amenities.append("실내 온도는 추정치")

    seats = max(4, int(people) if people else 20)
    address = (rec.get("road_addr") or rec.get("addr") or "").strip()

    official = True
    if cold:
        summary = ("행정안전부 지정 한파쉼터입니다. "
                   + (f"약 {people}명이 이용할 수 있습니다." if people
                      else "한파 시 개방되는 실내 공간입니다."))
        why = "공식 지정 한파쉼터라 무료이며, 추위를 피하러 들어가도 눈치가 보이지 않습니다."
    elif category == "busstop":
        summary = ("행정안전부 지정 무더위쉼터로 등록된 버스정류장입니다. "
                   + ("냉방설비를 갖춘 밀폐형 스마트쉼터입니다."
                      if ac else "그늘막 형태의 야외 정류장입니다."))
        why = "공식 지정 무더위쉼터라 무료이며, 이용에 눈치가 보이지 않습니다."
    else:
        summary = ("행정안전부 지정 무더위쉼터입니다. "
                   + ("냉방설비를 갖추고 있습니다." if has_cooling
                      else "냉방설비 정보는 등록되어 있지 않습니다."))
        why = "공식 지정 무더위쉼터라 무료이며, 이용에 눈치가 보이지 않습니다."

    return Place(
        id=f"{'C' if cold else 'H'}{abs(int(rec.get('no') or 0))}",
        name=name,
        category=category,
        address=address,
        lat=lat,
        lon=lon,
        modes=(HEATING,) if cold else (COOLING,),
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
        indoor_heat=indoor_heat,
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
    """쉼터 데이터셋 전량 동기화 + 반경 조회 (무더위/한파 공용)."""

    progress = Signal(int, int)     # (받은 건수, 전체)
    ready = Signal()

    def __init__(self, dataset: Dataset, parent: QObject | None = None):
        super().__init__(parent)
        self.dataset = dataset
        self._lock = threading.Lock()
        self._records: list[dict] = []
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="shelter")
        self._file = cache_dir("shelters") / f"{dataset.service_id}.json"
        self._syncing = False
        self._error = ""
        self._fetched_at = 0.0
        self._missing_pages: list[int] = []
        self._total_expected = 0
        self._load_cache()

    # -- 상태 -------------------------------------------------------------
    @property
    def has_key(self) -> bool:
        return bool(secrets.get(self.dataset.secret_key))

    @property
    def label(self) -> str:
        return self.dataset.label

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
            records = raw["records"]
            # 예전 캐시는 원본 필드명(LA/LO ...)으로 저장돼 있다.
            # 다시 내려받으면 API 한도를 쓰므로 그 자리에서 변환한다.
            if records and "lat" not in records[0]:
                records = [{k: v for k, v in normalize(r, self.dataset).items()
                            if v is not None} for r in records]
                with self._lock:
                    self._records = records
                self._fetched_at = raw.get("fetched_at", 0)
                self._missing_pages = raw.get("missing_pages", [])
                self._total_expected = raw.get("total_expected", 0)
                self._save_cache()
                return
            with self._lock:
                self._records = records
            self._fetched_at = raw.get("fetched_at", 0)
            self._missing_pages = raw.get("missing_pages", [])
            self._total_expected = raw.get("total_expected", 0)
        except (OSError, ValueError, KeyError):
            pass

    def _save_cache(self) -> None:
        try:
            with self._lock:
                data = {"fetched_at": time.time(), "records": self._records,
                        "missing_pages": self._missing_pages,
                        "total_expected": self._total_expected}
            self._file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self._fetched_at = data["fetched_at"]
        except OSError:
            pass

    def stale(self) -> bool:
        if not self.loaded or self._missing_pages:
            return True
        return (time.time() - self._fetched_at) > CACHE_TTL

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
            "serviceKey": secrets.get(self.dataset.secret_key),
            "returnType": "json",
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
        })
        req = urllib.request.Request(f"{BASE}/{self.dataset.service_id}?{q}",
                                     headers={"User-Agent": "CoolMapAI/1.0"})
        with urllib.request.urlopen(req, timeout=45) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        header = d.get("header", {})
        code = header.get("resultCode")
        if code != "00":
            msg = header.get("errorMsg") or header.get("resultMsg") or "unknown error"
            # 22: 일일 요청 한도 초과 / 20·30: 키 거부
            if code in FATAL_CODES:
                raise ApiRefused(code, msg)
            raise RuntimeError(f"[{code}] {msg}")
        return d.get("body") or [], int(d.get("totalCount") or 0)

    def _trim(self, body: list[dict]) -> list[dict]:
        """캐시에 담을 필드만 남기고, 곧바로 공통 이름으로 정규화해 둔다."""
        out = []
        for raw in body:
            rec = normalize(raw, self.dataset)
            out.append({k: v for k, v in rec.items() if v is not None})
        return out

    def _do_sync(self) -> None:
        """전량 동기화.

        일일 요청 한도가 있는 API 라서, 실패해도 받은 만큼은 반드시 저장하고
        못 받은 페이지 번호를 기록해 다음 실행에서 그것만 이어받는다.
        한도 초과(22) 같은 응답에는 재시도하지 않는다 — 남은 한도만 더 갉아먹는다.
        """
        rows: list[dict] = []
        total = 0
        refused: ApiRefused | None = None
        try:
            first, total = self._fetch_page(1)
            rows = self._trim(first)
            pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
            self.progress.emit(len(rows), total)

            # 이어받기: 이전에 못 받은 페이지가 있으면 그것만 처리
            todo = self._missing_pages or list(range(2, pages + 1))
            if self._missing_pages:
                with self._lock:
                    rows = list(self._records) or rows

            missing: list[int] = []
            for page in todo:
                body = None
                for attempt in range(2):     # 일시적 오류만 한 번 더
                    try:
                        body, _ = self._fetch_page(page)
                        break
                    except ApiRefused as exc:
                        refused = exc
                        break
                    except Exception as exc:
                        self._error = f"p{page} {type(exc).__name__}: {exc}"
                        time.sleep(0.8 * (attempt + 1))
                if refused is not None:
                    missing.extend(p for p in todo if p >= page)
                    break
                if body is None:
                    missing.append(page)
                    continue
                rows.extend(self._trim(body))
                self.progress.emit(len(rows), total)
                time.sleep(0.08)      # 공공 API 배려

            self._missing_pages = missing
            self._total_expected = total
            if rows:
                with self._lock:
                    self._records = rows
                self._save_cache()

            if refused is not None:
                self._error = refused.friendly()
            elif missing:
                self._error = (f"{len(missing)}개 구간을 받지 못했습니다 "
                               f"({len(rows):,}/{total:,}건). 다시 시도하면 이어받습니다.")
            else:
                self._error = ""
        except ApiRefused as exc:
            self._error = exc.friendly()
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
        finally:
            self._syncing = False
        self.ready.emit()

    @property
    def partial(self) -> bool:
        """일부만 받아온 상태인지."""
        return bool(self._missing_pages) and self.loaded

    @property
    def total_expected(self) -> int:
        return self._total_expected or self.count

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
                la, lo = float(r["lat"]), float(r["lon"])
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
            p = record_to_place(r, self.dataset.mode)
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
