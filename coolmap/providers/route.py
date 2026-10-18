"""도보 길 안내 — CoolMap 서버(route 함수 · T맵 보행자 경로)를 부른다.

mobile/src/backend.ts 의 walkRoute 와 같은 서버를 쓴다. 키는 서버에만 있다.
결과: {distance_m, time_s, path: [[lon, lat], ...], steps: [{text, at}]}
"""

from __future__ import annotations

import urllib.error
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from . import backend


class RouteProvider(QObject):
    ready = Signal(str, dict)       # (요청 키, 경로)
    failed = Signal(str, str)       # (요청 키, 쉬운 말 오류)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="route")
        self._cache: dict[str, dict] = {}

    @staticmethod
    def key(origin: tuple[float, float], dest: tuple[float, float]) -> str:
        return f"{origin[0]:.4f},{origin[1]:.4f}>{dest[0]:.5f},{dest[1]:.5f}"

    def request(self, origin: tuple[float, float], dest: tuple[float, float], name: str) -> str:
        """origin · dest 는 (위도, 경도). 요청 키를 돌려주고, 끝나면 ready / failed 를 낸다."""
        k = self.key(origin, dest)
        if k in self._cache:
            self.ready.emit(k, self._cache[k])
            return k
        self._pool.submit(self._fetch, k, origin, dest, name)
        return k

    def _fetch(self, k: str, origin, dest, name: str) -> None:
        try:
            data = backend.call("route", {"from": list(origin), "to": list(dest), "to_name": name}, timeout=30)
            if not data.get("path"):
                raise RuntimeError(data.get("error") or "경로가 없습니다")
            self._cache[k] = data
            self.ready.emit(k, data)
        except urllib.error.HTTPError as exc:
            self.failed.emit(k, backend.error_message(exc))
        except Exception as exc:
            self.failed.emit(k, "인터넷 연결을 확인해 주세요" if isinstance(exc, urllib.error.URLError) else str(exc))

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
