"""지도 화면 — 캔버스 + 오버레이 컨트롤 + 주변 쉼터 목록."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..ai import CROWD_ENABLED, Analysis, active_events, analyze_all, rank
from ..config import MARKER_ARROW, MARKER_AUTO, MARKER_HIGHLIGHT, AppState
from ..catalog import places_for
from ..theme import Palette
from .common import (
    Card,
    IconButton,
    IconLabel,
    Pill,
    crowd_color,
    elide,
    mono,
    nuisance_color,
    set_prop,
    ui_font,
)
from .mapcanvas import MapCanvas

SORTS = [
    ("balanced", "추천순"),
    ("close", "가까운순"),
    ("cool", "온도순"),
    ("quiet", "조용한순"),
    ("free", "눈치없는순"),
]


class PlaceRow(QFrame):
    """우측 목록의 한 줄."""

    selected = Signal(str)
    opened = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("cardFlat")
        self.setProperty("hoverable", True)
        self.setCursor(Qt.PointingHandCursor)
        self._pid = ""
        self._name_text = "-"
        self._meta_text = "-"
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(11)

        self.icon = IconLabel("building", 19, "#22D3EE", 1.9)
        lay.addWidget(self.icon, 0, Qt.AlignVCenter)

        mid = QVBoxLayout()
        mid.setSpacing(3)
        self.name = QLabel("-")
        self.name.setFont(ui_font(13, QFont.Bold))
        self.name.setMinimumWidth(0)
        self.name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.meta = QLabel("-")
        self.meta.setObjectName("mute")
        self.meta.setFont(mono(9, QFont.Normal, 0.6))
        self.meta.setMinimumWidth(0)
        self.meta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        mid.addWidget(self.name)
        mid.addWidget(self.meta)
        lay.addLayout(mid, 1)

        right = QVBoxLayout()
        right.setSpacing(4)
        right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.crowd = QLabel("-")
        self.crowd.setFont(mono(9, QFont.Bold, 0.5))
        self.crowd.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.crowd.setFixedWidth(74)
        self.nuis = QLabel("-")
        self.nuis.setFont(mono(9, QFont.Normal, 0.5))
        self.nuis.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.nuis.setFixedWidth(74)
        right.addWidget(self.crowd)
        right.addWidget(self.nuis)
        lay.addLayout(right)

    def set_analysis(self, a: Analysis, p: Palette) -> None:
        self._pid = a.place.id
        self.icon.set_icon(a.place.icon)
        self.icon.set_color(p.accent if a.crowd.open_now else p.text_mute)
        temp = f"실내 {a.indoor:.0f}°C" if a.crowd.open_now else "운영 종료"
        marker = "화살표" if a.place.inside_mall else "건물"
        self._name_text = a.place.name
        self._meta_text = f"{temp} · 도보 {a.walk_min}분 · {marker}"
        self._apply_texts()
        if CROWD_ENABLED:
            cc = crowd_color(p, a.crowd.key)
            self.crowd.setText(a.crowd.level)
            self.crowd.setStyleSheet(f"color: {cc.name()};")
        else:
            self.crowd.setText("쾌적 " + str(a.comfort))
            self.crowd.setStyleSheet(f"color: {p.accent};")
        nc = nuisance_color(p, a.nuisance.key)
        self.nuis.setText(f"민폐 {a.nuisance.score}")
        self.nuis.setStyleSheet(f"color: {nc.name()};")

    def _apply_texts(self) -> None:
        """가용 폭에 맞춰 이름/메타를 줄임표 처리."""
        budget = max(90, self.width() - 74 - 19 - 46)
        self.name.setText(elide(self._name_text, self.name.font(), budget))
        self.meta.setText(elide(self._meta_text, self.meta.font(), budget))

    def resizeEvent(self, ev) -> None:
        self._apply_texts()
        super().resizeEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self.selected.emit(self._pid)

    def mouseDoubleClickEvent(self, ev) -> None:
        self.opened.emit(self._pid)


class MapLegend(Card):
    """마커 표기 방식 안내 + 즉시 변경."""

    styleChanged = Signal(str)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent, padding=14, spacing=9)
        self.state = state
        self.setFixedWidth(268)
        lay = self.body()

        head = QHBoxLayout()
        head.setSpacing(8)
        self.icon = IconLabel("layers", 15, "#22D3EE", 2.0)
        t = QLabel("표기 방식")
        t.setFont(ui_font(13, QFont.Bold))
        head.addWidget(self.icon)
        head.addWidget(t)
        head.addStretch(1)
        lay.addLayout(head)

        self.combo = QComboBox()
        self.combo.addItem("자동 (건물+화살표)", MARKER_AUTO)
        self.combo.addItem("항상 건물 하이라이트", MARKER_HIGHLIGHT)
        self.combo.addItem("항상 화살표", MARKER_ARROW)
        self.combo.currentIndexChanged.connect(
            lambda i: self.styleChanged.emit(self.combo.itemData(i))
        )
        lay.addWidget(self.combo)

        self.hl_row, self.hl_label = self._legend_row("건물 전체 하이라이트")
        self.ar_row, self.ar_label = self._legend_row("상가 내 업소 — 화살표 지시")
        lay.addWidget(self.hl_row)
        lay.addWidget(self.ar_row)

        tip = QLabel("우클릭 — 현재 위치 직접 지정")
        tip.setObjectName("mute")
        tip.setFont(mono(9, QFont.Normal, 0.5))
        lay.addWidget(tip)

    def _legend_row(self, text: str) -> tuple[QWidget, QLabel]:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        swatch = QLabel()
        swatch.setFixedSize(16, 16)
        label = QLabel(text)
        label.setObjectName("mute")
        label.setFont(mono(9, QFont.Normal, 0.5))
        label.setWordWrap(True)
        h.addWidget(swatch, 0, Qt.AlignVCenter)
        h.addWidget(label, 1)
        w.swatch = swatch  # type: ignore[attr-defined]
        return w, label

    def sync(self) -> None:
        idx = self.combo.findData(self.state.get("marker_style"))
        if idx >= 0 and idx != self.combo.currentIndex():
            self.combo.blockSignals(True)
            self.combo.setCurrentIndex(idx)
            self.combo.blockSignals(False)

    def apply_palette(self, p: Palette) -> None:
        self.icon.set_color(p.accent)
        self.hl_row.swatch.setStyleSheet(  # type: ignore[attr-defined]
            f"background: {p.accent_soft}; border: 1px solid {p.accent}; border-radius: 4px;"
        )
        self.ar_row.swatch.setStyleSheet(  # type: ignore[attr-defined]
            "background: transparent; border: none;"
        )
        self.ar_row.swatch.setPixmap(  # type: ignore[attr-defined]
            icons.icon_pixmap("arrow_right", 16, p.accent)
        )


class SelectionPanel(Card):
    """지도에서 선택한 장소의 요약 패널."""

    openRequested = Signal(str)
    closed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, padding=16, spacing=10)
        self.setFixedWidth(340)
        self._pid = ""
        lay = self.body()

        head = QHBoxLayout()
        head.setSpacing(9)
        self.icon = IconLabel("building", 18, "#22D3EE", 1.9)
        self.name = QLabel("-")
        self.name.setFont(ui_font(15, QFont.ExtraBold))
        self.name.setWordWrap(True)
        self.close_btn = IconButton("close", 26, 13, tooltip="닫기")
        self.close_btn.clicked.connect(self.closed.emit)
        head.addWidget(self.icon, 0, Qt.AlignTop)
        head.addWidget(self.name, 1)
        head.addWidget(self.close_btn, 0, Qt.AlignTop)
        lay.addLayout(head)

        self.unit = QLabel("")
        self.unit.setObjectName("dim")
        self.unit.setFont(mono(9, QFont.DemiBold, 0.6))
        lay.addWidget(self.unit)

        pills = QHBoxLayout()
        pills.setSpacing(6)
        self.temp_pill = Pill("--", "thermo")
        self.crowd_pill = Pill("--", "users")
        self.nuis_pill = Pill("--", "star")
        for w in (self.temp_pill, self.crowd_pill, self.nuis_pill):
            pills.addWidget(w)
        pills.addStretch(1)
        lay.addLayout(pills)

        self.headline = QLabel("-")
        self.headline.setObjectName("dim")
        self.headline.setWordWrap(True)
        self.headline.setFont(ui_font(11))
        lay.addWidget(self.headline)

        self.btn = QPushButton("상세 보기")
        self.btn.setObjectName("primary")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(lambda: self.openRequested.emit(self._pid))
        lay.addWidget(self.btn)

    def set_analysis(self, a: Analysis, p: Palette) -> None:
        self._pid = a.place.id
        self.icon.set_icon(a.place.icon)
        self.icon.set_color(p.accent)
        self.name.setText(a.place.name)
        marker = "화살표 지시" if a.place.inside_mall else "건물 하이라이트"
        self.unit.setText(
            f"{a.place.unit or a.place.address} · {marker}"
        )
        self.temp_pill.set_text(f"실내 {a.indoor:.0f}°C" if a.crowd.open_now else "운영 종료")
        self.temp_pill.set_colors(p.accent, p.card)
        if CROWD_ENABLED:
            self.crowd_pill.set_text(f"{a.crowd.level} {a.crowd.percent}%")
            self.crowd_pill.set_colors(crowd_color(p, a.crowd.key).name(), p.card)
        else:
            self.crowd_pill.set_text(f"쾌적 {a.comfort}")
            self.crowd_pill.set_colors(p.accent, p.card)
        self.nuis_pill.set_text(f"민폐도 {a.nuisance.score}")
        self.nuis_pill.set_colors(nuisance_color(p, a.nuisance.key).name(), p.card)
        if a.crowd.by_event:
            note = (a.crowd.headline if CROWD_ENABLED
                    else "인근에서 행사가 진행 중이에요 (평소보다 붐빌 수 있음)")
            self.headline.setText(f"⚠  {note}\n{a.crowd.detail}")
            self.headline.setStyleSheet(f"color: {p.warn};")
        else:
            lead = a.crowd.headline if CROWD_ENABLED else a.nuisance.level
            self.headline.setText(
                f"{lead}\n권장 체류 {a.nuisance.stay_label} · 도보 {a.walk_min}분"
            )
            self.headline.setStyleSheet(f"color: {p.text_dim};")

    def apply_palette(self, p: Palette) -> None:
        self.close_btn.set_color(p.text_dim)


class MapView(QWidget):
    openPlace = Signal(str)
    locateRequested = Signal()
    originPicked = Signal(float, float)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self._analyses: dict[str, Analysis] = {}
        self._sort = "balanced"
        self._selected: str | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 지도 영역 -------------------------------------------------------
        self.map_area = QWidget()
        lay.addWidget(self.map_area, 1)

        self.canvas = MapCanvas(state, self.map_area)
        self.canvas.placeClicked.connect(self._on_pick)
        self.canvas.placeActivated.connect(self.openPlace.emit)
        self.canvas.originPicked.connect(self.originPicked.emit)

        self.legend = MapLegend(state, self.map_area)
        self.legend.styleChanged.connect(self._on_style)

        self.zoom_in = IconButton("plus", 38, 17, parent=self.map_area, tooltip="확대")
        self.zoom_out = IconButton("minus", 38, 17, parent=self.map_area, tooltip="축소")
        self.locate = IconButton("target", 38, 17, parent=self.map_area, tooltip="내 위치")
        self.fit = IconButton("layers", 38, 17, parent=self.map_area, tooltip="전체 보기")
        self.zoom_in.clicked.connect(lambda: self.canvas.zoom_by(1.28))
        self.zoom_out.clicked.connect(lambda: self.canvas.zoom_by(1 / 1.28))
        self.locate.clicked.connect(self._locate)
        self.fit.clicked.connect(self.canvas.fit_all)

        self.panel = SelectionPanel(self.map_area)
        self.panel.openRequested.connect(self.openPlace.emit)
        self.panel.closed.connect(self._clear_selection)
        self.panel.hide()

        # 우측 목록 -------------------------------------------------------
        side = QFrame()
        side.setFixedWidth(356)
        side.setStyleSheet("background: transparent;")
        slay = QVBoxLayout(side)
        slay.setContentsMargins(16, 20, 18, 18)
        slay.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("주변 쉼터")
        title.setFont(ui_font(18, QFont.ExtraBold))
        self.count = QLabel("")
        self.count.setObjectName("mute")
        self.count.setFont(mono(9))
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.count)
        slay.addLayout(head)

        chips = QGridLayout()
        chips.setSpacing(6)
        self.sort_group = QButtonGroup(self)
        self.sort_buttons: dict[str, QPushButton] = {}
        for i, (key, label) in enumerate(SORTS):
            b = QPushButton(label)
            b.setObjectName("chip")
            b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, k=key: self._set_sort(k))
            self.sort_group.addButton(b)
            self.sort_buttons[key] = b
            chips.addWidget(b, i // 3, i % 3)
        wrap = QWidget()
        wrap.setLayout(chips)
        slay.addWidget(wrap)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        self.rows_layout = QVBoxLayout(holder)
        self.rows_layout.setContentsMargins(0, 0, 6, 0)
        self.rows_layout.setSpacing(8)
        self.rows_layout.addStretch(1)
        scroll.setWidget(holder)
        slay.addWidget(scroll, 1)

        self.rows: list[PlaceRow] = []
        lay.addWidget(side)

    # ------------------------------------------------------------------
    def resizeEvent(self, ev) -> None:
        w = self.map_area.width()
        h = self.map_area.height()
        self.canvas.setGeometry(0, 0, w, h)
        self.legend.adjustSize()
        self.legend.move(18, 18)
        x = w - 56
        for i, b in enumerate((self.zoom_in, self.zoom_out, self.locate, self.fit)):
            b.move(x, 18 + i * 46)
        self.panel.adjustSize()
        self.panel.move(18, h - self.panel.height() - 18)
        super().resizeEvent(ev)

    def _locate(self) -> None:
        """현재 위치로 이동하고, 동시에 위치를 다시 확인한다."""
        self.canvas.center_on(self.state.origin, 16)
        self.locateRequested.emit()

    def _on_style(self, style: str) -> None:
        self.state.set("marker_style", style)

    def _set_sort(self, key: str) -> None:
        self._sort = key
        self.refresh()

    def _on_pick(self, pid: str) -> None:
        self._selected = pid
        self.canvas.set_selected(pid)
        a = self._analyses.get(pid)
        if a:
            self.panel.set_analysis(a, self.state.palette)
            self.panel.show()
            self.panel.adjustSize()
            self.panel.move(18, self.map_area.height() - self.panel.height() - 18)
        for row in self.rows:
            set_prop(row, "selected", row._pid == pid)

    def _clear_selection(self) -> None:
        self._selected = None
        self.canvas.set_selected(None)
        self.panel.hide()
        for row in self.rows:
            set_prop(row, "selected", False)

    def focus_place(self, pid: str) -> None:
        a = self._analyses.get(pid)
        if a:
            self.canvas.center_on(a.place.latlon, 17)
            self._on_pick(pid)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        state = self.state
        p = state.palette
        hour, minute, weekday = state.now()
        places = places_for(state.mode, origin=state.origin,
                            radius_m=float(state.get('search_radius')))
        analyses = analyze_all(places, state.mode, hour, minute, weekday,
                               state.target_temp, origin=state.origin)
        if state.get("only_official"):
            analyses = [a for a in analyses if a.place.official]
        analyses = [a for a in analyses if a.walk_min <= int(state.get("max_walk"))]
        self._analyses = {a.place.id: a for a in analyses}

        events = active_events(state.mode, hour, weekday, state.origin)
        self.canvas.set_data(analyses, events)
        self.legend.sync()

        for key, b in self.sort_buttons.items():
            set_prop(b, "active", key == self._sort)

        ranked = rank(analyses, prefer=self._sort)
        self.count.setText(f"{len(ranked)}곳")

        while len(self.rows) < len(ranked):
            row = PlaceRow()
            row.selected.connect(self._row_selected)
            row.opened.connect(self.openPlace.emit)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
            self.rows.append(row)
        for i, row in enumerate(self.rows):
            if i < len(ranked):
                row.setVisible(True)
                row.set_analysis(ranked[i], p)
                set_prop(row, "selected", ranked[i].place.id == self._selected)
            else:
                row.setVisible(False)

        if self._selected and self._selected in self._analyses:
            self.panel.set_analysis(self._analyses[self._selected], p)
        else:
            self._clear_selection()

    def _row_selected(self, pid: str) -> None:
        a = self._analyses.get(pid)
        if a:
            self.canvas.center_on(a.place.latlon)
        self._on_pick(pid)

    def apply_palette(self, p: Palette) -> None:
        pass
