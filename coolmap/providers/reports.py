"""쉼터 제보 — CoolMap 서버(report 함수)에 문제를 알리고, 최근 48시간 제보를 받는다.

mobile/src/backend.ts 의 reportShelter · recentReports 와 같은 서버를 쓴다.

화면이 다시 그려질 때마다 want() 를 불러도 되게 만든다:
  · 같은 쉼터 목록이면 REFRESH_S 안에는 다시 받지 않는다
  · 받은 내용이 바뀌었을 때만 updated 를 낸다
  (그러지 않으면 '갱신 → 다시 받기 → 갱신' 이 돌아 앱이 멈춘다)
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from . import backend

REFRESH_S = 5 * 60


class ReportProvider(QObject):
    updated = Signal()
    added = Signal(bool, str)       # (성공 여부, 쉬운 말 안내)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reports")
        self._lock = threading.Lock()
        self._reports: dict[str, dict] = {}
        self._key = ""
        self._fetched_at = 0.0
        self._pending = False

    def get(self, place_id: str) -> dict | None:
        with self._lock:
            return self._reports.get(place_id)

    def want(self, place_ids: list[str]) -> None:
        """이 쉼터들의 제보가 필요하다. 필요할 때만 서버에 묻는다."""
        ids = sorted(set(place_ids))[:300]
        if not ids:
            return
        key = ",".join(ids)
        if self._pending or (key == self._key and time.time() - self._fetched_at < REFRESH_S):
            return
        self._key = key
        self._pending = True
        self._pool.submit(self._fetch, ids)

    def _fetch(self, ids: list[str]) -> None:
        try:
            data = backend.call("report", {"task": "recent", "place_ids": ids}, timeout=20)
            reports = data.get("reports") or {}
            with self._lock:
                changed = reports != self._reports
                self._reports = reports
            self._fetched_at = time.time()
            if changed:
                self.updated.emit()
        except Exception:
            self._fetched_at = time.time()      # 실패해도 잠시 쉬었다가 다시 묻는다
        finally:
            self._pending = False

    def add(self, place_id: str, kind: str) -> None:
        self._pool.submit(self._add, place_id, kind)

    def _add(self, place_id: str, kind: str) -> None:
        try:
            backend.call("report", {"task": "add", "place_id": place_id, "kind": kind}, timeout=20)
            self._fetched_at = 0.0              # 내 제보가 바로 보이도록 다음 want() 에서 다시 받는다
            self.added.emit(True, "알려 주셔서 고마워요. 다른 분들께도 함께 보여 드릴게요.")
        except urllib.error.HTTPError as exc:
            try:
                msg = json.loads(exc.read().decode("utf-8")).get("error", "")
            except Exception:
                msg = ""
            self.added.emit(False, msg or f"서버 응답 {exc.code}")
        except Exception:
            self.added.emit(False, "인터넷 연결을 확인해 주세요")

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
