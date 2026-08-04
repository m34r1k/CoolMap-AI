"""좌측 사이드바 내비게이션."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..config import AppState
from ..models import COOLING
from ..theme import Palette
from .common import mono, set_prop

NAV_ITEMS = [
    ("home", "홈", "home"),
    ("map", "지도", "map"),
    ("favorites", "즐겨찾기", "heart"),
    ("ai", "AI 추천", "sparkle"),
    ("settings", "설정", "gear"),
]


class BrandLogo(QWidget):
    """CoolMap 심볼 — 냉/온 그라디언트 핀."""

    def __init__(self, size: int = 46, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._mode = COOLING

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.update()

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.width()
        p.translate(s * 0.5, s * 0.5)
        p.scale(s / 24.0, s / 24.0)
        p.translate(-12, -12)

        pin = QPainterPath(QPointF(12, 22.4))
        pin.cubicTo(5.4, 14.6, 3.6, 12.4, 3.6, 9.4)
        pin.cubicTo(3.6, 4.9, 7.4, 1.6, 12, 1.6)
        pin.cubicTo(16.6, 1.6, 20.4, 4.9, 20.4, 9.4)
        pin.cubicTo(20.4, 12.4, 18.6, 14.6, 12, 22.4)

        hole = QPainterPath()
        hole.addEllipse(QPointF(12, 9.2), 3.5, 3.5)
        shape = pin.subtracted(hole)

        grad = QLinearGradient(0, 1, 0, 22)
        if self._mode == COOLING:
            grad.setColorAt(0.0, QColor("#9BE4FA"))
            grad.setColorAt(0.52, QColor("#3AA9E0"))
            grad.setColorAt(1.0, QColor("#F2542D"))
        else:
            grad.setColorAt(0.0, QColor("#7FC7E8"))
            grad.setColorAt(0.42, QColor("#F2542D"))
            grad.setColorAt(1.0, QColor("#FF9A3C"))
        p.fillPath(shape, grad)

        # 상단 하이라이트
        gloss = QColor(255, 255, 255, 60)
        glosspath = QPainterPath()
        glosspath.addEllipse(QPointF(9.0, 6.0), 3.4, 2.2)
        p.fillPath(glosspath, gloss)
        p.end()


class NavButton(QPushButton):
    def __init__(self, key: str, label: str, icon: str, parent: QWidget | None = None):
        super().__init__(f"   {label}", parent)
        self.key = key
        self.icon_name = icon
        self.setObjectName("navItem")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(50)


class Sidebar(QFrame):
    navigate = Signal(str)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(252)
        self.state = state
        self._current = "home"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 24, 20, 22)
        lay.setSpacing(6)

        # 브랜드 ----------------------------------------------------------
        brand = QHBoxLayout()
        brand.setSpacing(12)
        self.logo = BrandLogo(44)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.title = QLabel("CoolMap AI")
        self.title.setObjectName("brandTitle")
        self.sub = QLabel("CLIMATE CONTROL CENTER")
        self.sub.setObjectName("brandSub")
        text.addWidget(self.title)
        text.addWidget(self.sub)
        brand.addWidget(self.logo, 0, Qt.AlignTop)
        brand.addLayout(text, 1)
        lay.addLayout(brand)
        lay.addSpacing(26)

        # 내비게이션 -------------------------------------------------------
        self.buttons: dict[str, NavButton] = {}
        for key, label, icon in NAV_ITEMS[:-1]:
            b = NavButton(key, label, icon)
            b.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
            lay.addWidget(b)
            self.buttons[key] = b

        lay.addStretch(1)

        key, label, icon = NAV_ITEMS[-1]
        b = NavButton(key, label, icon)
        b.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
        lay.addWidget(b)
        self.buttons[key] = b

        lay.addSpacing(10)
        self.clock = QLabel("")
        self.clock.setObjectName("mute")
        self.clock.setFont(mono(9, QFont.Normal, 0.8))
        self.clock.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.clock)

    # ------------------------------------------------------------------
    def set_current(self, key: str) -> None:
        self._current = key
        self.apply_palette(self.state.palette)

    def apply_palette(self, p: Palette) -> None:
        self.logo.set_mode(p.key)
        for key, btn in self.buttons.items():
            active = key == self._current
            set_prop(btn, "active", active)
            color = p.accent_ink if active else (p.accent if key == "ai" else p.text_dim)
            btn.setIcon(icons.qicon(btn.icon_name, 21, color))
            btn.setIconSize(icons.icon_size(21))
        self.clock.setText(self.state.clock_label())

    def refresh_clock(self) -> None:
        self.clock.setText(self.state.clock_label())
