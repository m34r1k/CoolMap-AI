"""물어보기 — CoolMap 서버(chat 함수)에서 Gemini 에게 묻는다.

mobile/src/backend.ts 의 askChat 과 같은 서버를 쓴다. Gemini 키는 서버에만 있다.
쉼터 · 날씨 · 앱에 관한 질문만 답하고, 그 밖은 서버가 정한 문장으로 거절한다.
실패(한도 초과 · 인터넷 끊김)하면 failed 를 내고, 화면은 규칙 기반 답(assistant.py)으로 대신한다.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from . import backend


class ChatProvider(QObject):
    answered = Signal(int, dict)    # (요청 번호, {answer, place_ids, on_topic})
    failed = Signal(int, str)       # (요청 번호, 쉬운 말 오류)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chat")

    def ask(self, req: int, question: str, context: dict, history: list[dict]) -> None:
        self._pool.submit(self._ask, req, question, context, history)

    def _ask(self, req: int, question: str, context: dict, history: list[dict]) -> None:
        if not backend.enabled():
            self.failed.emit(req, "서버에 연결할 수 없어요")
            return
        try:
            d = backend.call("chat", {"question": question, **context, "history": history[-2:]}, timeout=30)
            if not d.get("answer"):
                raise RuntimeError(d.get("error") or "답을 받지 못했어요")
            self.answered.emit(req, d)
        except Exception as exc:
            msg = backend.error_message(exc) if hasattr(exc, "read") else str(exc)
            self.failed.emit(req, msg)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
