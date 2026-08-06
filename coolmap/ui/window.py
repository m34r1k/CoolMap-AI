"""메인 윈도우."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCompleter,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import providers
from ..config import AppState
from ..catalog import all_names, find_by_id
from ..models import COOLING
from ..theme import build_qss
from .chat import ChatView
from .common import IconButton, IconLabel, Pill, apply_palette_tree, mono
from .detail import DetailView
from .favorites import FavoritesView
from .home import HomeView
from .mapview import MapView
from .settings_view import SettingsView
from .sidebar import BrandLogo, Sidebar


def app_icon(size: int = 64) -> QIcon:
    """브랜드 심볼을 앱 아이콘으로 렌더링."""
    logo = BrandLogo(size)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    logo.render(pm)
    return QIcon(pm)


class TopBar(QFrame):
    def __init__(self, state: AppState, window: "MainWindow", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("topbar")
        self.setFixedHeight(72)
        self.state = state
        self.window_ref = window

        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 14, 24, 14)
        lay.setSpacing(14)

        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("장소 검색…  (예: 도서관, 지하상가, 주민센터)")
        self.search.setMaximumWidth(560)
        self.search.setMinimumHeight(42)
        self.search_icon = IconLabel("search", 17, "#63788E", 2.0, self.search)
        self.search_icon.move(14, 13)
        self.search.returnPressed.connect(self._search)

        self.completer_model = all_names()
        completer = QCompleter(self.completer_model)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.activated.connect(lambda _t: QTimer.singleShot(0, self._search))
        self.search.setCompleter(completer)
        lay.addWidget(self.search, 1)

        self.mode_pill = Pill("냉방 모드", "snow", style="solid")
        lay.addWidget(self.mode_pill)

        self.clock = QLabel("")
        self.clock.setObjectName("mute")
        self.clock.setFont(mono(10, QFont.DemiBold, 0.6))
        lay.addWidget(self.clock)

        self.filter_btn = IconButton("filter", 40, 18, tooltip="공식 지정 쉼터만 보기")
        self.filter_btn.clicked.connect(self._toggle_official)
        lay.addWidget(self.filter_btn)

        self.locate_btn = IconButton("target", 40, 18, tooltip="현재 위치 다시 확인")
        self.locate_btn.clicked.connect(lambda: window.locate_now())
        lay.addWidget(self.locate_btn)

        self.mode_btn = IconButton("flame", 40, 18, tooltip="난방 모드로 전환")
        self.mode_btn.clicked.connect(state.toggle_mode)
        lay.addWidget(self.mode_btn)

        self._notice = QTimer(self)
        self._notice.setSingleShot(True)
        self._notice.timeout.connect(lambda: self.refresh())

    def set_locating(self, on: bool) -> None:
        p = self.state.palette
        self.locate_btn.setEnabled(not on)
        self.locate_btn.set_color(p.warn if on else p.text_dim)
        self.locate_btn.setToolTip("위치 확인 중…" if on else "현재 위치 다시 확인")
        if on:
            self.clock.setText("위치 확인 중…")

    def show_notice(self, text: str) -> None:
        self.clock.setText(text)
        self._notice.start(6000)

    def _toggle_official(self) -> None:
        self.state.set("only_official", not self.state.get("only_official"))

    def _search(self) -> None:
        text = self.search.text().strip()
        if not text:
            return
        from ..catalog import places_for

        low = text.lower()
        pool = places_for(self.state.mode,
                          radius_m=float(self.state.get("search_radius")) * 2, limit=400)
        match = next((p for p in pool if low in p.name.lower()), None)
        if match is None:
            match = next((p for p in pool
                          if low in p.category_label or low in p.address.lower()), None)
        if match:
            self.search.clear()
            self.window_ref.open_place(match.id)
        else:
            self.search.clear()
            self.search.setPlaceholderText(f"'{text}' 검색 결과가 없습니다")

    def refresh(self) -> None:
        p = self.state.palette
        self.mode_pill.set_text("냉방 모드" if self.state.mode == COOLING else "난방 모드")
        self.mode_pill.set_icon("snow" if self.state.mode == COOLING else "flame")
        self.mode_pill.set_colors(p.accent, p.accent_ink)
        self.mode_pill.adjustSize()
        acc = self.state.origin_accuracy
        acc_txt = f" ±{int(acc)}m" if acc and acc > 0 else ""
        self.clock.setText(f"{self.state.clock_label()}  ·  내 위치{acc_txt}")
        self.locate_btn.set_color(p.text_dim)
        on = bool(self.state.get("only_official"))
        self.filter_btn.set_color(p.accent if on else p.text_dim)
        self.filter_btn.setToolTip(
            "공식 지정 쉼터만 보기 (켜짐)" if on else "공식 지정 쉼터만 보기 (꺼짐)"
        )
        # 버튼은 '전환하면 될 모드'를 보여준다
        cooling = self.state.mode == COOLING
        self.mode_btn.set_icon_name("flame" if cooling else "snow")
        self.mode_btn.set_color(p.accent)
        self.mode_btn.setToolTip("난방 모드로 전환" if cooling else "냉방 모드로 전환")
        self.search_icon.set_color(p.text_mute)


class MainWindow(QMainWindow):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setWindowTitle("CoolMap AI — 냉난방 쉼터 지도")
        self.setWindowIcon(app_icon(96))
        self.resize(1440, 940)
        self.setMinimumSize(1160, 760)

        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar(state)
        self.sidebar.navigate.connect(self.navigate)
        root.addWidget(self.sidebar)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.topbar = TopBar(state, self)
        rl.addWidget(self.topbar)

        self.stack = QStackedWidget()
        rl.addWidget(self.stack, 1)
        root.addWidget(right, 1)

        # 페이지 ------------------------------------------------------------
        self.home = HomeView(state)
        self.map_view = MapView(state)
        self.favorites = FavoritesView(state)
        self.chat = ChatView(state)
        self.settings = SettingsView(state)
        self.detail = DetailView(state)

        self.pages = {
            "home": self.home,
            "map": self.map_view,
            "favorites": self.favorites,
            "ai": self.chat,
            "settings": self.settings,
        }
        for w in self.pages.values():
            self.stack.addWidget(w)
        self.stack.addWidget(self.detail)

        self._last_section = "home"

        # 시그널 ------------------------------------------------------------
        self.home.openMap.connect(lambda: self.navigate("map"))
        self.home.openPlace.connect(self.open_place)
        self.map_view.openPlace.connect(self.open_place)
        self.map_view.locateRequested.connect(self.locate_now)
        self.map_view.originPicked.connect(self._on_origin_picked)
        self.favorites.openPlace.connect(self.open_place)
        self.chat.openPlace.connect(self.open_place)
        self.detail.back.connect(self._back)
        self.detail.showOnMap.connect(self._show_on_map)
        self.settings.changed.connect(self.refresh_all)

        state.modeChanged.connect(self._on_mode_changed)
        state.settingsChanged.connect(self.refresh_all)
        state.favoritesChanged.connect(self.refresh_all)

        # 외부 데이터 준비 (백그라운드)
        self.nuisance_ai = providers.nuisance_ai()
        self.weather = providers.weather_provider()
        self.shelters = providers.shelter_provider(state.mode)
        self.shelters.ready.connect(self._on_shelters)
        self.location = providers.location_provider()
        self.location.located.connect(self._on_located)
        self.location.failed.connect(self._on_locate_failed)
        state.originChanged.connect(self._on_origin_changed)
        self.nuisance_ai.scored.connect(self._on_ai_scored)
        self.weather.updated.connect(self._on_weather)
        QTimer.singleShot(300, self._warm_providers)
        QTimer.singleShot(600, self.locate_now)

        self._ai_refresh = QTimer(self)
        self._ai_refresh.setSingleShot(True)
        self._ai_refresh.timeout.connect(self.refresh_current)

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start(30000)

        self.apply_theme()
        self.navigate("home")

    # ------------------------------------------------------------------
    def apply_theme(self) -> None:
        p = self.state.palette
        self.setStyleSheet(build_qss(p))
        apply_palette_tree(self, p)

    def _on_mode_changed(self, _mode: str) -> None:
        self.apply_theme()
        self.refresh_all()
        QTimer.singleShot(50, self._warm_providers)

    def _warm_providers(self) -> None:
        """민폐도·날씨를 미리 받아둔다 (UI 블로킹 없음)."""
        from ..catalog import places_for

        self.weather.observation(*self.state.origin)
        # 현재 모드의 쉼터 데이터셋을 동기화한다 (냉방=무더위 / 난방=한파)
        self.shelters = providers.shelter_provider(self.state.mode)
        try:
            self.shelters.ready.connect(self._on_shelters)
        except (RuntimeError, TypeError):
            pass
        self.shelters.sync()
        # 민폐도는 '시설 유형' 단위로 캐시되므로 근처 목록만 예열해도 대부분 채워진다
        self.nuisance_ai.warm(
            places_for(self.state.mode,
                       radius_m=float(self.state.get("search_radius"))),
            self.state.mode)

    def _on_ai_scored(self, _place_id: str) -> None:
        if self._ai_refresh.isActive():
            return
        self._ai_refresh.start(400)      # 여러 결과를 모아서 한 번만 갱신

    def _on_weather(self) -> None:
        self._ai_refresh.start(200)

    def locate_now(self) -> None:
        """현재 위치 다시 확인.

        수동 지정 상태였다면 자동 모드로 되돌린다. 그러지 않으면 버튼을 눌러도
        아무 일도 일어나지 않아 위치가 고정된 것처럼 보인다.
        """
        if self.state.get("location_mode") != "auto":
            self.state.set("location_mode", "auto", silent=True)
            self.topbar.show_notice("자동 위치 확인으로 전환합니다…")
        self.topbar.set_locating(True)
        self.location.request()

    def _on_origin_picked(self, lat: float, lon: float) -> None:
        """지도 우클릭 — 현재 위치를 수동 지정한다."""
        self.state.set("location_mode", "manual", silent=True)
        self.state.set_origin(lat, lon, "지도에서 직접 지정", -1.0)
        self.topbar.show_notice("현재 위치를 지도에서 지정했습니다 (수동 모드)")

    def _on_located(self, lat: float, lon: float, accuracy: float, source: str) -> None:
        self.topbar.set_locating(False)
        self.state.set_origin(lat, lon, source, accuracy)

    def _on_locate_failed(self, msg: str) -> None:
        self.topbar.set_locating(False)
        self.topbar.show_notice(f"위치 확인 실패 — {msg}")

    def _on_origin_changed(self) -> None:
        self.map_view.canvas._user_moved = False
        self.home.preview.canvas._user_moved = False
        self.refresh_all()
        QTimer.singleShot(150, self._warm_providers)

    def _on_shelters(self) -> None:
        """쉼터 실데이터가 도착하면 목록을 다시 만든다."""
        self.refresh_all()
        QTimer.singleShot(100, self._warm_providers)

    def _tick_clock(self) -> None:
        self.topbar.refresh()
        self.sidebar.refresh_clock()
        if self.state.get("time_mode") == "real":
            self.refresh_current()

    def navigate(self, key: str) -> None:
        if key not in self.pages:
            return
        self._last_section = key
        self.sidebar.set_current(key)
        self.stack.setCurrentWidget(self.pages[key])
        self.refresh_current()

    def open_place(self, pid: str) -> None:
        if find_by_id(pid, self.state.mode, self.state.origin) is None:
            return
        self.detail.set_place(pid)
        self.stack.setCurrentWidget(self.detail)
        apply_palette_tree(self.detail, self.state.palette)
        self.detail.refresh()

    def _back(self) -> None:
        self.navigate(self._last_section)

    def _show_on_map(self, pid: str) -> None:
        self.navigate("map")
        self.map_view.focus_place(pid)

    def refresh_current(self) -> None:
        w = self.stack.currentWidget()
        fn = getattr(w, "refresh", None)
        if callable(fn):
            fn()
        self.topbar.refresh()
        self.sidebar.refresh_clock()

    def closeEvent(self, ev) -> None:
        providers.shutdown_all()
        super().closeEvent(ev)

    def refresh_all(self) -> None:
        for w in list(self.pages.values()) + [self.detail]:
            fn = getattr(w, "refresh", None)
            if callable(fn):
                fn()
        self.settings.refresh()
        self.topbar.refresh()
        self.sidebar.apply_palette(self.state.palette)
