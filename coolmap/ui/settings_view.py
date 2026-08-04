"""설정 화면."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .. import providers
from ..config import (
    MARKER_ARROW,
    MARKER_AUTO,
    MARKER_HIGHLIGHT,
    AppState,
)
from ..theme import Palette
from .common import Card, IconLabel, mono, ui_font

WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


class SettingsView(QWidget):
    changed = Signal()

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self._loading = False

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
        lay.setSpacing(18)
        lay.setAlignment(Qt.AlignTop)

        title = QLabel("설정")
        title.setObjectName("h1")
        lay.addWidget(title)

        # 1. 지도 표기 방식 ------------------------------------------------
        card, body = self._card("지도 표기 방식", "layers")
        desc = QLabel(
            "쉼터를 지도에 어떻게 표시할지 선택합니다. "
            "'자동'은 독립 건물은 하이라이트하고, 상가·복합몰 안의 업소는 화살표로 정확한 지점을 가리킵니다."
        )
        desc.setObjectName("dim")
        desc.setWordWrap(True)
        body.addWidget(desc)

        self.marker_combo = QComboBox()
        self.marker_combo.addItem("자동 — 건물 하이라이트 + 상가 내 업소 화살표", MARKER_AUTO)
        self.marker_combo.addItem("항상 건물 하이라이트", MARKER_HIGHLIGHT)
        self.marker_combo.addItem("항상 화살표로 지시", MARKER_ARROW)
        self.marker_combo.setMinimumWidth(400)
        self.marker_combo.currentIndexChanged.connect(
            lambda i: self._set("marker_style", self.marker_combo.itemData(i))
        )
        body.addWidget(self.marker_combo)

        self.cb_labels = self._check(body, "지도에 장소 이름 라벨 표시")
        self.cb_labels.toggled.connect(lambda v: self._set("map_labels", v))
        self.cb_events = self._check(body, "이벤트 영향권을 지도에 원으로 표시")
        self.cb_events.toggled.connect(lambda v: self._set("show_event_zones", v))
        self.cb_closed = self._check(body, "운영이 끝난 쉼터도 지도에 표시")
        self.cb_closed.toggled.connect(lambda v: self._set("show_closed", v))
        self.cb_anim = self._check(body, "애니메이션 효과 사용 (레이더 · 펄스)")
        self.cb_anim.toggled.connect(lambda v: self._set("animations", v))
        lay.addWidget(card)

        # 2. 모드 / 목표 온도 -----------------------------------------------
        card, body = self._card("모드 · 목표 온도", "thermo")
        self.cool_slider, cool_row = self._slider("냉방 목표 온도", 16, 28)
        self.cool_slider.valueChanged.connect(lambda v: self._set("target_cool", float(v)))
        body.addLayout(cool_row)
        self.heat_slider, heat_row = self._slider("난방 목표 온도", 16, 28)
        self.heat_slider.valueChanged.connect(lambda v: self._set("target_heat", float(v)))
        body.addLayout(heat_row)
        note = QLabel("목표 온도에 가까울수록 쾌적 점수가 높아집니다.")
        note.setObjectName("mute")
        note.setFont(mono(9, QFont.Normal, 0.5))
        body.addWidget(note)
        lay.addWidget(card)

        # 3. 추천 필터 --------------------------------------------------------
        card, body = self._card("추천 필터", "filter")
        self.cb_official = self._check(body, "공식 지정 무더위·한파 쉼터만 보기")
        self.cb_official.toggled.connect(lambda v: self._set("only_official", v))
        self.walk_slider, walk_row = self._slider("최대 도보 시간", 5, 60, unit="분")
        self.walk_slider.valueChanged.connect(lambda v: self._set("max_walk", int(v)))
        body.addLayout(walk_row)
        self.radius_slider, radius_row = self._slider("쉼터 검색 반경", 500, 5000, unit="m")
        self.radius_slider.setSingleStep(250)
        self.radius_slider.valueChanged.connect(
            lambda v: self._set("search_radius", int(round(v / 250) * 250)))
        body.addLayout(radius_row)
        rnote = QLabel("전국 6만여 곳 중 현재 위치 주변만 불러옵니다. 넓힐수록 목록이 길어집니다.")
        rnote.setObjectName("mute")
        rnote.setFont(mono(9, QFont.Normal, 0.5))
        rnote.setWordWrap(True)
        body.addWidget(rnote)
        lay.addWidget(card)

        # 3.5 현재 위치 ---------------------------------------------------------
        card, body = self._card("현재 위치", "target")
        locdesc = QLabel(
            "쉼터는 현재 위치를 기준으로 찾습니다. 자동 모드는 윈도우 위치 서비스"
            "(GPS·Wi-Fi)를 사용하고, 실패하면 IP 기반 추정으로 대체합니다.\n"
            "위치가 잡히지 않으면 Windows 설정 > 개인 정보 및 보안 > 위치 에서 "
            "'앱이 사용자 위치에 액세스하도록 허용'을 켜주세요."
        )
        locdesc.setObjectName("dim")
        locdesc.setWordWrap(True)
        body.addWidget(locdesc)

        self.loc_combo = QComboBox()
        self.loc_combo.addItem("자동 (윈도우 위치 서비스 → IP)", "auto")
        self.loc_combo.addItem("수동 지정 (지도에서 선택한 위치 유지)", "manual")
        self.loc_combo.currentIndexChanged.connect(
            lambda i: self._set("location_mode", self.loc_combo.itemData(i)))
        body.addWidget(self.loc_combo)

        self.loc_value = QLabel("-")
        self.loc_value.setFont(mono(10, QFont.DemiBold, 0.5))
        body.addWidget(self.loc_value)

        self.loc_backend = QLabel("-")
        self.loc_backend.setObjectName("mute")
        self.loc_backend.setFont(mono(9, QFont.Normal, 0.5))
        body.addWidget(self.loc_backend)

        locrow = QHBoxLayout()
        self.loc_btn = QPushButton("현재 위치 다시 확인")
        self.loc_btn.setCursor(Qt.PointingHandCursor)
        self.loc_btn.clicked.connect(self._locate)
        locrow.addWidget(self.loc_btn)
        locrow.addStretch(1)
        body.addLayout(locrow)
        lay.addWidget(card)

        # 4. 시각 -------------------------------------------------------------
        card, body = self._card("기준 시각", "clock")
        desc2 = QLabel(
            "혼잡도 예측은 시각과 요일에 따라 달라집니다. "
            "시뮬레이션 모드로 특정 시간대의 예측을 미리 확인할 수 있습니다."
        )
        desc2.setObjectName("dim")
        desc2.setWordWrap(True)
        body.addWidget(desc2)

        self.time_combo = QComboBox()
        self.time_combo.addItem("실시간 (현재 시각 사용)", "real")
        self.time_combo.addItem("시뮬레이션 (직접 지정)", "manual")
        self.time_combo.currentIndexChanged.connect(
            lambda i: self._set("time_mode", self.time_combo.itemData(i))
        )
        body.addWidget(self.time_combo)

        self.hour_slider, hour_row = self._slider("시각", 0, 23, unit="시")
        self.hour_slider.valueChanged.connect(lambda v: self._set("manual_hour", int(v)))
        body.addLayout(hour_row)

        day_row = QHBoxLayout()
        day_label = QLabel("요일")
        day_label.setFixedWidth(130)
        day_label.setObjectName("dim")
        self.day_combo = QComboBox()
        for i, d in enumerate(WEEKDAYS):
            self.day_combo.addItem(d, i)
        self.day_combo.currentIndexChanged.connect(
            lambda i: self._set("manual_weekday", i)
        )
        day_row.addWidget(day_label)
        day_row.addWidget(self.day_combo)
        day_row.addStretch(1)
        body.addLayout(day_row)
        lay.addWidget(card)

        # 5. 데이터 출처 --------------------------------------------------------
        card, body = self._card("데이터 연동 상태", "layers")
        self.source_label = QLabel("-")
        self.source_label.setObjectName("dim")
        self.source_label.setWordWrap(True)
        self.source_label.setTextFormat(Qt.RichText)
        body.addWidget(self.source_label)

        btns = QHBoxLayout()
        clear_tiles = QPushButton("지도 캐시 비우기")
        clear_tiles.setCursor(Qt.PointingHandCursor)
        clear_tiles.clicked.connect(self._clear_tiles)
        clear_ai = QPushButton("민폐도 캐시 비우기")
        clear_ai.setCursor(Qt.PointingHandCursor)
        clear_ai.clicked.connect(self._clear_ai)
        self.sync_btn = QPushButton("쉼터 데이터 새로 받기")
        self.sync_btn.setCursor(Qt.PointingHandCursor)
        self.sync_btn.clicked.connect(self._sync_shelters)
        btns.addWidget(self.sync_btn)
        btns.addWidget(clear_tiles)
        btns.addWidget(clear_ai)
        btns.addStretch(1)
        body.addLayout(btns)
        lay.addWidget(card)

        # 6. 정보 --------------------------------------------------------------
        card, body = self._card("CoolMap 정보", "info")
        info = QLabel(
            "CoolMap AI · 냉난방 쉼터 지도\n\n"
            "· 지도: OpenStreetMap 타일과 실제 건물 외곽선(Overpass)을 사용합니다.\n"
            "· 날씨: 기상청 초단기실황·단기예보의 실측값입니다.\n"
            "· 민폐도: Gemini가 시설 성격·구매 필요 여부·좌석·공식 쉼터 지정 여부를 근거로 "
            "0~100으로 추정합니다. 측정값이 아닌 추정치이며, 키가 없으면 규칙 기반으로 계산합니다.\n"
            "· 혼잡도: 실시간 인구 데이터 연동 전이라 비활성 상태입니다.\n"
            "· 쉼터: 행정안전부 재난안전데이터공유플랫폼의 전국 무더위쉼터(약 6만 곳)입니다.\n"
            "· 난방 모드는 한파쉼터 데이터가 별도라, 무더위쉼터로 지정된 "
            "실내시설을 참고용으로 보여줍니다."
        )
        info.setObjectName("dim")
        info.setWordWrap(True)
        body.addWidget(info)

        reset = QPushButton("설정 초기화")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(self._reset)
        row = QHBoxLayout()
        row.addWidget(reset)
        row.addStretch(1)
        body.addLayout(row)
        lay.addWidget(card)

    # ------------------------------------------------------------------
    def _card(self, title: str, icon: str) -> tuple[Card, QVBoxLayout]:
        card = Card(padding=22, spacing=13)
        body = card.body()
        head = QHBoxLayout()
        head.setSpacing(10)
        ic = IconLabel(icon, 18, "#22D3EE", 1.9)
        t = QLabel(title)
        t.setFont(ui_font(17, QFont.ExtraBold))
        head.addWidget(ic)
        head.addWidget(t)
        head.addStretch(1)
        body.addLayout(head)
        card.head_icon = ic  # type: ignore[attr-defined]
        return card, body

    def _check(self, body: QVBoxLayout, text: str) -> QCheckBox:
        cb = QCheckBox(text)
        cb.setCursor(Qt.PointingHandCursor)
        body.addWidget(cb)
        return cb

    def _slider(self, label: str, lo: int, hi: int, unit: str = "°C"):
        row = QHBoxLayout()
        row.setSpacing(14)
        lab = QLabel(label)
        lab.setObjectName("dim")
        lab.setFixedWidth(130)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(lo, hi)
        value = QLabel("-")
        value.setFont(mono(11, QFont.Bold, 0.5))
        value.setFixedWidth(56)
        value.setAlignment(Qt.AlignRight)
        slider.valueChanged.connect(lambda v: value.setText(f"{v}{unit}"))
        row.addWidget(lab)
        row.addWidget(slider, 1)
        row.addWidget(value)
        slider.value_label = value  # type: ignore[attr-defined]
        return slider, row

    def _locate(self) -> None:
        loc = providers.location_provider()
        self.loc_btn.setText("확인 중…")
        self.loc_btn.setEnabled(False)
        loc.located.connect(self._on_located)
        loc.failed.connect(self._on_locate_failed)
        loc.request()

    def _on_located(self, lat, lon, acc, source) -> None:
        self.loc_btn.setText("현재 위치 다시 확인")
        self.loc_btn.setEnabled(True)
        self.refresh()

    def _on_locate_failed(self, msg) -> None:
        self.loc_btn.setText("현재 위치 다시 확인")
        self.loc_btn.setEnabled(True)
        self.loc_value.setText(f"확인 실패 — {msg}")

    def _sync_shelters(self) -> None:
        sp = providers.shelter_provider()
        sp.progress.connect(self._on_sync_progress)
        sp.ready.connect(self.refresh)
        sp.sync(force=True)
        self.sync_btn.setText("받는 중…")
        self.sync_btn.setEnabled(False)

    def _on_sync_progress(self, got: int, total: int) -> None:
        self.sync_btn.setText(f"받는 중… {got:,}/{total:,}")
        if got >= total:
            self.sync_btn.setText("쉼터 데이터 새로 받기")
            self.sync_btn.setEnabled(True)

    def _clear_tiles(self) -> None:
        providers.tile_provider().clear_cache()
        providers.building_provider().clear_cache()
        self.refresh()

    def _clear_ai(self) -> None:
        providers.nuisance_ai().clear_cache()
        self.changed.emit()
        self.refresh()

    def _refresh_sources(self) -> None:
        from ..ai import CROWD_ENABLED

        tiles = providers.tile_provider()
        weather = providers.weather_provider()
        ai = providers.nuisance_ai()
        buildings = providers.building_provider()
        p = self.state.palette

        def dot(ok: bool, label: str) -> str:
            color = p.good if ok else p.text_mute
            return f"<span style='color:{color};'>●</span> {label}"

        sp = providers.shelter_provider()
        from ..catalog import source_label

        if sp.loaded:
            shelter_txt = (f"쉼터 목록 — 행안부 무더위쉼터 {sp.count:,}건"
                           f" (내려받은 지 {sp.age_days:.1f}일)")
        elif sp.syncing:
            shelter_txt = "쉼터 목록 — 내려받는 중…"
        else:
            shelter_txt = "쉼터 목록 — 데모 데이터 (키 없음 또는 미동기화)"

        rows = [
            dot(sp.loaded, shelter_txt),
            dot(sp.loaded, f"현재 모드 출처 — {source_label(self.state.mode)}"),
            dot(not tiles.offline, f"지도 타일 — OpenStreetMap "
                                   f"(캐시 {tiles.cache_size_mb():.1f}MB)"),
            dot(True, f"건물 외곽선 — OSM Overpass (캐시 {buildings.cache_count()}구역)"),
            dot(weather.live, "날씨 — 기상청 단기예보"
                              + ("" if weather.live else " (키 없음 · 모의 데이터 사용)")),
            dot(ai.enabled, f"민폐도 — Gemini {ai.model}"
                            + ("" if ai.enabled else " (키 없음 · 규칙 기반 사용)")),
            dot(CROWD_ENABLED, "혼잡도 — 실시간 인구 데이터 "
                               + ("연동됨" if CROWD_ENABLED else "연동 예정 (Coming Soon)")),
        ]
        self.source_label.setText("<br>".join(rows))

    def _set(self, key: str, value) -> None:
        if self._loading:
            return
        self.state.set(key, value)
        self.changed.emit()

    def _reset(self) -> None:
        from ..config import DEFAULTS

        self._loading = True
        for k, v in DEFAULTS.items():
            if k == "favorites":
                continue
            self.state.set(k, v, silent=True)
        self._loading = False
        self.state.modeChanged.emit(self.state.mode)
        self.state.settingsChanged.emit()
        self.refresh()
        self.changed.emit()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._loading = True
        s = self.state
        idx = self.marker_combo.findData(s.get("marker_style"))
        self.marker_combo.setCurrentIndex(max(0, idx))
        self.cb_labels.setChecked(bool(s.get("map_labels")))
        self.cb_events.setChecked(bool(s.get("show_event_zones")))
        self.cb_closed.setChecked(bool(s.get("show_closed")))
        self.cb_anim.setChecked(bool(s.get("animations")))
        self.cool_slider.setValue(int(s.get("target_cool")))
        self.cool_slider.value_label.setText(f"{int(s.get('target_cool'))}°C")
        self.heat_slider.setValue(int(s.get("target_heat")))
        self.heat_slider.value_label.setText(f"{int(s.get('target_heat'))}°C")
        self.cb_official.setChecked(bool(s.get("only_official")))
        self.walk_slider.setValue(int(s.get("max_walk")))
        self.walk_slider.value_label.setText(f"{int(s.get('max_walk'))}분")
        lidx = self.loc_combo.findData(s.get("location_mode"))
        self.loc_combo.setCurrentIndex(max(0, lidx))
        self.loc_value.setText(s.origin_label())
        from ..providers.location import LocationProvider
        self.loc_backend.setText(f"백엔드: {LocationProvider.backend_name()}")
        self.loc_btn.setEnabled(s.get("location_mode") == "auto")
        self.radius_slider.setValue(int(s.get("search_radius")))
        self.radius_slider.value_label.setText(f"{int(s.get('search_radius'))}m")
        tidx = self.time_combo.findData(s.get("time_mode"))
        self.time_combo.setCurrentIndex(max(0, tidx))
        self.hour_slider.setValue(int(s.get("manual_hour")))
        self.hour_slider.value_label.setText(f"{int(s.get('manual_hour'))}시")
        self.day_combo.setCurrentIndex(int(s.get("manual_weekday")))
        manual = s.get("time_mode") == "manual"
        self.hour_slider.setEnabled(manual)
        self.day_combo.setEnabled(manual)
        self._refresh_sources()
        self._loading = False

    def apply_palette(self, p: Palette) -> None:
        for card in self.findChildren(Card):
            ic = getattr(card, "head_icon", None)
            if ic is not None:
                ic.set_color(p.accent)
