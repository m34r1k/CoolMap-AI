"""OSM 래스터 타일 제공자.

- 디스크 캐시 (%APPDATA%\\CoolMap\\cache\\tiles)
- 백그라운드 스레드 다운로드 (UI 블로킹 없음)
- 다크 테마에 맞춘 색 변환 (반전 + 채도/색조 보정) — 원본은 밝은 지도라 그대로 쓰면 안 맞는다

OSM 타일 이용 정책상 식별 가능한 User-Agent 를 보내고, 캐시를 반드시 사용한다.
대량 일괄 다운로드는 하지 않는다 (화면에 보이는 타일만 요청).
"""

from __future__ import annotations

import threading
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QImage, QPixmap, qRgb

from .. import __version__
from ..paths import cache_dir

TILE_SIZE = 256
USER_AGENT = f"CoolMapAI/{__version__} (desktop shelter map; contact: local user)"

# 사용 가능한 타일 소스
SOURCES = {
    "osm": {
        "name": "OpenStreetMap",
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "max_zoom": 19,
        "attribution": "© OpenStreetMap contributors",
        "dark": True,      # 밝은 지도 → 다크 변환 필요
    },
}

MEM_CACHE_MAX = 320


#: 모드별 다크맵 색 램프 (어두운 배경색 → 밝은 선/글자색)
#: 원본 OSM 타일의 밝기를 뒤집어 이 두 색 사이로 재배치한다.
RAMPS = {
    "cooling": ("#070E1A", "#A8C8E4"),
    "heating": ("#140809", "#F0C4B4"),
}

#: 밝기 재배치 구간과 곡선.
#: 감마를 1 보다 크게 두면 넓은 지면(원본의 밝은 부분)은 어둡게 눌리고
#: 도로·글자(원본의 어두운 선)는 밝게 남아, 다크 UI 와 어울리면서도 잘 읽힌다.
#: (1 미만으로 두면 배경까지 들려 전체가 뿌옇게 된다)
RAMP_LO = 0.04
RAMP_HI = 1.0
RAMP_GAMMA = 1.35


def _color_table(mode: str) -> list[int]:
    """밝기(0~255) → 다크맵 색상 256단계 룩업 테이블.

    픽셀별 파이썬 연산은 너무 느리므로, 그레이스케일로 바꾼 뒤
    Qt 의 인덱스 컬러 테이블로 한 번에 매핑한다.
    """
    dark, light = RAMPS.get(mode, RAMPS["cooling"])
    d, l = QColor(dark), QColor(light)
    table = []
    for i in range(256):
        v = 1.0 - i / 255.0                 # 반전: 밝은 지면 → 어둡게, 검은 글자 → 밝게
        v = v ** RAMP_GAMMA
        v = RAMP_LO + v * (RAMP_HI - RAMP_LO)
        r = int(d.red() + (l.red() - d.red()) * v)
        g = int(d.green() + (l.green() - d.green()) * v)
        b = int(d.blue() + (l.blue() - d.blue()) * v)
        table.append(qRgb(min(r, 255), min(g, 255), min(b, 255)))
    return table


def _dark_transform(img: QImage, table: list[int]) -> QImage:
    """밝은 OSM 타일 → 다크맵.

    이전에는 반전 후 멀티플라이로 눌렀는데, 전체가 뭉개져 도로와 지명이
    거의 안 보였다. 지금은 밝기를 뽑아 색 램프로 재배치해서
    배경은 어둡게 두되 선과 글자는 확실히 띄운다.
    """
    gray = img.convertToFormat(QImage.Format_Grayscale8)
    indexed = QImage(bytes(gray.constBits()), gray.width(), gray.height(),
                     gray.bytesPerLine(), QImage.Format_Indexed8)
    indexed.setColorTable(table)
    return indexed.convertToFormat(QImage.Format_ARGB32)


class TileProvider(QObject):
    """타일을 캐시에서 즉시 주거나, 없으면 받아온 뒤 tileReady 를 낸다."""

    tileReady = Signal()

    def __init__(self, source: str = "osm", parent: QObject | None = None):
        super().__init__(parent)
        self.source = source if source in SOURCES else "osm"
        self._mem: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._pending: set[tuple] = set()
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tile")
        self._mode = "cooling"
        self._table = _color_table("cooling")
        self._dark = True
        self._enabled = True
        self._failures = 0
        self._dir = cache_dir("tiles")

    # -- 설정 ------------------------------------------------------------
    @property
    def meta(self) -> dict:
        return SOURCES[self.source]

    @property
    def max_zoom(self) -> int:
        return self.meta["max_zoom"]

    @property
    def attribution(self) -> str:
        return self.meta["attribution"]

    def set_mode(self, mode: str) -> None:
        """모드 색상 적용. 변환 결과가 바뀌므로 메모리 캐시를 비운다."""
        if mode == self._mode:
            return
        self._mode = mode
        self._table = _color_table(mode)
        with self._lock:
            self._mem.clear()
        self.tileReady.emit()

    def set_enabled(self, on: bool) -> None:
        self._enabled = on
        self.tileReady.emit()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def offline(self) -> bool:
        return self._failures >= 6

    # -- 조회 ------------------------------------------------------------
    def _disk_path(self, z: int, x: int, y: int):
        d = self._dir / self.source / str(z) / str(x)
        return d / f"{y}.png"

    def get(self, z: int, x: int, y: int) -> QPixmap | None:
        """즉시 사용 가능한 타일. 없으면 None 을 주고 백그라운드로 받아온다."""
        if not self._enabled:
            return None
        key = (self.source, z, x, y)
        with self._lock:
            pm = self._mem.get(key)
            if pm is not None:
                self._mem.move_to_end(key)
                return pm
            if key in self._pending:
                return None

        path = self._disk_path(z, x, y)
        if path.exists():
            img = QImage(str(path))
            if not img.isNull():
                return self._store(key, img)
            try:
                path.unlink()       # 손상된 캐시
            except OSError:
                pass

        with self._lock:
            if key in self._pending:
                return None
            self._pending.add(key)
        self._pool.submit(self._fetch, key)
        return None

    def _store(self, key: tuple, img: QImage) -> QPixmap:
        if self._dark and self.meta.get("dark"):
            img = _dark_transform(img, self._table)
        pm = QPixmap.fromImage(img)
        with self._lock:
            self._mem[key] = pm
            while len(self._mem) > MEM_CACHE_MAX:
                self._mem.popitem(last=False)
        return pm

    def _fetch(self, key: tuple) -> None:
        _src, z, x, y = key
        url = self.meta["url"].format(z=z, x=x, y=y)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=12) as r:
                data = r.read()
            path = self._disk_path(z, x, y)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(path)
            self._failures = 0
        except Exception:
            self._failures += 1
        finally:
            with self._lock:
                self._pending.discard(key)
        self.tileReady.emit()

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def cache_size_mb(self) -> float:
        total = 0
        for p in self._dir.rglob("*.png"):
            try:
                total += p.stat().st_size
            except OSError:
                pass
        return total / (1024 * 1024)

    def clear_cache(self) -> None:
        with self._lock:
            self._mem.clear()
        for p in self._dir.rglob("*.png"):
            try:
                p.unlink()
            except OSError:
                pass
        self.tileReady.emit()
