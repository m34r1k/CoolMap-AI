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
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import icons, providers
from ..config import AppState
from ..catalog import all_names, find_by_id
from ..theme import build_qss
from .chat import ChatView
from .common import IconLabel, apply_palette_tree, ui_font
from .detail import DetailView
from .placecard import set_route_handler
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
    """장소 검색 · 지금 상태(위치 확인 중 등) · 내 위치 다시 찾기.

    더위/추위 전환은 홈에, 공식 쉼터만 보기 같은 필터는 설정에 있다 (같은 버튼을 여러 곳에 두지 않는다).
    """

    def __init__(self, state: AppState, window: "MainWindow", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("topbar")
        self.setFixedHeight(76)
        self.state = state
        self.window_ref = window

        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 14, 24, 14)
        lay.setSpacing(14)

        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("쉼터 이름으로 찾기  (예: 도서관, 주민센터)")
        self.search.setMaximumWidth(560)
        self.search.setMinimumHeight(46)
        self.search.setFont(ui_font(16))
        self.search_icon = IconLabel("search", 18, "#63788E", 2.0, self.search)
        self.search_icon.move(14, 14)
        self.search.returnPressed.connect(self._search)

        self.completer_model = all_names()
        completer = QCompleter(self.completer_model)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.activated.connect(lambda _t: QTimer.singleShot(0, self._search))
        self.search.setCompleter(completer)
        lay.addWidget(self.search, 1)

        self.status = QLabel("")
        self.status.setFont(ui_font(15))
        lay.addWidget(self.status)

        self.locate_btn = QPushButton("  내 위치 다시 찾기")
        self.locate_btn.setCursor(Qt.PointingHandCursor)
        self.locate_btn.setMinimumHeight(46)
        self.locate_btn.setFont(ui_font(15, QFont.Bold))
        self.locate_btn.clicked.connect(lambda: window.locate_now())
        lay.addWidget(self.locate_btn)

        self._notice = QTimer(self)
        self._notice.setSingleShot(True)
        self._notice.timeout.connect(lambda: self.refresh())

    def set_locating(self, on: bool) -> None:
        self.locate_btn.setEnabled(not on)
        if on:
            self.status.setText("내 위치를 찾는 중…")

    def show_notice(self, text: str) -> None:
        self.status.setText(text)
        self._notice.start(6000)

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
        self.search.clear()
        if match:
            self.window_ref.open_place(match.id)
        else:
            self.search.setPlaceholderText(f"'{text}' 을(를) 찾지 못했어요")

    def refresh(self) -> None:
        p = self.state.palette
        if not self._notice.isActive():
            self.status.setText("")
        self.status.setStyleSheet(f"color: {p.text_dim};")
        self.locate_btn.setIcon(icons.qicon("target", 20, p.accent))
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
        self.chat = ChatView(state)
        self.settings = SettingsView(state)
        self.detail = DetailView(state)

        self.pages = {
            "home": self.home,
            "map": self.map_view,
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
        self.chat.openPlace.connect(self.open_place)
        self.detail.back.connect(self._back)
        self.detail.showOnMap.connect(self._show_on_map)
        self.settings.changed.connect(self.refresh_all)

        state.modeChanged.connect(self._on_mode_changed)
        state.themeChanged.connect(self._on_theme_changed)
        state.settingsChanged.connect(self.refresh_all)
        state.favoritesChanged.connect(self.refresh_all)

        # 외부 데이터 준비 (백그라운드)
        self.nuisance_ai = providers.nuisance_ai()
        self.weather = providers.weather_provider()
        # 모드마다 쉼터 제공자가 따로 있다. ready 신호는 제공자마다 딱 한 번만 연결한다
        # (전에는 데이터 준비 때마다 다시 연결해서, 신호 한 번에 갱신이 수십 번 돌았다)
        self._watched: set[int] = set()
        self.shelters = self._watch_shelters(state.mode)
        self.location = providers.location_provider()
        self.location.located.connect(self._on_located)
        self.location.failed.connect(self._on_locate_failed)
        state.originChanged.connect(self._on_origin_changed)
        self.nuisance_ai.scored.connect(self._on_ai_scored)
        self.weather.updated.connect(self._on_weather)
        # 지도 상호 판단이 끝날 때마다 추정 쉼터가 하나씩 늘어난다
        self.candidates = providers.candidate_provider()
        self.candidates.updated.connect(self._on_ai_scored)
        QTimer.singleShot(300, self._warm_providers)
        QTimer.singleShot(600, self.locate_now)

        self._ai_refresh = QTimer(self)
        self._ai_refresh.setSingleShot(True)
        self._ai_refresh.timeout.connect(self.refresh_current)
        # 짧은 시간에 몰려오는 갱신 요청(설정 · 위치 · 쉼터 도착)을 한 번으로 합친다
        self._refresh_soon = QTimer(self)
        self._refresh_soon.setSingleShot(True)
        self._refresh_soon.timeout.connect(self._do_refresh_all)

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start(30000)

        # '길찾기' 는 앱 안 길 안내(지도 화면)로 연다
        set_route_handler(self.start_route)

        self.apply_theme()
        self.navigate("home")

    # ------------------------------------------------------------------
    def apply_theme(self) -> None:
        p = self.state.palette
        self.setStyleSheet(build_qss(p))
        apply_palette_tree(self, p)

    def _on_theme_changed(self) -> None:
        self.apply_theme()
        self.refresh_all()

    def _on_mode_changed(self, _mode: str) -> None:
        self.apply_theme()
        self.refresh_all()
        QTimer.singleShot(50, self._warm_providers)

    def _watch_shelters(self, mode: str):
        sp = providers.shelter_provider(mode)
        if id(sp) not in self._watched:
            self._watched.add(id(sp))
            sp.ready.connect(self._on_shelters)
        return sp

    def _warm_providers(self) -> None:
        """날씨 · 쉼터 목록 · 민폐도를 미리 받아둔다 (UI 블로킹 없음)."""
        self.weather.observation(*self.state.origin)
        # 현재 모드의 쉼터 데이터셋을 동기화한다 (냉방=무더위 / 난방=한파).
        # 오래됐을 때만 받고, 실패하면 제공자가 몇 분 쉬었다가 다시 시도한다.
        self.shelters = self._watch_shelters(self.state.mode)
        self.shelters.sync()
        self._warm_nuisance()

    def _warm_nuisance(self) -> None:
        # 민폐도는 '시설 유형' 단위로 캐시되므로 근처 목록만 예열해도 대부분 채워진다
        from ..catalog import places_for

        self.nuisance_ai.warm(
            places_for(self.state.mode,
                       radius_m=float(self.state.get("search_radius"))),
            self.state.mode)

    def _on_ai_scored(self, _place_id: str = "") -> None:
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
            self.topbar.show_notice("자동으로 위치를 찾을게요…")
        self.topbar.set_locating(True)
        self.location.request()

    def _on_origin_picked(self, lat: float, lon: float) -> None:
        """지도 우클릭 — 현재 위치를 수동 지정한다."""
        self.state.set("location_mode", "manual", silent=True)
        self.state.set_origin(lat, lon, "지도에서 직접 지정", -1.0)
        self.topbar.show_notice("지도에서 고른 곳을 내 위치로 정했어요")

    def _on_located(self, lat: float, lon: float, accuracy: float, source: str) -> None:
        self.topbar.set_locating(False)
        self.state.set_origin(lat, lon, source, accuracy)

    def _on_locate_failed(self, msg: str) -> None:
        self.topbar.set_locating(False)
        self.topbar.show_notice(f"위치를 찾지 못했어요 — {msg}")

    def _on_origin_changed(self) -> None:
        self.map_view.canvas._user_moved = False
        self.refresh_all()
        QTimer.singleShot(150, self._warm_providers)

    def _on_shelters(self) -> None:
        """쉼터 실데이터가 도착하면 목록을 다시 만든다.

        여기서 쉼터 동기화(_warm_providers)를 다시 부르면 안 된다 — 받기가 덜 끝났을 때
        '도착 → 다시 받기 → 도착' 이 끝없이 돌아 앱이 멈춘다.
        """
        self.refresh_all()
        QTimer.singleShot(100, self._warm_nuisance)

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

    def start_route(self, pid: str) -> None:
        self.navigate("map")
        self.map_view.start_route(pid)

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
        """데이터나 설정이 바뀌었을 때. 바로 하지 않고 잠깐 모았다가 한 번만 한다."""
        self._refresh_soon.start(120)

    def _do_refresh_all(self) -> None:
        # 지금 보이는 화면만 다시 그린다. 다른 화면은 들어갈 때(navigate) 다시 그린다.
        self.refresh_current()
        self.sidebar.apply_palette(self.state.palette)
