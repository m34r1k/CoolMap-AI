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
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

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
TONE_LIGHTEN = 285      # 클수록 지도가 밝아진다 (도로·지명 가독성 ↔ 마커 대비)


def _dark_transform(img: QImage, accent: QColor, tone: QColor) -> QImage:
    """밝은 OSM 타일을 다크 테마로 변환.

    반전 → 탈채도(반전 색상이 기괴해지므로) → 테마 톤으로 멀티플라이 → 강조색 미세 틴트.
    tone 을 모드별 배경색으로 넘기면 냉방은 푸르게, 난방은 붉게 물든다.
    """
    out = img.convertToFormat(QImage.Format_ARGB32)
    out.invertPixels(QImage.InvertRgb)

    gray = out.convertToFormat(QImage.Format_Grayscale8).convertToFormat(QImage.Format_ARGB32)

    p = QPainter(out)
    p.setOpacity(0.80)
    p.drawImage(0, 0, gray)                     # 탈채도
    p.setOpacity(1.0)
    p.setCompositionMode(QPainter.CompositionMode_Multiply)
    p.fillRect(out.rect(), QColor(tone).lighter(TONE_LIGHTEN))   # 모드 톤 입히기 + 전체 감광
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    tint = QColor(accent)
    tint.setAlpha(16)
    p.fillRect(out.rect(), tint)
    p.end()
    return out


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
        self._accent = QColor("#22D3EE")
        self._tone = QColor("#0A1220")
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

    def set_theme(self, accent: str, tone: str) -> None:
        """모드 색상 적용. 변환 결과가 바뀌므로 메모리 캐시를 비운다."""
        if QColor(accent) == self._accent and QColor(tone) == self._tone:
            return
        self._accent = QColor(accent)
        self._tone = QColor(tone)
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
            img = _dark_transform(img, self._accent, self._tone)
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
