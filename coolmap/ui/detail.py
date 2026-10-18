"""장소 상세 — 이름 → 길찾기 → 꼭 필요한 정보(걸리는 시간 · 운영 · 온도 · 머물기) 순서.

점수(쾌적 · 민폐도)와 계산 근거는 '자세히 보기' 를 눌러야 펼쳐진다.
mobile/src/app/place/[id].tsx 와 같은 구성이다.
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
from ..ai import Analysis, analyze
from ..catalog import find_by_id
from ..config import AppState
from ..plain import open_line, stay_line, tags, temp_compare, temp_line, walk_line
from ..theme import Palette
from .common import Card, GaugeArc, IconLabel, MeterBar, nuisance_color, ui_font
from .placecard import InfoLine, ReportNotice, SirenButton, start_route, tag_label

CONTENT_WIDTH = 860


def _label(size: int, weight=QFont.Normal, wrap: bool = True) -> QLabel:
    lab = QLabel("")
    lab.setFont(ui_font(size, weight))
    lab.setWordWrap(wrap)
    return lab


class DetailView(QWidget):
    back = Signal()
    showOnMap = Signal(str)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self._pid: str | None = None
        self._analysis: Analysis | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.scroll)

        page = QWidget()
        self.scroll.setWidget(page)
        center = QHBoxLayout(page)
        center.setContentsMargins(32, 18, 32, 40)
        content = QWidget()
        content.setMaximumWidth(CONTENT_WIDTH)
        center.addStretch(1)
        center.addWidget(content, 100)
        center.addStretch(1)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.setAlignment(Qt.AlignTop)

        self.back_btn = QPushButton("  뒤로")
        self.back_btn.setObjectName("ghost")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setFont(ui_font(16, QFont.Bold))
        self.back_btn.clicked.connect(self.back.emit)
        # 위: 왼쪽 '뒤로', 오른쪽 구석 '문제 알리기'
        row = QHBoxLayout()
        row.addWidget(self.back_btn)
        row.addStretch(1)
        self.siren = SirenButton()
        row.addWidget(self.siren)
        lay.addLayout(row)

        cat = QHBoxLayout()
        cat.setSpacing(8)
        self.cat_icon = IconLabel("building", 22, "#22D3EE", 2.0)
        self.cat_label = _label(16, QFont.Bold, wrap=False)
        cat.addWidget(self.cat_icon)
        cat.addWidget(self.cat_label)
        cat.addStretch(1)
        lay.addLayout(cat)

        self.title = _label(28, QFont.ExtraBold)
        lay.addWidget(self.title)
        self.address = _label(15)
        lay.addWidget(self.address)
        self.tags = QHBoxLayout()
        self.tags.setSpacing(6)
        lay.addLayout(self.tags)

        self.route_btn = QPushButton("  길찾기")
        self.route_btn.setObjectName("primary")
        self.route_btn.setCursor(Qt.PointingHandCursor)
        self.route_btn.setMinimumHeight(56)
        self.route_btn.clicked.connect(self._route)
        lay.addWidget(self.route_btn)

        info = Card(padding=18, spacing=12)
        self.report = ReportNotice()
        info.body().addWidget(self.report)
        self.walk = InfoLine("walk")
        self.open = InfoLine("clock")
        self.hours = _label(14)
        self.hours.setContentsMargins(30, 0, 0, 0)
        self.temp = InfoLine("thermo")
        self.stay = InfoLine("star")
        for w in (self.walk, self.open, self.hours, self.temp, self.stay):
            info.body().addWidget(w)
        lay.addWidget(info)

        self.tips_card = Card(padding=18, spacing=8)
        t = _label(18, QFont.ExtraBold)
        t.setText("머물 때 알아 두세요")
        self.tips_card.body().addWidget(t)
        self.tips = _label(16)
        self.tips_card.body().addWidget(self.tips)
        lay.addWidget(self.tips_card)

        self.amen_card = Card(padding=18, spacing=8)
        t = _label(18, QFont.ExtraBold)
        t.setText("시설 정보")
        self.amen_card.body().addWidget(t)
        self.amenities = _label(15)
        self.amen_card.body().addWidget(self.amenities)
        lay.addWidget(self.amen_card)

        acts = QHBoxLayout()
        acts.setSpacing(10)
        self.fav_btn = QPushButton("자주 가는 곳에 저장")
        self.map_btn = QPushButton("  지도에서 보기")
        for b in (self.fav_btn, self.map_btn):
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(50)
            b.setFont(ui_font(16, QFont.Bold))
        self.fav_btn.clicked.connect(self._toggle_fav)
        self.map_btn.clicked.connect(lambda: self._pid and self.showOnMap.emit(self._pid))
        acts.addWidget(self.fav_btn, 1)
        acts.addWidget(self.map_btn)
        lay.addLayout(acts)

        # 점수와 근거 — 궁금한 사람만 펼쳐 본다
        self.more_btn = QPushButton("자세히 보기 (점수 · 근거)")
        self.more_btn.setCursor(Qt.PointingHandCursor)
        self.more_btn.setMinimumHeight(50)
        self.more_btn.setFont(ui_font(16, QFont.Bold))
        self.more_btn.clicked.connect(self._toggle_more)
        lay.addWidget(self.more_btn)

        self.more = Card(padding=18, spacing=12)
        mb = self.more.body()
        self.comfort_cap = _label(15, QFont.Bold)
        self.comfort_cap.setText("쾌적 점수 (목표 온도·습도·바람을 종합)")
        self.comfort = _label(30, QFont.ExtraBold)
        self.comfort_bar = MeterBar(height=8)
        mb.addWidget(self.comfort_cap)
        mb.addWidget(self.comfort)
        mb.addWidget(self.comfort_bar)
        self.nuis_cap = _label(15, QFont.Bold)
        self.nuis_cap.setText("민폐도 (오래 머물 때 눈치 보이는 정도)")
        mb.addWidget(self.nuis_cap)
        g = QHBoxLayout()
        g.addStretch(1)
        self.gauge = GaugeArc(size=170)
        g.addWidget(self.gauge)
        g.addStretch(1)
        mb.addLayout(g)
        self.nuis_text = _label(15)
        mb.addWidget(self.nuis_text)
        self.extra = _label(15)
        mb.addWidget(self.extra)
        self.source = _label(13)
        mb.addWidget(self.source)
        self.more.setVisible(False)
        lay.addWidget(self.more)

    # ------------------------------------------------------------------
    def _route(self) -> None:
        if self._analysis:
            start_route(self._analysis, self.state.origin)

    def _toggle_fav(self) -> None:
        if self._pid:
            self.state.toggle_favorite(self._pid)
            self._sync_fav()

    def _sync_fav(self) -> None:
        on = bool(self._pid) and self.state.is_favorite(self._pid)
        p = self.state.palette
        self.fav_btn.setText("  자주 가는 곳 ✓" if on else "  자주 가는 곳에 저장")
        self.fav_btn.setIcon(icons.qicon("heart_fill" if on else "heart", 20, p.accent if on else p.text))

    def _toggle_more(self) -> None:
        show = not self.more.isVisible()
        self.more.setVisible(show)
        self.more_btn.setText("자세히 보기 닫기" if show else "자세히 보기 (점수 · 근거)")

    def set_place(self, pid: str) -> None:
        self._pid = pid
        self.more.setVisible(False)
        self.more_btn.setText("자세히 보기 (점수 · 근거)")
        self.scroll.verticalScrollBar().setValue(0)
        self.refresh()

    def refresh(self) -> None:
        place = (find_by_id(self._pid, self.state.mode, self.state.origin)
                 if self._pid else None)
        if place is None:
            return
        state = self.state
        p = state.palette
        hour, minute, weekday = state.now()
        a = analyze(place, state.mode, hour, minute, weekday, state.target_temp,
                    origin=state.origin)
        self._analysis = a
        open_ = a.open_now

        self.back_btn.setIcon(icons.qicon("arrow_left", 20, p.text))
        self.cat_icon.set_icon(place.icon)
        self.cat_icon.set_color(p.accent)
        self.cat_label.setText(place.category_label)
        self.cat_label.setStyleSheet(f"color: {p.accent};")
        self.title.setText(place.name)
        unit = f" · {place.unit}" if place.unit else ""
        self.address.setText(f"{place.address}{unit}")
        self.address.setVisible(bool(place.address or place.unit))
        self.address.setStyleSheet(f"color: {p.text_dim};")

        while self.tags.count():
            item = self.tags.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for text, tone in tags(a):
            self.tags.addWidget(tag_label(text, tone, p))
        self.tags.addStretch(1)

        self.route_btn.setIcon(icons.qicon("walk", 22, p.accent_ink))
        self.siren.set_place(place.id, place.name, state)
        providers.report_provider().want([place.id])
        self.report.set(place.id, state)
        self.walk.set(walk_line(a), p.text, p.text_dim)
        self.open.set(open_line(a, hour, minute, weekday), p.good if open_ else p.text_mute)
        self.hours.setText(f"운영 시간 {place.hours_label()}")
        self.hours.setStyleSheet(f"color: {p.text_dim};")
        self.temp.set(f"{temp_line(a)} · {temp_compare(a)}", p.text, p.text_dim)
        self.stay.set(stay_line(a), p.text, p.text_dim)

        self.tips_card.setVisible(bool(a.nuisance.tips))
        self.tips.setText("\n".join(f"· {t}" for t in a.nuisance.tips))
        self.tips.setStyleSheet(f"color: {p.text_dim};")
        self.amen_card.setVisible(bool(place.amenities))
        self.amenities.setText("  ·  ".join(place.amenities))
        self.amenities.setStyleSheet(f"color: {p.text_dim};")

        self._sync_fav()
        self.map_btn.setIcon(icons.qicon("map", 20, p.text))

        # 자세히 보기
        nc = nuisance_color(p, a.nuisance.key)
        self.comfort.setText(f"{a.comfort} / 100")
        self.comfort.setStyleSheet(f"color: {p.accent};")
        self.comfort_bar.set_value(a.comfort / 100.0)
        self.comfort_bar.set_colors(p.accent, p.card_alt)
        self.gauge.set_data(a.nuisance.score, a.nuisance.level, "0=편함 · 100=눈치")
        self.gauge.set_colors(nc, p.card_alt, p.text, p.text_mute)
        lines = [f"권장 체류 {a.nuisance.stay_label}"]
        if a.nuisance.reason:
            lines.append(a.nuisance.reason)
        if a.nuisance.source != "gemini":
            lines += [f"· {name} {'+' if v > 0 else ''}{v}" for name, v in a.nuisance.factors]
        self.nuis_text.setText("\n".join(lines))
        self.extra.setText(
            f"체감 {a.feels_inside:.1f}°C · 습도 {place.humidity}% · 바람 {place.airflow}"
            + (f"\n{place.why}" if place.why else ""))
        self.source.setText(
            "실내 온도와 점수는 추정치예요. "
            + ("민폐도는 Gemini가 추정했어요." if a.nuisance.source == "gemini"
               else "민폐도는 규칙으로 계산했어요."))
        for lab in (self.comfort_cap, self.nuis_cap, self.nuis_text, self.extra):
            lab.setStyleSheet(f"color: {p.text_dim};")
        self.source.setStyleSheet(f"color: {p.text_mute};")

    def apply_palette(self, p: Palette) -> None:
        pass
