"""홈 화면."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..ai import active_events, analyze_all, rank
from ..config import AppState
from ..catalog import places_for
from ..models import COOLING, HEATING
from ..theme import Palette
from .common import (
    Card,
    IconLabel,
    Pill,
    SectionTitle,
    add_shadow,
    mono,
    set_prop,
    ui_font,
)
from .mapcanvas import MapCanvas
from .placecard import PlaceCard


class MapPreview(QFrame):
    """홈 화면의 지도 미리보기 (오버레이 포함)."""

    openMap = Signal()

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumHeight(340)
        add_shadow(self, blur=30, alpha=90, dy=6)

        self.canvas = MapCanvas(state, self, compact=True)
        self.canvas.radius = 14

        self.scan = Pill("LIVE SCAN ACTIVE", "target", self, style="soft")
        self.open_btn = QPushButton("전체 지도 열기", self)
        self.open_btn.setObjectName("primary")
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.clicked.connect(self.openMap.emit)
        self.hint = QLabel("건물 하이라이트 · 상가 내 업소는 화살표", self)
        self.hint.setFont(mono(9, QFont.DemiBold, 0.8))

    def resizeEvent(self, ev) -> None:
        m = 14
        self.canvas.setGeometry(m, m, self.width() - m * 2, self.height() - m * 2)
        self.scan.move(m + 14, m + 14)
        self.open_btn.adjustSize()
        self.open_btn.move(self.width() - m - self.open_btn.width() - 14,
                           self.height() - m - self.open_btn.height() - 14)
        self.hint.adjustSize()
        self.hint.move(m + 14, self.height() - m - self.hint.height() - 16)
        super().resizeEvent(ev)

    def apply_palette(self, p: Palette) -> None:
        self.scan.set_colors(p.accent, p.panel)
        self.hint.setStyleSheet(f"color: {p.text_mute};")


class ModeCard(Card):
    """냉방/난방 전환 + 목표 온도."""

    modeChanged = Signal(str)
    targetChanged = Signal(float)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent, padding=22, spacing=14)
        self.state = state
        self.setFixedWidth(330)
        lay = self.body()

        title = QLabel("Active Mode")
        title.setFont(ui_font(20, QFont.ExtraBold))
        self.sub = QLabel("-")
        self.sub.setObjectName("dim")
        self.sub.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(self.sub)
        lay.addSpacing(4)

        self.buttons: dict[str, QPushButton] = {}
        for key, label, icon in ((COOLING, "냉방", "snow"), (HEATING, "난방", "flame")):
            btn = QPushButton(f"   {label}")
            btn.setObjectName("modeOption")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(False)
            btn.clicked.connect(lambda _=False, k=key: self.modeChanged.emit(k))
            btn.setProperty("iconName", icon)
            self.buttons[key] = btn
            lay.addWidget(btn)

        lay.addSpacing(6)
        div = QFrame()
        div.setObjectName("divider")
        lay.addWidget(div)

        cap = QLabel("TARGET TEMP")
        cap.setObjectName("label")
        lay.addWidget(cap)

        row = QHBoxLayout()
        self.temp_label = QLabel("22°C")
        self.temp_label.setObjectName("bigNum")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(16, 30)
        self.slider.valueChanged.connect(self._on_slider)
        row.addWidget(self.temp_label)
        row.addStretch(1)
        row.addWidget(self.slider, 1)
        lay.addLayout(row)

        self.note = QLabel("")
        self.note.setObjectName("mute")
        self.note.setFont(mono(9, QFont.Normal, 0.6))
        self.note.setWordWrap(True)
        lay.addWidget(self.note)

    def _on_slider(self, v: int) -> None:
        self.temp_label.setText(f"{v}°C")
        self.targetChanged.emit(float(v))

    def refresh(self) -> None:
        p = self.state.palette
        self.sub.setText(p.tagline)
        for key, btn in self.buttons.items():
            set_prop(btn, "active", key == self.state.mode)
            from .. import icons

            color = p.accent_ink if key == self.state.mode else p.text_dim
            btn.setIcon(icons.qicon(btn.property("iconName"), 19, color))
            btn.setIconSize(icons.icon_size(19))
        self.slider.blockSignals(True)
        self.slider.setValue(int(self.state.target_temp))
        self.slider.blockSignals(False)
        self.temp_label.setText(f"{int(self.state.target_temp)}°C")
        self.note.setText(
            "목표 온도를 기준으로 쾌적 점수를 계산합니다."
            if self.state.mode == COOLING
            else "난방 모드에서는 목표보다 따뜻한 곳을 높게 평가합니다."
        )

    def apply_palette(self, p: Palette) -> None:
        self.refresh()


class OutdoorBadge(Card):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, padding=16, spacing=2)
        self.setFixedWidth(180)
        lay = self.body()
        cap = QLabel("OUTDOOR")
        cap.setObjectName("label")
        cap.setAlignment(Qt.AlignCenter)
        self.temp = QLabel("--")
        self.temp.setFont(ui_font(30, QFont.ExtraBold))
        self.temp.setAlignment(Qt.AlignCenter)
        self.alert = Pill("정상", "info", style="soft")
        lay.addWidget(cap)
        lay.addWidget(self.temp)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.alert)
        row.addStretch(1)
        lay.addLayout(row)

    def set_weather(self, w, p: Palette) -> None:
        self.temp.setText(f"{w.outdoor:.0f}°C")
        self.temp.setStyleSheet(f"color: {p.accent};")
        if w.alert:
            self.alert.set_text(w.alert)
            self.alert.set_icon("alert")
            self.alert.set_colors(p.bad, p.card)
        else:
            self.alert.set_text(w.condition)
            self.alert.set_icon("info")
            self.alert.set_colors(p.text_dim, p.card)


class EventStrip(Card):
    """진행 중 이벤트 안내."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, padding=16, spacing=10)
        lay = self.body()
        head = QHBoxLayout()
        head.setSpacing(9)
        self.icon = IconLabel("alert", 17, "#FBBF24", 2.0)
        title = QLabel("진행 중인 주변 이벤트")
        title.setFont(ui_font(14, QFont.Bold))
        head.addWidget(self.icon)
        head.addWidget(title)
        head.addStretch(1)
        lay.addLayout(head)
        self.body_label = QLabel("-")
        self.body_label.setObjectName("dim")
        self.body_label.setWordWrap(True)
        lay.addWidget(self.body_label)

    def set_events(self, events, p: Palette) -> None:
        from ..ai import CROWD_ENABLED

        self.icon.set_color(p.warn)
        lines = [f"· {e.title} ({e.start_hour:02d}:00–{e.end_hour:02d}:00) — {e.note}"
                 for e in events]
        lines.append(
            "영향권 내 쉼터는 '사람이 이벤트로 인해 많아요'로 표시됩니다."
            if CROWD_ENABLED else
            "영향권 내 쉼터에는 행사 안내가 표시됩니다. 혼잡도 수치는 준비 중입니다."
        )
        self.body_label.setText("\n".join(lines))


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

        content = QWidget()
        scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(32, 26, 32, 34)
        lay.setSpacing(22)

        # 헤더 -----------------------------------------------------------
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(6)
        self.title = QLabel("가장 쾌적한 장소를 찾아보세요.")
        self.title.setObjectName("h1")
        self.subtitle = QLabel("Find the most comfortable place.")
        self.subtitle.setObjectName("mute")
        self.subtitle.setFont(mono(11, QFont.Normal, 0.8))
        title_box.addWidget(self.title)
        title_box.addWidget(self.subtitle)
        header.addLayout(title_box, 1)
        self.badge = OutdoorBadge()
        header.addWidget(self.badge, 0, Qt.AlignTop)
        lay.addLayout(header)

        # 모드 + 지도 -----------------------------------------------------
        row = QHBoxLayout()
        row.setSpacing(20)
        self.mode_card = ModeCard(state)
        # 시그널을 연결하지 않아 카드에서 모드를 바꿔도 반응이 없었다
        self.mode_card.modeChanged.connect(self._set_mode)
        self.mode_card.targetChanged.connect(self._set_target)
        self.preview = MapPreview(state)
        self.preview.openMap.connect(self.openMap.emit)
        row.addWidget(self.mode_card)
        row.addWidget(self.preview, 1)
        lay.addLayout(row)

        # 이벤트 ----------------------------------------------------------
        self.event_strip = EventStrip()
        lay.addWidget(self.event_strip)

        # 추천 ------------------------------------------------------------
        self.rec_title = SectionTitle("AI 추천", "sparkle", size=21)
        self.rec_count = QLabel("")
        self.rec_count.setObjectName("mute")
        self.rec_count.setFont(mono(10))
        self.rec_title.add_widget(self.rec_count)
        lay.addWidget(self.rec_title)

        self.cards_holder = QWidget()
        self.grid = QGridLayout(self.cards_holder)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(18)
        for col in range(3):
            self.grid.setColumnStretch(col, 1)
        lay.addWidget(self.cards_holder)

        self.cards: list[PlaceCard] = []
        for i in range(6):
            c = PlaceCard(show_favorite=True)
            c.openRequested.connect(self.openPlace.emit)
            c.favoriteToggled.connect(self._toggle_fav)
            c.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            self.grid.addWidget(c, i // 3, i % 3)
            self.cards.append(c)

        lay.addStretch(1)

    def _toggle_fav(self, pid: str) -> None:
        self.state.toggle_favorite(pid)

    def _set_mode(self, mode: str) -> None:
        self.state.mode = mode

    def _set_target(self, value: float) -> None:
        self.state.target_temp = value

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        state = self.state
        p = state.palette
        hour, minute, weekday = state.now()

        places = places_for(state.mode, origin=state.origin,
                            radius_m=float(state.get('search_radius')),
                            include_ai=bool(state.get("ai_candidates")))
        analyses = analyze_all(places, state.mode, hour, minute, weekday,
                               state.target_temp, origin=state.origin)
        if state.get("only_official"):
            analyses = [a for a in analyses if a.place.official]
        analyses = [a for a in analyses if a.walk_min <= int(state.get("max_walk"))]
        ranked = rank(analyses)

        from ..ai import live_weather
        self.badge.set_weather(live_weather(state.mode, hour, minute, state.origin), p)
        self.mode_card.refresh()
        self.preview.canvas.set_data(analyses, active_events(state.mode, hour, weekday, state.origin))
        self.preview.canvas.fit_all()

        events = active_events(state.mode, hour, weekday, state.origin)
        self.event_strip.setVisible(bool(events))
        if events:
            self.event_strip.set_events(events, p)

        self.rec_count.setText(f"{len(ranked)}곳 분석 · {state.clock_label()}")
        top = ranked[:6]
        for i, card in enumerate(self.cards):
            if i < len(top):
                card.setVisible(True)
                card.set_analysis(top[i], p, favorite=state.is_favorite(top[i].place.id))
            else:
                card.setVisible(False)

    def apply_palette(self, p: Palette) -> None:
        self.title.setText(
            "가장 시원한 장소를 찾아보세요." if p.key == COOLING
            else "가장 따뜻한 장소를 찾아보세요."
        )
        self.subtitle.setText(
            "Find the coolest place nearby." if p.key == COOLING
            else "Find the warmest place nearby."
        )
