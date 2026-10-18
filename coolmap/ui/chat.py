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

from .. import icons
from ..assistant import ChatReply, greeting, respond, suggestions
from ..config import AppState
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
        self.subtitle = QLabel("쉼터에 대해 궁금한 걸 물어보세요")
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
            b.clicked.connect(lambda _=False, btn=b: self.send(btn.text()))
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

    def _bubble_ai(self, reply: ChatReply) -> QWidget:
        p = self.state.palette
        box = QFrame()
        box.setObjectName("card")
        v = QVBoxLayout(box)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(12)
        lab = QLabel(_rich(reply.text, p.accent))
        lab.setTextFormat(Qt.RichText)
        lab.setWordWrap(True)
        lab.setFont(ui_font(17))
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

    def send(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.input.clear()
        user = self._bubble_user(text)
        self.messages.addWidget(user)
        self.messages.addWidget(self._bubble_ai(respond(self.state, text)))
        # 질문과 답의 첫 줄이 보이게 (맨 끝으로 내리면 답 문장이 장소 카드에 밀려 사라진다)
        QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(
            max(0, user.mapTo(self.scroll.widget(), user.rect().topLeft()).y() - 12)))

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
