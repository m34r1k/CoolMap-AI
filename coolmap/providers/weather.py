"""기상청 단기예보 조회서비스 연동.

- 초단기실황(getUltraSrtNcst) : 현재 기온·습도·풍속
- 단기예보(getVilageFcst)     : 시간대별 기온 예보 (혼잡도 대신 '언제 더운지' 표시에 사용)

사용자가 키를 넣지 않았으면 CoolMap 서버(supabase/functions/weather)를 거쳐 받는다.
서버는 격자 단위로 캐시하므로 같은 동네 사용자는 기상청 호출을 나눠 쓴다.
둘 다 안 되거나 네트워크가 끊기면 data.weather_for() 의 모의 곡선으로 폴백한다.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Signal

from .. import secrets
from . import backend
from ..geo import latlon_to_kma_grid
from ..models import COOLING, Weather
from ..paths import cache_dir

BASE = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
CACHE_TTL = 30 * 60          # 실황 30분
FCST_TTL = 3 * 60 * 60       # 예보 3시간

# 단기예보 발표 시각
_FCST_BASE_TIMES = [2, 5, 8, 11, 14, 17, 20, 23]


def _http_json(path: str, params: dict) -> dict | None:
    key = secrets.kma_key()
    if not key:
        return None
    q = urllib.parse.urlencode(
        {**params, "serviceKey": key, "dataType": "JSON"},
        quote_via=urllib.parse.quote,
    )
    url = f"{BASE}/{path}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "CoolMapAI/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _items(payload: dict | None) -> list[dict]:
    if not payload:
        return []
    try:
        body = payload["response"]["body"]
        if payload["response"]["header"]["resultCode"] != "00":
            return []
        item = body["items"]["item"]
        return item if isinstance(item, list) else [item]
    except (KeyError, TypeError):
        return []


def _fcst_base(now: datetime) -> tuple[str, str]:
    """가장 최근의 단기예보 발표 시각 (발표 후 10분 여유)."""
    t = now - timedelta(minutes=15)
    hours = [h for h in _FCST_BASE_TIMES if h <= t.hour]
    if hours:
        return t.strftime("%Y%m%d"), f"{hours[-1]:02d}00"
    y = t - timedelta(days=1)
    return y.strftime("%Y%m%d"), "2300"


class WeatherProvider(QObject):
    """위경도 기준 실황/예보. 조회는 백그라운드, 결과는 캐시."""

    updated = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._now: dict[tuple, tuple[float, dict]] = {}      # grid -> (ts, values)
        self._fcst: dict[tuple, tuple[float, dict]] = {}     # grid -> (ts, {hour: temp})
        self._pending: set[tuple] = set()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kma")
        self._last_error = ""
        self._live = False
        self._cache_file = cache_dir("weather") / "kma.json"
        self._load_cache()

    # -- 캐시 ------------------------------------------------------------
    def _load_cache(self) -> None:
        try:
            raw = json.loads(self._cache_file.read_text(encoding="utf-8"))
            for k, v in raw.get("now", {}).items():
                self._now[tuple(json.loads(k))] = (v["ts"], v["val"])
            for k, v in raw.get("fcst", {}).items():
                self._fcst[tuple(json.loads(k))] = (
                    v["ts"], {int(h): t for h, t in v["val"].items()}
                )
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def _save_cache(self) -> None:
        try:
            data = {
                "now": {json.dumps(list(k)): {"ts": ts, "val": val}
                        for k, (ts, val) in self._now.items()},
                "fcst": {json.dumps(list(k)): {"ts": ts, "val": val}
                         for k, (ts, val) in self._fcst.items()},
            }
            self._cache_file.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass

    # -- 상태 ------------------------------------------------------------
    @property
    def live(self) -> bool:
        """실제 기상청 관측값을 보유 중인지 (디스크 캐시 포함)."""
        if not self.has_key:
            return False
        with self._lock:
            return bool(self._now)

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def own_key(self) -> bool:
        return bool(secrets.kma_key())

    @property
    def use_backend(self) -> bool:
        """사용자 키가 없으면 CoolMap 서버를 거친다."""
        return not self.own_key and backend.enabled()

    @property
    def has_key(self) -> bool:
        """받아 올 경로가 있는지 (사용자 키 또는 서버)."""
        return self.own_key or backend.enabled()

    # -- 조회 ------------------------------------------------------------
    def observation(self, lat: float, lon: float) -> dict | None:
        """현재 실황값. 없으면 백그라운드 조회 후 None."""
        if not self.has_key:
            return None
        grid = latlon_to_kma_grid(lat, lon)
        with self._lock:
            hit = self._now.get(grid)
            if hit and time.time() - hit[0] < CACHE_TTL:
                return hit[1]
            if grid in self._pending:
                return hit[1] if hit else None
            self._pending.add(grid)
        self._pool.submit(self._fetch, grid)
        with self._lock:
            hit = self._now.get(grid)
        return hit[1] if hit else None

    def forecast(self, lat: float, lon: float) -> dict[int, float]:
        """시간(0~23) -> 예보 기온."""
        grid = latlon_to_kma_grid(lat, lon)
        with self._lock:
            hit = self._fcst.get(grid)
        return dict(hit[1]) if hit else {}

    def _fetch(self, grid: tuple[int, int]) -> None:
        if self.use_backend:
            self._fetch_backend(grid)
            return
        nx, ny = grid
        now = datetime.now()
        try:
            # 실황 — 매시 40분에 갱신되므로 1시간 전 기준이 안전
            t = now - timedelta(minutes=45)
            obs = _items(_http_json("getUltraSrtNcst", {
                "base_date": t.strftime("%Y%m%d"), "base_time": t.strftime("%H00"),
                "nx": nx, "ny": ny, "pageNo": 1, "numOfRows": 100,
            }))
            values = {i["category"]: i["obsrValue"] for i in obs}
            if values:
                with self._lock:
                    self._now[grid] = (time.time(), values)
                self._live = True
                self._last_error = ""

            # 예보
            with self._lock:
                stale = self._fcst.get(grid)
            if not stale or time.time() - stale[0] > FCST_TTL:
                bd, bt = _fcst_base(now)
                fc = _items(_http_json("getVilageFcst", {
                    "base_date": bd, "base_time": bt,
                    "nx": nx, "ny": ny, "pageNo": 1, "numOfRows": 300,
                }))
                temps: dict[int, float] = {}
                for i in fc:
                    if i.get("category") == "TMP":
                        try:
                            temps[int(i["fcstTime"][:2])] = float(i["fcstValue"])
                        except (ValueError, KeyError):
                            pass
                if temps:
                    with self._lock:
                        self._fcst[grid] = (time.time(), temps)
            self._save_cache()
        except Exception as e:            # 네트워크/파싱 실패 → 폴백 유지
            self._last_error = f"{type(e).__name__}: {e}"
        finally:
            with self._lock:
                self._pending.discard(grid)
        self.updated.emit()

    def _fetch_backend(self, grid: tuple[int, int]) -> None:
        """서버 경유. 서버가 이미 실황 값과 시간별 기온으로 정리해서 준다."""
        nx, ny = grid
        try:
            d = backend.function("weather", {"nx": nx, "ny": ny})
            # 서버 캐시에서 온 값은 그만큼 오래된 것이므로 받은 시각을 앞당겨 둔다
            now_ts = time.time()
            if d.get("now"):
                with self._lock:
                    self._now[grid] = (now_ts - float(d.get("now_age") or 0), d["now"])
                self._live = True
            if d.get("fcst"):
                temps = {int(h): float(t) for h, t in d["fcst"].items()}
                with self._lock:
                    self._fcst[grid] = (now_ts - float(d.get("fcst_age") or 0), temps)
            self._last_error = d.get("error") or d.get("note") or ""
            self._save_cache()
        except Exception as e:            # 네트워크/파싱 실패 → 폴백 유지
            self._last_error = f"{type(e).__name__}: {e}"
        finally:
            with self._lock:
                self._pending.discard(grid)
        self.updated.emit()

    # -- Weather 조립 -----------------------------------------------------
    def weather(self, lat: float, lon: float, mode: str, hour: int, minute: int = 0) -> Weather:
        """실황이 있으면 실데이터로, 없으면 모의 곡선으로 Weather 생성."""
        from ..data import weather_for      # 순환 임포트 방지

        obs = self.observation(lat, lon)
        if not obs or "T1H" not in obs:
            w = weather_for(mode, hour, minute)
            return Weather(w.outdoor, w.feels, w.humidity, w.condition, w.alert)

        try:
            temp = float(obs.get("T1H"))
            humid = int(float(obs.get("REH", 50)))
            wind = float(obs.get("WSD", 1.0))
        except (TypeError, ValueError):
            w = weather_for(mode, hour, minute)
            return Weather(w.outdoor, w.feels, w.humidity, w.condition, w.alert)

        if mode == COOLING:
            # 열지수 근사 (Steadman 계열 단순화)
            feels = temp + 0.05 * humid - 2.0 if temp >= 27 else temp
            alert = "폭염경보" if temp >= 35 else ("폭염주의보" if temp >= 33 else "")
            condition = "매우 더움" if temp >= 34 else ("더움" if temp >= 30 else "보통")
        else:
            # 풍속 냉각 (체감온도)
            v = max(wind * 3.6, 1.0) ** 0.16
            feels = 13.12 + 0.6215 * temp - 11.37 * v + 0.3965 * temp * v if temp <= 10 else temp
            alert = "한파경보" if temp <= -12 else ("한파주의보" if temp <= -5 else "")
            condition = "매우 추움" if temp <= -8 else ("추움" if temp <= 3 else "보통")

        return Weather(
            outdoor=round(temp, 1),
            feels=round(feels, 1),
            humidity=max(0, min(100, humid)),
            condition=condition,
            alert=alert,
        )

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
