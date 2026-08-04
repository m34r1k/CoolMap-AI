"""AI 추천 화면 — CoolMap Intelligence."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..ai import CROWD_ENABLED, Analysis
from ..assistant import QUICK_PROMPTS, greeting, respond
from ..config import AppState
from ..theme import Palette
from .common import (
    Card,
    ClickableCard,
    IconButton,
    IconLabel,
    crowd_color,
    mono,
    nuisance_color,
    ui_font,
)


class UserBubble(QWidget):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch(1)
        self.bubble = QLabel(text)
        self.bubble.setWordWrap(True)
        self.bubble.setMaximumWidth(520)
        self.bubble.setFont(ui_font(13))
        self.bubble.setContentsMargins(18, 14, 18, 14)
        lay.addWidget(self.bubble)

    def apply_palette(self, p: Palette) -> None:
        self.bubble.setStyleSheet(
            f"background: {p.card_alt}; border: 1px solid {p.border_soft};"
            f"border-radius: 16px; color: {p.text};"
        )


class ChatPlaceCard(ClickableCard):
    """대화 안에 들어가는 장소 카드."""

    openRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, padding=0, spacing=0, shadow=False)
        self._pid = ""
        self.setMinimumHeight(180)
        lay = self.body()

        self.banner = _CardBanner()
        lay.addWidget(self.banner)

        stats = QWidget()
        sl = QHBoxLayout(stats)
        sl.setContentsMargins(18, 14, 18, 16)
        sl.setSpacing(24)
        self.crowd_box = self._stat_box("CROWD LEVEL")
        self.nuis_box = self._stat_box("NUISANCE")
        self.air_box = self._stat_box("AIR QUALITY")
        for b in (self.crowd_box, self.nuis_box, self.air_box):
            sl.addWidget(b, 1)
        lay.addWidget(stats)

        self.clicked.connect(lambda: self.openRequested.emit(self._pid))

    def _stat_box(self, caption: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        cap = QLabel(caption)
        cap.setObjectName("label")
        row = QHBoxLayout()
        row.setSpacing(7)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        val = QLabel("-")
        val.setFont(ui_font(12, QFont.DemiBold))
        row.addWidget(dot, 0, Qt.AlignVCenter)
        row.addWidget(val, 1)
        lay.addWidget(cap)
        lay.addLayout(row)
        w.dot = dot   # type: ignore[attr-defined]
        w.val = val   # type: ignore[attr-defined]
        w.cap = cap   # type: ignore[attr-defined]
        return w

    def set_analysis(self, a: Analysis, p: Palette) -> None:
        self._pid = a.place.id
        hours = "24시간 운영" if a.place.always_open else f"{a.place.open_to % 24}시까지 운영"
        self.banner.set_data(a.place.name, hours, f"{a.indoor:.0f}°C", a.place.icon, p)

        if CROWD_ENABLED:
            cc = crowd_color(p, a.crowd.key)
            self.crowd_box.val.setText(f"{a.crowd.level} ({a.crowd.percent}%)")
            self.crowd_box.val.setStyleSheet(f"color: {p.text};")
            self.crowd_box.dot.setStyleSheet(f"background: {cc.name()}; border-radius: 4px;")
        else:
            self.crowd_box.cap.setText("COMFORT")
            self.crowd_box.val.setText(f"{a.comfort}/100")
            self.crowd_box.val.setStyleSheet(f"color: {p.text};")
            self.crowd_box.dot.setStyleSheet(f"background: {p.accent}; border-radius: 4px;")

        nc = nuisance_color(p, a.nuisance.key)
        self.nuis_box.val.setText(f"{a.nuisance.score} · {a.nuisance.level}")
        self.nuis_box.val.setStyleSheet(f"color: {p.text};")
        self.nuis_box.dot.setStyleSheet(f"background: {nc.name()}; border-radius: 4px;")

        aq = "매우 좋음" if a.place.aqi <= 20 else ("좋음" if a.place.aqi <= 35 else "보통")
        self.air_box.val.setText(f"{aq} (AQI {a.place.aqi})")
        self.air_box.val.setStyleSheet(f"color: {p.text};")
        self.air_box.dot.setStyleSheet(
            f"background: {p.good if a.place.aqi <= 35 else p.warn}; border-radius: 4px;")


class _CardBanner(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(112)
        self._title = "-"
        self._sub = "-"
        self._temp = "-"
        self._icon = "building"
        self._p: Palette | None = None

    def set_data(self, title: str, sub: str, temp: str, icon: str, p: Palette) -> None:
        self._title, self._sub, self._temp, self._icon, self._p = title, sub, temp, icon, p
        self.update()

    def paintEvent(self, ev) -> None:
        if self._p is None:
            return
        from .. import icons

        p = self._p
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor(p.accent_deep))
        grad.setColorAt(1.0, QColor(p.card_alt))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawRoundedRect(QRectF(0, 0, w, h + 18), 16, 16)
        painter.fillRect(QRectF(0, h - 18, w, 18), QColor(p.card))

        icons.draw_icon(painter, self._icon, QRectF(w - 96, h - 92, 74, 74),
                        QColor(255, 255, 255, 40), 1.6)

        painter.setPen(QColor(p.text))
        painter.setFont(ui_font(17, QFont.ExtraBold))
        painter.drawText(QRectF(18, h - 62, w - 130, 26), Qt.AlignVCenter | Qt.AlignLeft,
                         self._title)
        painter.setPen(QColor(p.text_dim))
        painter.setFont(mono(9, QFont.DemiBold, 0.6))
        painter.drawText(QRectF(18, h - 38, w - 130, 18), Qt.AlignVCenter | Qt.AlignLeft,
                         self._sub)

        # 온도 배지
        badge = QRectF(w - 86, 14, 68, 26)
        painter.setBrush(QColor(p.accent))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(badge, 13, 13)
        painter.setPen(QColor(p.accent_ink))
        painter.setFont(mono(10, QFont.Bold, 0.4))
        painter.drawText(badge, Qt.AlignCenter, self._temp)
        painter.end()


class AiMessage(QWidget):
    """AI 응답 — 텍스트 + 장소 카드."""

    openPlace = Signal(str)

    def __init__(self, reply, p: Palette, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.card = Card(padding=18, spacing=14)
        self.card.setMinimumWidth(520)
        self.card.setMaximumWidth(660)
        lay.addWidget(self.card)
        lay.addStretch(1)
        body = self.card.body()

        self.text = QLabel(reply.text)
        self.text.setTextFormat(Qt.RichText)
        self.text.setWordWrap(True)
        self.text.setFont(ui_font(13))
        body.addWidget(self.text)

        for i, a in enumerate(reply.places[:3]):
            if i == 0:
                card = ChatPlaceCard()
                card.set_analysis(a, p)
                card.openRequested.connect(self.openPlace.emit)
                body.addWidget(card)
            else:
                body.addWidget(self._mini_row(a, p))

        if reply.note:
            note = QLabel(reply.note)
            note.setObjectName("mute")
            note.setFont(mono(9, QFont.Normal, 0.5))
            note.setWordWrap(True)
            body.addWidget(note)

    def _mini_row(self, a: Analysis, p: Palette) -> QWidget:
        row = ClickableCard(flat=True, padding=12, spacing=0)
        row.setProperty("hoverable", True)
        lay = row.body()
        h = QHBoxLayout()
        h.setSpacing(12)
        icon = IconLabel(a.place.icon, 18, p.accent, 1.9)
        box = QVBoxLayout()
        box.setSpacing(2)
        name = QLabel(a.place.name)
        name.setFont(ui_font(13, QFont.Bold))
        meta = QLabel(f"{a.indoor:.0f}°C · {a.distance_label} · 민폐도 {a.nuisance.score}")
        meta.setObjectName("mute")
        meta.setFont(mono(9, QFont.Normal, 0.5))
        box.addWidget(name)
        box.addWidget(meta)
        chev = IconLabel("chevron_right", 15, p.text_mute, 2.0)
        h.addWidget(icon)
        h.addLayout(box, 1)
        h.addWidget(chev)
        lay.addLayout(h)
        row.clicked.connect(lambda pid=a.place.id: self.openPlace.emit(pid))
        return row

    def apply_palette(self, p: Palette) -> None:
        pass


class ChatView(QWidget):
    openPlace = Signal(str)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self._started = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(0)

        frame = QFrame()
        frame.setObjectName("card")
        lay.addWidget(frame, 1)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(0)

        # 헤더 ------------------------------------------------------------
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(22, 18, 22, 18)
        hl.setSpacing(14)
        self.avatar = QLabel()
        self.avatar.setFixedSize(46, 46)
        self.avatar_icon = IconLabel("sparkle", 22, "#22D3EE", 1.7, self.avatar)
        self.avatar_icon.move(12, 12)
        box = QVBoxLayout()
        box.setSpacing(3)
        title = QLabel("CoolMap Intelligence")
        title.setFont(ui_font(18, QFont.ExtraBold))
        self.status = QLabel("● 실시간 열·이동 데이터 분석 중")
        self.status.setFont(mono(9, QFont.DemiBold, 0.5))
        box.addWidget(title)
        box.addWidget(self.status)
        hl.addWidget(self.avatar)
        hl.addLayout(box, 1)
        fl.addWidget(header)

        div = QFrame()
        div.setObjectName("divider")
        fl.addWidget(div)

        # 메시지 -----------------------------------------------------------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        self.messages = QVBoxLayout(holder)
        self.messages.setContentsMargins(22, 20, 22, 20)
        self.messages.setSpacing(16)
        self.messages.addStretch(1)
        self.scroll.setWidget(holder)
        fl.addWidget(self.scroll, 1)

        div2 = QFrame()
        div2.setObjectName("divider")
        fl.addWidget(div2)

        # 퀵 프롬프트 --------------------------------------------------------
        quick = QWidget()
        ql = QHBoxLayout(quick)
        ql.setContentsMargins(22, 14, 22, 6)
        ql.setSpacing(8)
        self.quick_buttons: list[QPushButton] = []
        for label, prompt, icon in QUICK_PROMPTS:
            b = QPushButton(label)
            b.setObjectName("chip")
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("iconName", icon)
            b.clicked.connect(lambda _=False, t=prompt: self.send(t))
            ql.addWidget(b)
            self.quick_buttons.append(b)
        ql.addStretch(1)
        fl.addWidget(quick)

        # 입력 --------------------------------------------------------------
        input_row = QWidget()
        il = QHBoxLayout(input_row)
        il.setContentsMargins(22, 8, 22, 18)
        il.setSpacing(10)
        self.input = QLineEdit()
        self.input.setPlaceholderText("CoolMap AI에게 물어보세요…  예) 지금 조용하고 시원한 곳")
        self.input.setMinimumHeight(46)
        self.input.returnPressed.connect(lambda: self.send(self.input.text()))
        self.send_btn = IconButton("send", 46, 19, tooltip="보내기")
        self.send_btn.clicked.connect(lambda: self.send(self.input.text()))
        il.addWidget(self.input, 1)
        il.addWidget(self.send_btn)
        fl.addWidget(input_row)

    # ------------------------------------------------------------------
    def _add(self, widget: QWidget) -> None:
        self.messages.insertWidget(self.messages.count() - 1, widget)
        from .common import apply_palette_tree

        apply_palette_tree(widget, self.state.palette)
        # 레이아웃이 확정된 뒤에 맨 아래로 (한 번으로는 높이가 덜 잡힌다)
        for delay in (0, 60, 200):
            QTimer.singleShot(delay, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def send(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.input.clear()
        self._add(UserBubble(text))
        reply = respond(self.state, text)
        msg = AiMessage(reply, self.state.palette)
        msg.openPlace.connect(self.openPlace.emit)
        self._add(msg)

    def refresh(self) -> None:
        if not self._started:
            self._started = True
            msg = AiMessage(greeting(self.state), self.state.palette)
            msg.openPlace.connect(self.openPlace.emit)
            self._add(msg)
        self.status.setText(
            f"● 실시간 열·이동 데이터 분석 중 · {self.state.clock_label()}"
        )

    def apply_palette(self, p: Palette) -> None:
        self.avatar.setStyleSheet(
            f"background: {p.accent_soft}; border: 1px solid {p.accent_deep};"
            f"border-radius: 23px;"
        )
        self.avatar_icon.set_color(p.accent)
        self.status.setStyleSheet(f"color: {p.warn};")
        self.send_btn.set_color(p.accent)
        from .. import icons

        for b in self.quick_buttons:
            b.setIcon(icons.qicon(b.property("iconName"), 14, p.text_dim))
            b.setIconSize(icons.icon_size(14))
