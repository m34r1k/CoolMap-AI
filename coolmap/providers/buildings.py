"""OSM Overpass API — 건물 외곽선(폴리곤) 제공자.

건물 하이라이트 기능에 필요한 실제 건물 footprint 를 가져온다. 키 불필요.

- 타일(0.01° 격자) 단위로 조회하고 디스크에 영구 캐시 (건물은 거의 안 변한다)
- 백그라운드 스레드, UI 블로킹 없음
- Overpass 는 공용 인프라이므로 요청을 아끼고 실패 시 조용히 폴백한다
"""

from __future__ import annotations

import json
import math
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from ..paths import cache_dir

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "CoolMapAI/1.0 (desktop shelter map)"

CELL = 0.01          # 약 1.1km × 0.9km
MAX_CELLS = 24       # 한 번에 유지할 셀 수
MIN_INTERVAL = 1.2   # 요청 간 최소 간격 (초)

Poly = list[tuple[float, float]]      # [(lat, lon), ...]


def _cell_of(lat: float, lon: float) -> tuple[int, int]:
    return int(math.floor(lat / CELL)), int(math.floor(lon / CELL))


def _cell_bbox(cell: tuple[int, int]) -> tuple[float, float, float, float]:
    la, lo = cell
    return la * CELL, lo * CELL, (la + 1) * CELL, (lo + 1) * CELL


