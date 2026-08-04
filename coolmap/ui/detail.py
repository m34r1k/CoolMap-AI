"""장소 상세 화면."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..ai import CROWD_ENABLED, Analysis, analyze
from ..config import AppState
from ..catalog import find_by_id
from ..models import COOLING
from ..theme import Palette
from .common import (
    Card,
    GaugeArc,
    HeroBanner,
    HourlyChart,
    IconButton,
    IconLabel,
    MeterBar,
    Pill,
    StatTile,
    TagRow,
    crowd_color,
    mono,
    nuisance_color,
    ui_font,
)


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
        root.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.scroll, 1)

        content = QWidget()
        self.scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 히어로 -----------------------------------------------------------
        self.hero = HeroBanner(height=250)
        lay.addWidget(self.hero)

        self.back_btn = IconButton("arrow_left", 38, 17, parent=self.hero, tooltip="뒤로")
        self.back_btn.clicked.connect(self.back.emit)
        self.fav_btn = IconButton("heart", 38, 17, parent=self.hero, tooltip="즐겨찾기")
        self.fav_btn.clicked.connect(self._toggle_fav)
        self.map_btn = IconButton("map", 38, 17, parent=self.hero, tooltip="지도에서 보기")
        self.map_btn.clicked.connect(lambda: self._pid and self.showOnMap.emit(self._pid))

        body = QWidget()
        lay.addWidget(body)
        b = QVBoxLayout(body)
        b.setContentsMargins(34, 24, 34, 30)
        b.setSpacing(18)

        # 타이틀 -----------------------------------------------------------
        pills = QHBoxLayout()
        pills.setSpacing(8)
        self.cat_pill = Pill("-", "building")
        self.dist_pill = Pill("-", "walk", style="outline")
        self.official_pill = Pill("공식 지정 쉼터", "check_circle", style="soft")
        pills.addWidget(self.cat_pill)
        pills.addWidget(self.dist_pill)
        pills.addWidget(self.official_pill)
        pills.addStretch(1)
        b.addLayout(pills)

        self.title = QLabel("-")
        self.title.setObjectName("h1")
        self.title.setWordWrap(True)
        b.addWidget(self.title)

        self.summary = QLabel("-")
        self.summary.setObjectName("body")
        self.summary.setWordWrap(True)
        b.addWidget(self.summary)

        self.location = QLabel("-")
        self.location.setObjectName("mute")
        self.location.setFont(mono(10, QFont.DemiBold, 0.6))
        self.location.setWordWrap(True)
        b.addWidget(self.location)

        # 온도 3종 ----------------------------------------------------------
        temp_card = Card(padding=12, spacing=10)
        temps = QHBoxLayout()
        temps.setSpacing(10)
        self.t_out = StatTile("OUTDOOR", "-", "°C")
        self.t_in = StatTile("INDOOR", "-", "°C", highlight=True)
        self.t_feel = StatTile("FEELS LIKE", "-", "°C")
        for t in (self.t_out, self.t_in, self.t_feel):
            temps.addWidget(t, 1)
        temp_card.body().addLayout(temps)
        b.addWidget(temp_card)

        # 지표 3종 ----------------------------------------------------------
        metrics = QHBoxLayout()
        metrics.setSpacing(14)

        self.comfort_card = Card(padding=18, spacing=8)
        cc = self.comfort_card.body()
        crow = QHBoxLayout()
        crow.setSpacing(8)
        self.comfort_icon = IconLabel("sparkle", 16, "#22D3EE", 1.9)
        clab = QLabel("AI 쾌적 점수")
        clab.setObjectName("label")
        crow.addWidget(self.comfort_icon)
        crow.addWidget(clab)
        crow.addStretch(1)
        cc.addLayout(crow)
        num_row = QHBoxLayout()
        num_row.setSpacing(3)
        self.comfort_value = QLabel("-")
        self.comfort_value.setFont(ui_font(38, QFont.ExtraBold))
        self.comfort_max = QLabel("/100")
        self.comfort_max.setObjectName("mute")
        num_row.addWidget(self.comfort_value, 0, Qt.AlignBottom)
        num_row.addWidget(self.comfort_max, 0, Qt.AlignBottom)
        num_row.addStretch(1)
        cc.addLayout(num_row)
        self.comfort_bar = MeterBar(height=7)
        cc.addWidget(self.comfort_bar)
        metrics.addWidget(self.comfort_card, 2)

        self.humid_card = self._mini_metric("HUMIDITY", "droplet")
        self.air_card = self._mini_metric("AIRFLOW", "wind")
        metrics.addWidget(self.humid_card, 1)
        metrics.addWidget(self.air_card, 1)
        b.addLayout(metrics)

        # 혼잡도 예측 -------------------------------------------------------
        self.crowd_card = Card(padding=20, spacing=14)
        cl = self.crowd_card.body()
        head = QHBoxLayout()
        head.setSpacing(9)
        self.crowd_icon = IconLabel("users", 18, "#22D3EE", 1.9)
        ct = QLabel("AI 혼잡도 예측")
        ct.setFont(ui_font(16, QFont.ExtraBold))
        self.conf_pill = Pill("신뢰도 -", "check", style="outline")
        self.soon_pill = Pill("COMING SOON", "clock", style="soft")
        self.soon_pill.setVisible(not CROWD_ENABLED)
        head.addWidget(self.crowd_icon)
        head.addWidget(ct)
        head.addStretch(1)
        head.addWidget(self.soon_pill)
        head.addWidget(self.conf_pill)
        cl.addLayout(head)

        info = QHBoxLayout()
        info.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(4)
        self.crowd_level = QLabel("-")
        self.crowd_level.setFont(ui_font(26, QFont.ExtraBold))
        self.crowd_people = QLabel("-")
        self.crowd_people.setObjectName("mute")
        self.crowd_people.setFont(mono(10, QFont.DemiBold, 0.6))
        left.addWidget(self.crowd_level)
        left.addWidget(self.crowd_people)
        info.addLayout(left)
        info.addStretch(1)
        self.crowd_ratio_bar = MeterBar(height=9)
        self.crowd_ratio_bar.setFixedWidth(200)
        info.addWidget(self.crowd_ratio_bar, 0, Qt.AlignVCenter)
        cl.addLayout(info)

        self.event_banner = QFrame()
        self.event_banner.setObjectName("cardFlat")
        eb = QHBoxLayout(self.event_banner)
        eb.setContentsMargins(14, 12, 14, 12)
        eb.setSpacing(11)
        self.event_icon = IconLabel("alert", 17, "#FBBF24", 2.0)
        ebox = QVBoxLayout()
        ebox.setSpacing(3)
        self.event_title = QLabel("-")
        self.event_title.setFont(ui_font(13, QFont.Bold))
        self.event_note = QLabel("-")
        self.event_note.setObjectName("mute")
        self.event_note.setFont(mono(9, QFont.Normal, 0.5))
        self.event_note.setWordWrap(True)
        ebox.addWidget(self.event_title)
        ebox.addWidget(self.event_note)
        eb.addWidget(self.event_icon, 0, Qt.AlignTop)
        eb.addLayout(ebox, 1)
        cl.addWidget(self.event_banner)

        chart_label = QLabel("시간대별 예측")
        chart_label.setObjectName("label")
        cl.addWidget(chart_label)
        self.chart = HourlyChart()
        cl.addWidget(self.chart)
        b.addWidget(self.crowd_card)

        # 민폐도 -------------------------------------------------------------
        self.nuis_card = Card(padding=20, spacing=14)
        nl = self.nuis_card.body()
        nhead = QHBoxLayout()
        nhead.setSpacing(9)
        self.nuis_icon = IconLabel("star", 18, "#22D3EE", 1.9)
        nt = QLabel("민폐도 지수")
        nt.setFont(ui_font(16, QFont.ExtraBold))
        self.stay_pill = Pill("권장 체류 -", "clock", style="soft")
        nhead.addWidget(self.nuis_icon)
        nhead.addWidget(nt)
        nhead.addStretch(1)
        nhead.addWidget(self.stay_pill)
        nl.addLayout(nhead)

        nbody = QHBoxLayout()
        nbody.setSpacing(20)
        self.gauge = GaugeArc(size=168)
        nbody.addWidget(self.gauge, 0, Qt.AlignTop)

        nright = QVBoxLayout()
        nright.setSpacing(9)
        self.nuis_desc = QLabel("-")
        self.nuis_desc.setObjectName("body")
        self.nuis_desc.setWordWrap(True)
        nright.addWidget(self.nuis_desc)
        self.factors_holder = QWidget()
        self.factors_layout = QVBoxLayout(self.factors_holder)
        self.factors_layout.setContentsMargins(0, 0, 0, 0)
        self.factors_layout.setSpacing(6)
        nright.addWidget(self.factors_holder)
        nright.addStretch(1)
        nbody.addLayout(nright, 1)
        nl.addLayout(nbody)

        self.tips_label = QLabel("-")
        self.tips_label.setObjectName("dim")
        self.tips_label.setWordWrap(True)
        self.tips_label.setFont(ui_font(12))
        nl.addWidget(self.tips_label)
        b.addWidget(self.nuis_card)

        # 편의시설 ------------------------------------------------------------
        self.amen_card = Card(padding=20, spacing=12)
        al = self.amen_card.body()
        at = QLabel("편의시설 · 운영")
        at.setFont(ui_font(16, QFont.ExtraBold))
        al.addWidget(at)
        self.hours_label = QLabel("-")
        self.hours_label.setObjectName("dim")
        self.hours_label.setFont(mono(10, QFont.DemiBold, 0.6))
        al.addWidget(self.hours_label)
        self.tags = TagRow()
        al.addWidget(self.tags)
        b.addWidget(self.amen_card)

        # 추천 이유 -----------------------------------------------------------
        self.why_card = Card(padding=20, spacing=11)
        wl = self.why_card.body()
        whead = QHBoxLayout()
        whead.setSpacing(9)
        self.why_icon = IconLabel("bulb", 18, "#22D3EE", 1.9)
        wt = QLabel("CoolMap이 이곳을 추천하는 이유")
        wt.setFont(ui_font(16, QFont.ExtraBold))
        whead.addWidget(self.why_icon)
        whead.addWidget(wt)
        whead.addStretch(1)
        wl.addLayout(whead)
        self.why_text = QLabel("-")
        self.why_text.setObjectName("body")
        self.why_text.setWordWrap(True)
        wl.addWidget(self.why_text)
        b.addWidget(self.why_card)

        b.addStretch(1)

        # 하단 액션 바 ---------------------------------------------------------
        bar = QFrame()
        bar.setObjectName("topbar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(34, 14, 34, 14)
        bl.setSpacing(12)
        self.route_btn = QPushButton("길찾기")
        self.route_btn.setObjectName("primary")
        self.route_btn.setCursor(Qt.PointingHandCursor)
        self.route_btn.clicked.connect(self._route)
        self.map_btn2 = QPushButton("지도에서 보기")
        self.map_btn2.setCursor(Qt.PointingHandCursor)
        self.map_btn2.clicked.connect(lambda: self._pid and self.showOnMap.emit(self._pid))
        bl.addWidget(self.route_btn, 1)
        bl.addWidget(self.map_btn2)
        root.addWidget(bar)

        self.route_note = QLabel("")
        self.route_note.setObjectName("mute")

    def _building_name(self, place) -> str:
        """이 쉼터가 속한 건물 이름 (OSM). 지도에서 하이라이트되는 대상."""
        from .. import providers

        try:
            b = providers.building_provider().building_at(place.lat, place.lon)
        except Exception:
            return ""
        if not b:
            return ""
        name = b.get("name") or ""
        levels = b.get("levels") or ""
        if name and levels:
            return f"{name} ({levels}층 건물 전체 하이라이트)"
        if name:
            return f"{name} 내"
        return "건물 전체 하이라이트"

    def _mini_metric(self, caption: str, icon: str) -> Card:
        card = Card(padding=18, spacing=8)
        lay = card.body()
        row = QHBoxLayout()
        row.setSpacing(8)
        ic = IconLabel(icon, 15, "#9FB3C8", 1.9)
        lab = QLabel(caption)
        lab.setObjectName("label")
        row.addWidget(ic)
        row.addWidget(lab)
        row.addStretch(1)
        lay.addLayout(row)
        val = QLabel("-")
        val.setFont(ui_font(24, QFont.ExtraBold))
        lay.addWidget(val)
        lay.addStretch(1)
        card.icon_widget = ic       # type: ignore[attr-defined]
        card.value_widget = val     # type: ignore[attr-defined]
        return card

    def resizeEvent(self, ev) -> None:
        self.back_btn.move(20, 18)
        self.fav_btn.move(self.hero.width() - 104, 18)
        self.map_btn.move(self.hero.width() - 58, 18)
        super().resizeEvent(ev)

    def _toggle_fav(self) -> None:
        if self._pid:
            self.state.toggle_favorite(self._pid)
            self._sync_fav()

    def _sync_fav(self) -> None:
        if not self._pid:
            return
        on = self.state.is_favorite(self._pid)
        p = self.state.palette
        self.fav_btn.set_icon_name("heart_fill" if on else "heart")
        self.fav_btn.set_color(p.accent if on else p.text)

    def _route(self) -> None:
        if not self._analysis:
            return
        a = self._analysis
        self.route_btn.setText(
            f"도보 {a.walk_min}분 · {a.distance_label} — 경로 안내 시작"
        )

    # ------------------------------------------------------------------
    def set_place(self, pid: str) -> None:
        self._pid = pid
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

        self.hero.set_data(place.icon, p.accent_deep, p.bg, p.accent)
        self.cat_pill.set_text(place.category_label)
        self.cat_pill.set_icon(place.icon)
        self.cat_pill.set_colors(p.accent, p.card)
        self.dist_pill.set_text(f"{a.distance_label} · 도보 {a.walk_min}분")
        self.dist_pill.set_colors(p.text_dim, p.card)
        self.official_pill.setVisible(place.official)
        self.official_pill.set_colors(p.good, p.card)

        self.title.setText(place.name)
        self.summary.setText(place.summary)
        marker = "지도에서 화살표로 위치를 지시합니다" if place.inside_mall \
            else "지도에서 건물 전체가 하이라이트됩니다"
        unit = f" · {place.unit}" if place.unit else ""
        self.location.setText(f"{place.address}{unit}  ·  {marker}")

        # 온도
        self.t_out.set_value(f"{a.weather.outdoor:.0f}")
        self.t_out.set_value_color(p.bad if state.mode == COOLING else p.accent_bright)
        self.t_in.set_value(f"{a.indoor:.1f}")
        self.t_in.set_value_color(p.accent)
        self.t_feel.set_value(f"{a.feels_inside:.1f}")
        self.t_feel.set_value_color(p.text)

        # 지표
        self.comfort_value.setText(str(a.comfort))
        self.comfort_value.setStyleSheet(f"color: {p.accent};")
        self.comfort_bar.set_colors(p.accent, p.card_alt)
        self.comfort_bar.set_value(a.comfort / 100)
        self.comfort_icon.set_color(p.accent)
        self.humid_card.value_widget.setText(f"{place.humidity}%")
        self.air_card.value_widget.setText(place.airflow)
        self.humid_card.icon_widget.set_color(p.text_dim)
        self.air_card.icon_widget.set_color(p.text_dim)

        # 혼잡도 ------------------------------------------------------
        self.crowd_icon.set_color(p.accent if CROWD_ENABLED else p.text_mute)
        self.soon_pill.set_colors(p.warn, p.card)
        self.conf_pill.setVisible(CROWD_ENABLED)

        if CROWD_ENABLED:
            cc = crowd_color(p, a.crowd.key)
            self.crowd_level.setText(a.crowd.level)
            self.crowd_level.setStyleSheet(f"color: {cc.name()};")
            if a.crowd.open_now:
                self.crowd_people.setText(
                    f"현재 약 {a.crowd.people}명 · 수용 {place.capacity}명 대비 {a.crowd.percent}%"
                )
            else:
                self.crowd_people.setText(f"운영 시간 {place.hours_label()}")
            self.crowd_ratio_bar.set_colors(cc.name(), p.card_alt)
            self.crowd_ratio_bar.set_value(a.crowd.ratio)
            self.conf_pill.set_text(f"신뢰도 {a.crowd.confidence}%")
            self.conf_pill.set_colors(p.text_dim, p.card)
            event_hours = (set(range(a.crowd.event.start_hour, a.crowd.event.end_hour))
                           if a.crowd.event else set())
            self.chart.set_colors(p.accent, p.card_alt, p.text_mute, p.warn)
            self.chart.set_data(a.crowd.hourly, hour, event_hours)
        else:
            # 실시간 인구 데이터 연동 전 — 수치를 감추고 비활성 상태로 표시
            self.crowd_level.setText("준비 중")
            self.crowd_level.setStyleSheet(f"color: {p.text_mute};")
            self.crowd_people.setText("실시간 인구 데이터 연동 후 제공됩니다")
            self.crowd_ratio_bar.set_colors(p.card_alt, p.card_alt)
            self.crowd_ratio_bar.set_value(0.0)
            self.chart.set_colors(p.text_mute, p.card_alt, p.text_mute, p.text_mute)
            self.chart.set_data([0.0] * 24, -1, set())
            self.chart.setEnabled(False)

        # 인근 행사 안내 (행사 정보 자체는 예측이 아니라 사실)
        if a.crowd.by_event:
            self.event_banner.setVisible(True)
            self.event_icon.set_color(p.warn)
            self.event_title.setText(
                a.crowd.headline if CROWD_ENABLED
                else "인근에서 행사가 진행 중이에요 (평소보다 붐빌 수 있음)")
            self.event_title.setStyleSheet(f"color: {p.warn};")
            self.event_note.setText(a.crowd.detail)
        elif CROWD_ENABLED:
            self.event_banner.setVisible(True)
            self.event_icon.set_color(p.text_dim)
            self.event_title.setText(a.crowd.headline)
            self.event_title.setStyleSheet(f"color: {p.text};")
            self.event_note.setText(a.crowd.detail)
        else:
            self.event_banner.setVisible(False)

        # 민폐도
        nc = nuisance_color(p, a.nuisance.key)
        self.nuis_icon.set_color(p.accent)
        self.gauge.set_colors(nc, p.card_alt, p.text, p.text_mute)
        self.gauge.set_data(a.nuisance.score, a.nuisance.level, "0=편함 · 100=눈치")
        self.stay_pill.set_text(f"권장 체류 {a.nuisance.stay_label}")
        self.stay_pill.set_colors(p.accent, p.card)
        detail_txt = (
            f"이 장소에 오래 머물 때 느껴지는 부담은 <b>{a.nuisance.level}</b> 수준입니다. "
            f"권장 체류 시간은 <b>{a.nuisance.stay_label}</b>입니다."
        )
        if a.nuisance.reason:
            detail_txt += f"<br>{a.nuisance.reason}"
        self.nuis_desc.setText(detail_txt)
        self.nuis_desc.setTextFormat(Qt.RichText)

        while self.factors_layout.count():
            item = self.factors_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for name, value in (a.nuisance.factors if a.nuisance.source != "gemini" else []):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(10)
            lab = QLabel(name)
            lab.setObjectName("mute")
            lab.setFont(mono(9, QFont.Normal, 0.5))
            lab.setFixedWidth(130)
            bar = MeterBar(height=6)
            bar.set_colors(p.good if value < 0 else nc.name(), p.card_alt)
            bar.set_value(min(1.0, abs(value) / 40))
            val = QLabel(f"{value:+d}")
            val.setFont(mono(9, QFont.Bold, 0.5))
            val.setStyleSheet(f"color: {p.good if value < 0 else nc.name()};")
            val.setFixedWidth(34)
            val.setAlignment(Qt.AlignRight)
            h.addWidget(lab)
            h.addWidget(bar, 1)
            h.addWidget(val)
            self.factors_layout.addWidget(row)

        self.tips_label.setText("\n".join(f"· {t}" for t in a.nuisance.tips))

        # 편의시설
        # 좌석 수(이용가능인원)는 원본 신뢰도가 낮아 표시하지 않는다.
        # 대신 어느 건물이 하이라이트되는지 알려준다.
        hours_txt = f"운영 시간 {place.hours_label()}"
        building = self._building_name(place)
        if building:
            hours_txt += f"  ·  {building}"
        self.hours_label.setText(hours_txt)
        self.tags.set_colors(p.text_dim, p.card_alt, p.border)
        self.tags.set_tags(place.amenities)

        # 이유
        self.why_icon.set_color(p.accent)
        base = place.why
        extra = (
            f" 현재 외기 {a.weather.outdoor:.0f}°C 대비 실내는 {a.indoor:.1f}°C로 "
            f"약 {a.delta:.1f}°C 차이가 납니다."
        )
        self.why_text.setText(base + extra)

        self.route_btn.setText("길찾기")
        self._sync_fav()

    def apply_palette(self, p: Palette) -> None:
        self.back_btn.set_color(p.text)
        self.map_btn.set_color(p.text)
        self._sync_fav()
