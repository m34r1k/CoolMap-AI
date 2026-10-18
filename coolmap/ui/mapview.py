"""지도 화면 — 캔버스 + 확대/축소 버튼 + 주변 쉼터 목록.

정렬은 '가까운 순 / 추천 순' 두 가지만 두고, 지도에서 고른 쉼터는 길찾기 버튼이 있는 큰 카드로 보여 준다.
(표기 방식 같은 세부 설정은 설정 화면의 '고급 설정' 에 있다)
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import icons, providers
from ..ai import Analysis, analyze, rank
from ..catalog import find_by_id
from ..config import AppState
from ..plain import nearby, nearest_first
from ..theme import Palette
from .common import Card, IconButton, set_prop, ui_font
from .mapcanvas import MapCanvas
from .placecard import PlaceRow, TopCard, open_directions

LIST_LIMIT = 40

SORTS = [
    ("near", "가까운 순"),
    ("best", "추천 순"),
]


class MapLegend(Card):
    """공식 쉼터 / AI 추정 구분."""

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent, padding=12, spacing=6)
        self.state = state
        lay = self.body()
        self.official = self._row("공식 쉼터 — 건물이 칠해져요")
        self.ai = self._row("점선 — AI 추정 (공식 아님)")
        lay.addWidget(self.official)
        lay.addWidget(self.ai)
        self.tip = QLabel("오른쪽 클릭 — 내 위치를 직접 지정")
        self.tip.setFont(ui_font(13))
        lay.addWidget(self.tip)

    def _row(self, text: str) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        sw = QLabel()
        sw.setFixedSize(18, 18)
        lab = QLabel(text)
        lab.setFont(ui_font(14, QFont.DemiBold))
        h.addWidget(sw)
        h.addWidget(lab, 1)
        w.swatch = sw  # type: ignore[attr-defined]
        return w

    def sync(self) -> None:
        # AI 추정을 끄면 점선 마커 자체가 안 나오므로 범례도 감춘다
        self.ai.setVisible(bool(self.state.get("ai_candidates"))
                           and providers.candidate_provider().has_key)

    def apply_palette(self, p: Palette) -> None:
        self.official.swatch.setStyleSheet(  # type: ignore[attr-defined]
            f"background: {p.accent_soft}; border: 2px solid {p.accent}; border-radius: 4px;")
        self.ai.swatch.setStyleSheet(  # type: ignore[attr-defined]
            f"background: transparent; border: 2px dashed {p.warn}; border-radius: 4px;")
        self.tip.setStyleSheet(f"color: {p.text_mute};")


class RoutePanel(Card):
    """길 안내 — 걸어서 몇 분 · 단계 안내. (mobile/src/app/route/[id].tsx 와 같은 구성)"""

    closeRequested = Signal()
    otherAppRequested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, padding=18, spacing=10)
        self.setFixedWidth(420)
        lay = self.body()
        self.title = QLabel("-")
        self.title.setFont(ui_font(20, QFont.ExtraBold))
        self.title.setWordWrap(True)
        self.summary = QLabel("")
        self.summary.setFont(ui_font(24, QFont.ExtraBold))
        self.summary.setWordWrap(True)
        self.steps = QLabel("")
        self.steps.setFont(ui_font(16))
        self.steps.setWordWrap(True)
        self.steps.setTextFormat(Qt.RichText)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        scroll.setWidget(self.steps)
        scroll.setMaximumHeight(260)
        self.scroll = scroll
        lay.addWidget(self.title)
        lay.addWidget(self.summary)
        lay.addWidget(scroll)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.other_btn = QPushButton("카카오맵으로 열기")
        self.close_btn = QPushButton("길 안내 끝내기")
        for b in (self.other_btn, self.close_btn):
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(46)
            b.setFont(ui_font(15, QFont.Bold))
        self.other_btn.clicked.connect(self.otherAppRequested.emit)
        self.close_btn.clicked.connect(self.closeRequested.emit)
        row.addWidget(self.other_btn, 1)
        row.addWidget(self.close_btn, 1)
        lay.addLayout(row)

    def show_loading(self, name: str, p: Palette) -> None:
        self.title.setText(f"{name}까지")
        self.summary.setText("걸어가는 길을 찾고 있어요…")
        self.summary.setStyleSheet(f"color: {p.text_dim};")
        self.summary.setFont(ui_font(17))
        self.scroll.setVisible(False)

    def show_error(self, msg: str, p: Palette) -> None:
        self.summary.setText(f"길을 찾지 못했어요.\n{msg}")
        self.summary.setStyleSheet(f"color: {p.warn};")
        self.summary.setFont(ui_font(16, QFont.Bold))
        self.scroll.setVisible(False)

    def show_route(self, data: dict, p: Palette) -> None:
        from ..data import distance_label

        minutes = max(1, round(float(data.get("time_s", 0)) / 60))
        self.summary.setText(f"걸어서 약 {minutes}분 · {distance_label(float(data.get('distance_m', 0)))}")
        self.summary.setStyleSheet(f"color: {p.accent};")
        self.summary.setFont(ui_font(24, QFont.ExtraBold))
        steps = [st.get("text", "") for st in data.get("steps", []) if st.get("text")]
        self.steps.setText("<br><br>".join(
            f"<b style='color:{p.accent}'>{i}.</b>&nbsp; {html.escape(t)}" for i, t in enumerate(steps, 1)))
        self.scroll.setVisible(bool(steps))
        # 단계가 적으면 다 보이게, 많으면 스크롤 (최대 260px)
        self.steps.adjustSize()
        self.scroll.setFixedHeight(min(260, self.steps.heightForWidth(self.width() - 60) + 8))


class MapView(QWidget):
    openPlace = Signal(str)
    locateRequested = Signal()
    originPicked = Signal(float, float)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self._analyses: dict[str, Analysis] = {}
        self._sort = "near"
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

        self.zoom_in = IconButton("plus", 46, 20, parent=self.map_area, tooltip="확대")
        self.zoom_out = IconButton("minus", 46, 20, parent=self.map_area, tooltip="축소")
        self.locate = IconButton("target", 46, 20, parent=self.map_area, tooltip="내 위치로")
        self.zoom_in.clicked.connect(lambda: self.canvas.zoom_by(1.28))
        self.zoom_out.clicked.connect(lambda: self.canvas.zoom_by(1 / 1.28))
        self.locate.clicked.connect(self._locate)

        self.panel = TopCard(self.map_area, closable=True)
        self.panel.setFixedWidth(400)
        self.panel.openRequested.connect(self.openPlace.emit)
        self.panel.closeRequested.connect(self._clear_selection)
        self.panel.hide()

        # 길 안내
        self.route_panel = RoutePanel(self.map_area)
        self.route_panel.closeRequested.connect(self.end_route)
        self.route_panel.otherAppRequested.connect(self._route_other_app)
        self.route_panel.hide()
        self._route_key = ""
        self._route_target: Analysis | None = None
        rp = providers.route_provider()
        rp.ready.connect(self._on_route_ready)
        rp.failed.connect(self._on_route_failed)

        # 우측 목록 -------------------------------------------------------
        side = QFrame()
        side.setFixedWidth(380)
        side.setStyleSheet("background: transparent;")
        slay = QVBoxLayout(side)
        slay.setContentsMargins(16, 20, 18, 18)
        slay.setSpacing(12)

        self.title = QLabel("주변 쉼터")
        self.title.setFont(ui_font(20, QFont.ExtraBold))
        self.count = QLabel("")
        self.count.setFont(ui_font(15, QFont.Bold))
        slay.addWidget(self.title)
        slay.addWidget(self.count)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.sort_buttons: dict[str, QPushButton] = {}
        for key, label in SORTS:
            b = QPushButton(label)
            b.setObjectName("chip")
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(40)
            b.setFont(ui_font(15, QFont.Bold))
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, k=key: self._set_sort(k))
            self.sort_buttons[key] = b
            chips.addWidget(b)
        slay.addLayout(chips)

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
        x = w - 64
        for i, b in enumerate((self.zoom_in, self.zoom_out, self.locate)):
            b.move(x, 18 + i * 54)
        self._place_panel()
        super().resizeEvent(ev)

    def _place_panel(self) -> None:
        self.panel.adjustSize()
        self.panel.move(18, self.map_area.height() - self.panel.height() - 18)
        self.route_panel.adjustSize()
        self.route_panel.move(18, self.map_area.height() - self.route_panel.height() - 18)

    # -- 길 안내 ------------------------------------------------------------
    def start_route(self, pid: str) -> None:
        """현재 위치에서 쉼터까지 걷는 길을 받아 지도에 그린다."""
        a = self._analyses.get(pid)
        if a is None:
            place = find_by_id(pid, self.state.mode, self.state.origin)
            if place is None:
                return
            h, m, wd = self.state.now()
            a = analyze(place, self.state.mode, h, m, wd, self.state.target_temp, origin=self.state.origin)
        self._route_target = a
        self._clear_selection()
        self.canvas.set_selected(pid)
        self.canvas.set_route([])
        self.canvas.fit_points([self.state.origin, a.place.latlon])
        self.route_panel.show_loading(a.place.name, self.state.palette)
        self.route_panel.other_btn.setIcon(icons.qicon("map", 18, self.state.palette.text))
        self.route_panel.show()
        self.route_panel.raise_()
        self._place_panel()
        self._route_key = providers.route_provider().request(self.state.origin, a.place.latlon, a.place.name)

    def end_route(self) -> None:
        self._route_key = ""
        self._route_target = None
        self.canvas.set_route([])
        self.canvas.set_selected(None)
        self.route_panel.hide()

    def _route_other_app(self) -> None:
        if self._route_target:
            open_directions(self._route_target, self.state.origin)

    def _on_route_ready(self, key: str, data: dict) -> None:
        if key != self._route_key or not self._route_target:
            return
        path = [(float(lat), float(lon)) for lon, lat in data.get("path", [])]
        self.canvas.set_route(path)
        self.canvas.fit_points(path + [self.state.origin, self._route_target.place.latlon])
        self.route_panel.show_route(data, self.state.palette)
        self._place_panel()

    def _on_route_failed(self, key: str, msg: str) -> None:
        if key != self._route_key:
            return
        self.route_panel.show_error(msg, self.state.palette)
        self._place_panel()

    def _locate(self) -> None:
        """현재 위치로 이동하고, 동시에 위치를 다시 확인한다."""
        self.canvas.center_on(self.state.origin, 16)
        self.locateRequested.emit()

    def _set_sort(self, key: str) -> None:
        self._sort = key
        self.refresh()

    def _on_pick(self, pid: str) -> None:
        if self._route_key:
            self.end_route()
        self._selected = pid
        self.canvas.set_selected(pid)
        a = self._analyses.get(pid)
        if a:
            self.panel.set_analysis(a, self.state)
            self.panel.show()
            self.panel.raise_()
            self._place_panel()
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

    def _row_clicked(self, pid: str) -> None:
        a = self._analyses.get(pid)
        if a:
            self.canvas.center_on(a.place.latlon)
        self._on_pick(pid)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        state = self.state
        p = state.palette
        hour, _minute, weekday = state.now()
        analyses = nearby(state)
        self._analyses = {a.place.id: a for a in analyses}
        self.canvas.set_data(analyses)
        self.legend.sync()

        ranked = nearest_first(analyses) if self._sort == "near" else rank(analyses)
        # 목록은 앞쪽 40곳만 (지도에는 모두 표시된다). 줄마다 위젯이라 많으면 화면 전환이 느려진다
        shown = ranked[:LIST_LIMIT]
        providers.report_provider().want([a.place.id for a in shown] + list(state.favorites))
        open_ = sum(1 for a in analyses if a.open_now)
        self.count.setText(f"{len(ranked)}곳 · 지금 열림 {open_}곳")
        self.count.setStyleSheet(f"color: {p.good if open_ else p.text_mute};")
        for key, b in self.sort_buttons.items():
            set_prop(b, "active", key == self._sort)
        for b in (self.zoom_in, self.zoom_out):
            b.set_color(p.text)
        self.locate.set_color(p.accent)

        while len(self.rows) < len(shown):
            row = PlaceRow()
            row.clicked.connect(self._row_clicked)
            row.opened.connect(self.openPlace.emit)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
            self.rows.append(row)
        for i, row in enumerate(self.rows):
            if i < len(shown):
                row.setVisible(True)
                row.set_analysis(shown[i], state)
                set_prop(row, "selected", shown[i].place.id == self._selected)
            else:
                row.setVisible(False)

        if self._route_key:
            pass      # 길 안내 중에는 선택 카드를 띄우지 않는다
        elif self._selected and self._selected in self._analyses:
            self.panel.set_analysis(self._analyses[self._selected], state)
            self._place_panel()
        else:
            self._clear_selection()

    def apply_palette(self, p: Palette) -> None:
        pass