class BuildingProvider(QObject):
    """화면에 보이는 영역의 건물 폴리곤을 준다."""

    updated = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._cells: dict[tuple[int, int], list[dict]] = {}
        self._pending: set[tuple[int, int]] = set()
        self._failed: dict[tuple[int, int], float] = {}
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="overpass")
        self._dir = cache_dir("buildings")
        self._last_request = 0.0
        self._enabled = True
        self._error = ""

    def set_enabled(self, on: bool) -> None:
        self._enabled = on

    @property
    def error(self) -> str:
        return self._error

    # -- 캐시 파일 --------------------------------------------------------
    def _path(self, cell: tuple[int, int]):
        return self._dir / f"{cell[0]}_{cell[1]}.json"

    def _load_cell(self, cell: tuple[int, int]) -> list[dict] | None:
        path = self._path(cell)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    # -- 조회 -------------------------------------------------------------
    def buildings_in(self, min_lat: float, min_lon: float,
                     max_lat: float, max_lon: float) -> list[dict]:
        """해당 영역의 건물 목록. 없으면 백그라운드로 받아온다."""
        if not self._enabled:
            return []
        out: list[dict] = []
        c0 = _cell_of(min_lat, min_lon)
        c1 = _cell_of(max_lat, max_lon)
        # 너무 넓으면(줌 아웃) 건물을 안 그린다
        if (c1[0] - c0[0] + 1) * (c1[1] - c0[1] + 1) > MAX_CELLS:
            return []

        for la in range(c0[0], c1[0] + 1):
            for lo in range(c0[1], c1[1] + 1):
                cell = (la, lo)
                with self._lock:
                    got = self._cells.get(cell)
                if got is None:
                    got = self._load_cell(cell)
                    if got is not None:
                        with self._lock:
                            self._cells[cell] = got
                if got is not None:
                    out.extend(got)
                    continue
                self._request(cell)
        return out

    def building_at(self, lat: float, lon: float) -> dict | None:
        """해당 좌표를 포함하는 건물 (없으면 가장 가까운 건물)."""
        cell = _cell_of(lat, lon)
        with self._lock:
            items = self._cells.get(cell)
        if items is None:
            items = self._load_cell(cell)
            if items is None:
                self._request(cell)
                return None
            with self._lock:
                self._cells[cell] = items

        best, best_d = None, float("inf")
        for b in items:
            poly = b["poly"]
            if _point_in_poly(lat, lon, poly):
                return b
            clat, clon = b["center"]
            d = (clat - lat) ** 2 + (clon - lon) ** 2
            if d < best_d:
                best_d, best = d, b
        # 너무 멀면 (약 120m 초과) 매칭하지 않는다
        return best if best_d < (0.0011 ** 2) else None

    def _request(self, cell: tuple[int, int]) -> None:
        with self._lock:
            if cell in self._pending:
                return
            last_fail = self._failed.get(cell, 0)
            if time.time() - last_fail < 120:      # 실패 후 2분 쿨다운
                return
            self._pending.add(cell)
        self._pool.submit(self._fetch, cell)

    def _fetch(self, cell: tuple[int, int]) -> None:
        try:
            # 공용 인프라 배려 — 요청 간격 유지
            wait = MIN_INTERVAL - (time.time() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.time()

            s, w, n, e = _cell_bbox(cell)
            query = (
                "[out:json][timeout:25];"
                f"(way['building']({s},{w},{n},{e});"
                f" relation['building']({s},{w},{n},{e}););"
                "out geom;"
            )
            # Overpass 공개 인스턴스는 504/429 가 흔하다 → 짧은 백오프로 재시도
            data = None
            attempts = [(ENDPOINTS[0], 35), (ENDPOINTS[1], 20), (ENDPOINTS[0], 35)]
            for i, (url, timeout) in enumerate(attempts):
                try:
                    req = urllib.request.Request(
                        url,
                        data=urllib.parse.urlencode({"data": query}).encode(),
                        headers={"User-Agent": USER_AGENT},
                    )
                    with urllib.request.urlopen(req, timeout=timeout) as r:
                        data = json.loads(r.read().decode("utf-8", "replace"))
                    break
                except Exception as exc:
                    self._error = f"{type(exc).__name__}: {exc}"
                    if i < len(attempts) - 1:
                        time.sleep(1.5 * (i + 1))
            if data is None:
                raise RuntimeError(self._error or "overpass unreachable")

            items = _parse(data)
            self._path(cell).write_text(json.dumps(items), encoding="utf-8")
            with self._lock:
                self._cells[cell] = items
                while len(self._cells) > MAX_CELLS * 3:
                    self._cells.pop(next(iter(self._cells)))
                self._failed.pop(cell, None)
            self._error = ""
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            with self._lock:
                self._failed[cell] = time.time()
        finally:
            with self._lock:
                self._pending.discard(cell)
        self.updated.emit()

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def cache_count(self) -> int:
        return len(list(self._dir.glob("*.json")))

    def clear_cache(self) -> None:
        with self._lock:
            self._cells.clear()
            self._failed.clear()
        for p in self._dir.glob("*.json"):
            try:
                p.unlink()
            except OSError:
                pass


def _parse(data: dict) -> list[dict]:
    out: list[dict] = []
    for el in data.get("elements", []):
        poly: Poly = []
        if el.get("type") == "way" and el.get("geometry"):
            poly = [(p["lat"], p["lon"]) for p in el["geometry"]]
        elif el.get("type") == "relation":
            # 멀티폴리곤은 가장 긴 outer 링만 사용
            best: Poly = []
            for m in el.get("members", []):
                if m.get("role") == "outer" and m.get("geometry"):
                    ring = [(p["lat"], p["lon"]) for p in m["geometry"]]
                    if len(ring) > len(best):
                        best = ring
            poly = best
        if len(poly) < 3:
            continue
        if poly[0] == poly[-1]:
            poly = poly[:-1]
        lats = [p[0] for p in poly]
        lons = [p[1] for p in poly]
        tags = el.get("tags", {})
        out.append({
            "id": f"{el.get('type', 'w')}{el.get('id')}",
            "poly": poly,
            "center": (sum(lats) / len(lats), sum(lons) / len(lons)),
            "bbox": (min(lats), min(lons), max(lats), max(lons)),
            "name": tags.get("name", ""),
            "levels": tags.get("building:levels", ""),
        })
    return out


def _point_in_poly(lat: float, lon: float, poly: Poly) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi
            if x_cross > lon:
                inside = not inside
        j = i
    return inside
