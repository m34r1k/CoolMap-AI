"""쉼터 제보 — CoolMap 서버(report 함수)에 문제를 알리고, 최근 24시간 제보를 받는다.

mobile/src/backend.ts 의 reportShelter · recentReports 와 같은 서버를 쓴다.

화면이 다시 그려질 때마다 want() 를 불러도 되게 만든다:
  · 같은 쉼터 목록이면 REFRESH_S 안에는 다시 받지 않는다
  · 받은 내용이 바뀌었을 때만 updated 를 낸다
  (그러지 않으면 '갱신 → 다시 받기 → 갱신' 이 돌아 앱이 멈춘다)
"""

from __future__ import annotations

import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from . import backend

REFRESH_S = 5 * 60


class ReportProvider(QObject):
    updated = Signal()
    added = Signal(bool, str, str, int, str)    # (성공, 안내, 장소 id, 제보 id, 종류)
    cancelled = Signal(bool, str, str)          # (성공, 안내, 장소 id)

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

    def add(self, place_id: str, kind: str, device: str) -> None:
        self._pool.submit(self._add, place_id, kind, device)

    def cancel(self, place_id: str, report_id: int, device: str) -> None:
        self._pool.submit(self._cancel, place_id, report_id, device)

    @staticmethod
    def _http_error(exc: urllib.error.HTTPError) -> str:
        return backend.error_message(exc)

    def _add(self, place_id: str, kind: str, device: str) -> None:
        try:
            d = backend.call("report", {"task": "add", "place_id": place_id, "kind": kind,
                                        "device": device}, timeout=20)
            self._fetched_at = 0.0              # 내 제보가 바로 보이도록 다음 want() 에서 다시 받는다
            msg = ("다른 분들께 '지금은 괜찮아요' 로 보여 드릴게요." if kind == "ok" else
                   "다른 분들께도 함께 보여 드릴게요.\n잘못 눌렀다면 '내 제보 취소' 를 누르세요.")
            self.added.emit(True, msg, place_id, int(d.get("id") or 0), kind)
        except urllib.error.HTTPError as exc:
            self.added.emit(False, self._http_error(exc), place_id, 0, kind)
        except Exception:
            self.added.emit(False, "인터넷 연결을 확인해 주세요", place_id, 0, kind)

    def _cancel(self, place_id: str, report_id: int, device: str) -> None:
        try:
            backend.call("report", {"task": "cancel", "id": int(report_id), "device": device}, timeout=20)
            self._fetched_at = 0.0
            self.cancelled.emit(True, "제보를 취소했어요.", place_id)
        except urllib.error.HTTPError as exc:
            self._fetched_at = 0.0
            self.cancelled.emit(False, self._http_error(exc), place_id)
        except Exception:
            self.cancelled.emit(False, "인터넷 연결을 확인해 주세요", place_id)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
