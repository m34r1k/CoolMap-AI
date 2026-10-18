"""홈 — "지금 어디로 가면 돼?" 에 바로 답한다.

바깥 기온 → 더위/추위 피하기 → 가장 가까운 쉼터 한 곳(길찾기) → 자주 가는 곳 → 다른 쉼터 몇 곳.
mobile/src/app/(tabs)/index.tsx 와 같은 구성이다.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import icons, providers
from ..ai import analyze, live_weather
from ..catalog import find_by_id
from ..config import AppState
from ..models import COOLING, HEATING
from ..plain import MODE_TITLE, SHELTER_WORD, nearby, nearest_first
from ..theme import Palette
from .common import Card, IconLabel, set_prop, ui_font
from .placecard import PlaceRow, TopCard

#: 내용이 너무 넓게 퍼지지 않게 가운데 이 폭으로 모은다
CONTENT_WIDTH = 860


class WeatherCard(Card):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, padding=20, spacing=0)
        row = QHBoxLayout()
        row.setSpacing(16)
        self.icon = IconLabel("snow", 44, "#22D3EE", 2.0)
        box = QVBoxLayout()
        box.setSpacing(0)
        self.caption = QLabel("지금 바깥 기온")
        self.caption.setFont(ui_font(15))
        self.temp = QLabel("--")
        self.temp.setFont(ui_font(38, QFont.ExtraBold))
        box.addWidget(self.caption)
        box.addWidget(self.temp)
        self.alert = QLabel("")
        self.alert.setFont(ui_font(16, QFont.ExtraBold))
        row.addWidget(self.icon, 0, Qt.AlignVCenter)
        row.addLayout(box, 1)
        row.addWidget(self.alert, 0, Qt.AlignVCenter)
        self.body().addLayout(row)

    def set_weather(self, w, mode: str, p: Palette) -> None:
        hot = mode == COOLING
        self.icon.set_icon("snow" if not hot else "flame")
        self.icon.set_color(p.bad if hot else p.accent_bright)
        self.caption.setStyleSheet(f"color: {p.text_dim};")
        self.temp.setText(f"{w.outdoor:.0f}°C")
        self.alert.setVisible(bool(w.alert))
        self.alert.setText(f"  {w.alert}  ")
        self.alert.setStyleSheet(f"background: {p.warn}; color: {p.bg}; border-radius: 10px; padding: 6px 4px;")


class ModeSwitch(QWidget):
    """더위 피하기 / 추위 피하기."""

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.buttons: dict[str, QPushButton] = {}
        for mode in (COOLING, HEATING):
            b = QPushButton(f"  {MODE_TITLE[mode]}")
            b.setObjectName("modeOption")
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(54)
            b.setFont(ui_font(17, QFont.ExtraBold))
            b.clicked.connect(lambda _=False, m=mode: setattr(self.state, "mode", m))
            lay.addWidget(b, 1)
            self.buttons[mode] = b

    def refresh(self) -> None:
        p = self.state.palette
        for mode, b in self.buttons.items():
            on = mode == self.state.mode
            set_prop(b, "active", on)
            b.setIcon(icons.qicon("snow" if mode == COOLING else "flame", 22,
                                  p.accent_ink if on else p.text_dim))
            b.setIconSize(icons.icon_size(22))


def _heading(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setFont(ui_font(22, QFont.ExtraBold))
    return lab


class HomeView(QWidget):
    openMap = Signal()
    openPlace = Signal(str)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        page = QWidget()
        scroll.setWidget(page)
        center = QHBoxLayout(page)
        center.setContentsMargins(32, 26, 32, 40)
        content = QWidget()
        content.setMaximumWidth(CONTENT_WIDTH)
        center.addStretch(1)
        center.addWidget(content, 100)
        center.addStretch(1)

        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        lay.setAlignment(Qt.AlignTop)

        self.weather = WeatherCard()
        lay.addWidget(self.weather)
        self.modes = ModeSwitch(state)
        lay.addWidget(self.modes)

        lay.addSpacing(10)
        self.best_title = _heading("가장 가까운 쉼터")
        lay.addWidget(self.best_title)
        self.notice = QLabel("")
        self.notice.setFont(ui_font(16, QFont.Bold))
        self.notice.setWordWrap(True)
        lay.addWidget(self.notice)
        self.best = TopCard()
        self.best.openRequested.connect(self.openPlace.emit)
        lay.addWidget(self.best)

        self.fav_title = _heading("자주 가는 곳")
        self.fav_box = QVBoxLayout()
        self.fav_box.setSpacing(8)
        lay.addSpacing(10)
        lay.addWidget(self.fav_title)
        lay.addLayout(self.fav_box)

        self.rest_title = _heading("다른 쉼터")
        self.rest_box = QVBoxLayout()
        self.rest_box.setSpacing(8)
        lay.addSpacing(10)
        lay.addWidget(self.rest_title)
        lay.addLayout(self.rest_box)

        self.map_btn = QPushButton("지도에서 모두 보기")
        self.map_btn.setCursor(Qt.PointingHandCursor)
        self.map_btn.setMinimumHeight(52)
        self.map_btn.setFont(ui_font(16, QFont.Bold))
        self.map_btn.clicked.connect(self.openMap.emit)
        lay.addWidget(self.map_btn)

    @staticmethod
    def _clear(box: QVBoxLayout) -> None:
        while box.count():
            item = box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _fill(self, box: QVBoxLayout, items) -> None:
        self._clear(box)
        for a in items:
            row = PlaceRow()
            row.set_analysis(a, self.state)
            row.clicked.connect(self.openPlace.emit)
            box.addWidget(row)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        state = self.state
        p = state.palette
        hour, minute, weekday = state.now()

        self.weather.set_weather(live_weather(state.mode, hour, minute, state.origin), state.mode, p)
        self.modes.refresh()

        items = nearest_first(nearby(state))
        providers.report_provider().want([a.place.id for a in items[:40]] + list(state.favorites))
        self.best_title.setText(f"가장 가까운 {SHELTER_WORD[state.mode]}")
        if items:
            best = items[0]
            self.best.setVisible(True)
            self.best.set_analysis(best, state)
            closed = not best.open_now
            self.notice.setVisible(closed)
            self.notice.setText("지금 문을 연 쉼터가 주변에 없어요. 가장 가까운 곳을 보여 드려요.")
            self.notice.setStyleSheet(f"color: {p.warn};")
        else:
            self.best.setVisible(False)
            self.notice.setVisible(True)
            self.notice.setText("가까운 곳에 쉼터가 없어요. 지도에서 다른 곳을 찾아보세요.")
            self.notice.setStyleSheet(f"color: {p.text_dim};")

        favs = [q for q in (find_by_id(pid, state.mode, state.origin) for pid in state.favorites) if q]
        fav_items = [analyze(place, state.mode, hour, minute, weekday, state.target_temp,
                             origin=state.origin) for place in favs]
        self.fav_title.setVisible(bool(fav_items))
        self._fill(self.fav_box, fav_items)

        rest = items[1:6]
        self.rest_title.setVisible(bool(rest))
        self._fill(self.rest_box, rest)
        self.map_btn.setVisible(bool(items))
        self.map_btn.setText(f"지도에서 모두 보기 ({len(items)}곳)")
        self.map_btn.setIcon(icons.qicon("map", 20, p.text))

    def apply_palette(self, p: Palette) -> None:
        pass
