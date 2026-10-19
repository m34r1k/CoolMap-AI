"""물어보기 — 쉼터에 대해 말로 묻고 답을 듣는다.

타자가 어려운 사람도 쓸 수 있게 '누르기만 하면 되는 질문' 을 늘 보여 준다.
mobile/src/app/(tabs)/chat.tsx 와 같은 구성이다.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import icons, providers
from ..assistant import ChatReply, greeting, respond, suggestions
from ..config import AppState
from ..plain import chat_context, nearby
from ..theme import Palette
from .common import ui_font
from .placecard import PlaceRow, TopCard

CONTENT_WIDTH = 860


def _rich(text: str, accent: str) -> str:
    """assistant 의 <b>…</b> · \\n 만 HTML 로 바꾼다 (나머지는 이스케이프)."""
    out = html.escape(text).replace("&lt;b&gt;", f"<b style='color:{accent}'>").replace("&lt;/b&gt;", "</b>")
    return out.replace("\n", "<br>")


class ChatView(QWidget):
    openPlace = Signal(str)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self._mode: str | None = None
        self._req = 0
        self._pending: dict[int, tuple[str, QWidget]] = {}     # 요청 번호 → (질문, '생각 중' 말풍선)
        self._history: list[dict] = []                         # 직전 대화 {q, a}
        chat = providers.chat_provider()
        chat.answered.connect(self._on_answered)
        chat.failed.connect(self._on_failed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.scroll, 1)

        page = QWidget()
        self.scroll.setWidget(page)
        center = QHBoxLayout(page)
        center.setContentsMargins(32, 22, 32, 22)
        content = QWidget()
        content.setMaximumWidth(CONTENT_WIDTH)
        center.addStretch(1)
        center.addWidget(content, 100)
        center.addStretch(1)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        lay.setAlignment(Qt.AlignTop)

        title = QLabel("물어보기")
        title.setFont(ui_font(28, QFont.ExtraBold))
        self.subtitle = QLabel("쉼터 · 날씨 · 앱 쓰는 법을 물어보세요")
        self.subtitle.setFont(ui_font(16))
        lay.addWidget(title)
        lay.addWidget(self.subtitle)

        self.messages = QVBoxLayout()
        self.messages.setSpacing(14)
        lay.addLayout(self.messages)

        # 아래쪽: 누르기만 하면 되는 질문 + 입력창
        bottom = QFrame()
        bottom.setObjectName("topbar")
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(32, 12, 32, 16)
        bl.setSpacing(10)
        inner = QWidget()
        inner.setMaximumWidth(CONTENT_WIDTH)
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(10)
        self.quick = QGridLayout()
        self.quick.setSpacing(8)
        self.quick_buttons: list[QPushButton] = []
        for i in range(6):
            b = QPushButton("")
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(44)
            b.setFont(ui_font(15, QFont.Bold))
            b.clicked.connect(lambda _=False, btn=b: self.send(btn.text(), quick=True))
            self.quick.addWidget(b, i // 3, i % 3)
            self.quick_buttons.append(b)
        il.addLayout(self.quick)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("예) 가장 가까운 쉼터는 어디야?")
        self.input.setFont(ui_font(17))
        self.input.setMinimumHeight(52)
        self.input.returnPressed.connect(lambda: self.send(self.input.text()))
        self.send_btn = QPushButton("  보내기")
        self.send_btn.setObjectName("primary")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setMinimumHeight(52)
        self.send_btn.clicked.connect(lambda: self.send(self.input.text()))
        row.addWidget(self.input, 1)
        row.addWidget(self.send_btn)
        il.addLayout(row)

        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(inner, 100)
        h.addStretch(1)
        bl.addLayout(h)
        root.addWidget(bottom)

    # ------------------------------------------------------------------
    def _bubble_user(self, text: str) -> QWidget:
        p = self.state.palette
        lab = QLabel(text)
        lab.setFont(ui_font(17, QFont.DemiBold))
        lab.setWordWrap(True)
        lab.setStyleSheet(f"background: {p.accent}; color: {p.accent_ink}; border-radius: 16px; padding: 10px 14px;")
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(80, 0, 0, 0)
        h.addStretch(1)
        h.addWidget(lab)
        return wrap

    def _bubble_ai(self, reply: ChatReply, thinking: bool = False) -> QWidget:
        p = self.state.palette
        box = QFrame()
        box.setObjectName("card")
        v = QVBoxLayout(box)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(12)
        lab = QLabel(_rich(reply.text, p.accent))
        if thinking:
            lab.setStyleSheet(f"color: {p.text_dim};")
        lab.setTextFormat(Qt.RichText)
        lab.setWordWrap(True)
        lab.setFont(ui_font(17))
        if not thinking:
            lab.setStyleSheet("line-height: 150%;")
        v.addWidget(lab)
        for i, a in enumerate(reply.places):
            if i == 0:
                card = TopCard()
                card.set_analysis(a, self.state)
                card.openRequested.connect(self.openPlace.emit)
                v.addWidget(card)
            else:
                row = PlaceRow()
                row.set_analysis(a, self.state)
                row.clicked.connect(self.openPlace.emit)
                v.addWidget(row)
        return box

    def _restart(self) -> None:
        while self.messages.count():
            item = self.messages.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.messages.addWidget(self._bubble_ai(greeting(self.state)))
        self._pending.clear()
        self._history.clear()

    def send(self, text: str, quick: bool = False) -> None:
        """누르기만 하면 되는 질문(quick)은 규칙으로 바로 답한다 (빠르고, AI 호출 한도를 아낀다).
        직접 쓴 질문은 Gemini 에게 묻고, 한도 초과 · 인터넷 끊김이면 규칙 답으로 대신한다."""
        text = text.strip()
        if not text:
            return
        self.input.clear()
        user = self._bubble_user(text)
        self.messages.addWidget(user)
        if quick:
            self.messages.addWidget(self._bubble_ai(respond(self.state, text)))
        else:
            self._req += 1
            bubble = self._bubble_ai(ChatReply("생각하고 있어요…"), thinking=True)
            self.messages.addWidget(bubble)
            self._pending[self._req] = (text, bubble)
            providers.chat_provider().ask(self._req, text, chat_context(self.state), self._history[-2:])
        # 질문과 답의 첫 줄이 보이게 (맨 끝으로 내리면 답 문장이 장소 카드에 밀려 사라진다)
        QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(
            max(0, user.mapTo(self.scroll.widget(), user.rect().topLeft()).y() - 12)))

    def _replace(self, req: int, reply: ChatReply) -> None:
        item = self._pending.pop(req, None)
        if item is None:                    # 모드가 바뀌어 대화를 지웠다
            return
        question, bubble = item
        i = self.messages.indexOf(bubble)
        if i < 0:
            return
        self.messages.insertWidget(i, self._bubble_ai(reply))
        self.messages.removeWidget(bubble)
        bubble.deleteLater()
        self._history.append({"q": question, "a": reply.text})

    def _on_answered(self, req: int, d: dict) -> None:
        by_id = {a.place.id: a for a in nearby(self.state)}
        places = [by_id[i] for i in d.get("place_ids") or [] if i in by_id]
        self._replace(req, ChatReply(str(d.get("answer", "")), places))

    def _on_failed(self, req: int, _msg: str) -> None:
        item = self._pending.get(req)
        if item is not None:
            self._replace(req, respond(self.state, item[0]))

    def refresh(self) -> None:
        p = self.state.palette
        for b, q in zip(self.quick_buttons, suggestions(self.state.mode)):
            b.setText(q)
            b.setStyleSheet(f"QPushButton {{ color: {p.accent}; border: 1.5px solid {p.accent}; border-radius: 20px; }}"
                            f"QPushButton:hover {{ background: {p.accent_soft}; }}")
        self.subtitle.setStyleSheet(f"color: {p.text_dim};")
        self.send_btn.setIcon(icons.qicon("send", 18, p.accent_ink))
        # 모드가 바뀌면 인사부터 다시
        if self._mode != self.state.mode:
            self._mode = self.state.mode
            self._restart()

    def apply_palette(self, p: Palette) -> None:
        pass
