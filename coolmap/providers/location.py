"""현재 위치 확인.

브라우저의 Geolocation API(navigator.geolocation)는 웹 전용이라 이 앱에서는 쓸 수 없다.
대신 3단계로 확보한다.

1. **Qt Positioning** — PySide6 내장. Windows 에서는 `winrt` 백엔드가
   윈도우 위치 서비스(GPS·Wi-Fi·기지국)를 사용한다. 가장 정확하다(수십~수백 m).
   설정 > 개인 정보 > 위치 에서 앱 접근이 꺼져 있으면 실패한다.
2. **IP 기반 조회** — 권한이 없거나 실패했을 때. 도시 수준(수 km)이라 어디까지나 근사치.
3. **수동 지정** — 사용자가 지도를 클릭해 직접 지정. 항상 동작한다.
"""

from __future__ import annotations

import json
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal

IP_ENDPOINTS = [
    "https://ipapi.co/json/",
    "https://ipinfo.io/json",
]

# 위치를 못 구했을 때 쓰는 기본값 (서울시청)
DEFAULT_ORIGIN = (37.5662, 126.9784)


class LocationProvider(QObject):
    """현재 위치를 비동기로 확보한다."""

    located = Signal(float, float, float, str)   # lat, lon, accuracy(m), source
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._source = None
        self._busy = False
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="geoip")
        self._lock = threading.Lock()
        self._last_error = ""

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def last_error(self) -> str:
        return self._last_error

    @staticmethod
    def backend_name() -> str:
        try:
            from PySide6.QtPositioning import QGeoPositionInfoSource

            names = QGeoPositionInfoSource.availableSources()
            return ", ".join(names) if names else "없음"
        except Exception:
            return "QtPositioning 없음"

    # ------------------------------------------------------------------
    def request(self, timeout_ms: int = 20000) -> None:
        """위치 1회 조회. 결과는 located / failed 로 전달된다."""
        if self._busy:
            return
        self._busy = True
        self._last_error = ""
        if not self._start_qt(timeout_ms):
            self._start_ip()

    def _start_qt(self, timeout_ms: int) -> bool:
        try:
            from PySide6.QtPositioning import QGeoPositionInfoSource
        except ImportError:
            return False

        try:
            src = QGeoPositionInfoSource.createDefaultSource(self)
        except Exception:
            return False
        if src is None:
            return False

        self._source = src
        src.positionUpdated.connect(self._on_qt_position)
        src.errorOccurred.connect(self._on_qt_error)
        # winrt 백엔드가 조용히 멈추는 경우가 있어 자체 타임아웃을 둔다
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_qt_timeout)
        self._timeout.start(timeout_ms + 2000)
        try:
            src.requestUpdate(timeout_ms)
        except Exception:
            return False
        return True

    def _teardown_qt(self) -> None:
        if self._source is not None:
            try:
                self._source.positionUpdated.disconnect(self._on_qt_position)
                self._source.errorOccurred.disconnect(self._on_qt_error)
            except (RuntimeError, TypeError):
                pass
            self._source = None
        t = getattr(self, "_timeout", None)
        if t is not None and t.isActive():
            t.stop()

    def _on_qt_position(self, info) -> None:
        from PySide6.QtPositioning import QGeoPositionInfo

        c = info.coordinate()
        acc = info.attribute(QGeoPositionInfo.HorizontalAccuracy)
        if acc != acc:          # NaN
            acc = -1.0
        self._teardown_qt()
        self._busy = False
        self.located.emit(c.latitude(), c.longitude(), float(acc), "윈도우 위치 서비스")

    def _on_qt_error(self, err) -> None:
        self._last_error = f"위치 서비스 오류 ({err})"
        self._teardown_qt()
        self._start_ip()

    def _on_qt_timeout(self) -> None:
        self._last_error = "위치 서비스 응답 없음"
        self._teardown_qt()
        self._start_ip()

    # ------------------------------------------------------------------
    def _start_ip(self) -> None:
        self._pool.submit(self._fetch_ip)

    def _fetch_ip(self) -> None:
        for url in IP_ENDPOINTS:
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "CoolMapAI/1.0", "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    d = json.loads(r.read().decode("utf-8", "replace"))
                lat = lon = None
                if "latitude" in d and "longitude" in d:
                    lat, lon = float(d["latitude"]), float(d["longitude"])
                elif "loc" in d:                       # ipinfo.io -> "37.5,127.0"
                    parts = str(d["loc"]).split(",")
                    lat, lon = float(parts[0]), float(parts[1])
                if lat is None:
                    continue
                self._busy = False
                self.located.emit(lat, lon, 5000.0, "IP 기반 추정")
                return
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
        self._busy = False
        self.failed.emit(self._last_error or "위치를 확인할 수 없습니다")

    def shutdown(self) -> None:
        self._teardown_qt()
        self._pool.shutdown(wait=False, cancel_futures=True)
