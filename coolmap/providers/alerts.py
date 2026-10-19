"""재난문자 — CoolMap 서버(alerts 함수)에서 내 시군구의 최근 24시간 행정안전부 재난문자를 받는다.

mobile/src/backend.ts 의 disasterAlerts 와 같은 서버를 쓴다. 재난문자 키는 서버에만 있다.

reports.py 처럼 화면이 다시 그려질 때마다 want() 를 불러도 되게 만든다:
  · 같은 지역이면 REFRESH_S 안에는 다시 받지 않는다
  · 받은 내용이 바뀌었을 때만 updated 를 낸다
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from . import backend

REFRESH_S = 5 * 60


class AlertProvider(QObject):
    updated = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="alerts")
        self._lock = threading.Lock()
        self._alerts: list[dict] = []
        self._region = ""
        self._fetched_at = 0.0
        self._pending = False

    @property
    def region(self) -> str:
        return self._region

    def get(self) -> list[dict]:
        """[{sn, at, step, kind, text, area}] 최신순."""
        with self._lock:
            return list(self._alerts)

    def want(self, region: str) -> None:
        """이 지역의 문자가 필요하다. 지역을 모르면('') 전에 알던 지역을 그대로 쓴다."""
        region = region or self._region
        if not region or not backend.enabled():
            return
        if self._pending or (region == self._region and time.time() - self._fetched_at < REFRESH_S):
            return
        self._region = region
        self._pending = True
        self._pool.submit(self._fetch, region)

    def _fetch(self, region: str) -> None:
        try:
            d = backend.function("alerts", {"region": region})
            alerts = d.get("alerts") or []
            with self._lock:
                changed = alerts != self._alerts
                self._alerts = alerts
            self._fetched_at = time.time()
            if changed:
                self.updated.emit()
        except Exception:
            self._fetched_at = time.time()      # 실패해도 잠시 쉬었다가 다시 묻는다
        finally:
            self._pending = False

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
