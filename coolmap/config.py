"""앱 상태와 설정 저장."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .models import COOLING, HEATING
from .paths import settings_file
from .theme import Palette, palette_for

MARKER_AUTO = "auto"
MARKER_HIGHLIGHT = "highlight"
MARKER_ARROW = "arrow"

MARKER_LABELS = {
    MARKER_AUTO: "자동 (건물은 하이라이트 · 상가 내 업소는 화살표)",
    MARKER_HIGHLIGHT: "항상 건물 하이라이트",
    MARKER_ARROW: "항상 화살표 표시",
}

DEFAULTS: dict = {
    "mode": COOLING,
    "target_cool": 22.0,
    "target_heat": 23.0,
    "marker_style": MARKER_AUTO,
    "favorites": [],
    "time_mode": "real",          # real | manual
    "manual_hour": 15,
    "manual_weekday": 5,
    "show_event_zones": True,
    "show_closed": True,
    "map_labels": True,
    "animations": True,
    "only_official": False,
    "max_walk": 40,               # 분
    "search_radius": 2500,        # 쉼터 검색 반경 (m)
    "location_mode": "auto",      # auto(윈도우 위치 서비스) | manual
    "origin_lat": 37.5662,        # 마지막으로 확인된 현재 위치
    "origin_lon": 126.9784,
    "origin_source": "기본값 (서울시청)",
    "origin_accuracy": -1.0,
}


def _settings_path() -> Path:
    return settings_file()


class AppState(QObject):
    modeChanged = Signal(str)
    settingsChanged = Signal()
    favoritesChanged = Signal()
    clockChanged = Signal()
    originChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._data = dict(DEFAULTS)
        self._path = _settings_path()
        self.load()

    # -- 저장/로드 -------------------------------------------------------
    def load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for k, v in raw.items():
                if k in DEFAULTS:
                    self._data[k] = v
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    # -- 접근자 ----------------------------------------------------------
    def get(self, key: str):
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value, *, silent: bool = False) -> None:
        if self._data.get(key) == value:
            return
        self._data[key] = value
        self.save()
        if silent:
            return
        if key == "mode":
            self.modeChanged.emit(value)
        elif key in ("time_mode", "manual_hour", "manual_weekday"):
            self.clockChanged.emit()
            self.settingsChanged.emit()
        else:
            self.settingsChanged.emit()

    # -- 모드 ------------------------------------------------------------
    @property
    def mode(self) -> str:
        return self._data.get("mode", COOLING)

    @mode.setter
    def mode(self, value: str) -> None:
        self.set("mode", value)

    def toggle_mode(self) -> None:
        self.mode = HEATING if self.mode == COOLING else COOLING

    @property
    def palette(self) -> Palette:
        return palette_for(self.mode)

    @property
    def target_temp(self) -> float:
        return float(self.get("target_cool" if self.mode == COOLING else "target_heat"))

    @target_temp.setter
    def target_temp(self, value: float) -> None:
        self.set("target_cool" if self.mode == COOLING else "target_heat", float(value))

    # -- 현재 위치 --------------------------------------------------------
    @property
    def origin(self) -> tuple[float, float]:
        return float(self.get("origin_lat")), float(self.get("origin_lon"))

    @property
    def origin_source(self) -> str:
        return str(self.get("origin_source"))

    @property
    def origin_accuracy(self) -> float:
        return float(self.get("origin_accuracy"))

    def set_origin(self, lat: float, lon: float, source: str,
                   accuracy: float = -1.0) -> None:
        """현재 위치 갱신. 좌표가 실제로 바뀐 경우에만 신호를 낸다."""
        moved = (abs(lat - self.origin[0]) > 1e-6 or abs(lon - self.origin[1]) > 1e-6)
        self._data["origin_lat"] = float(lat)
        self._data["origin_lon"] = float(lon)
        self._data["origin_source"] = source
        self._data["origin_accuracy"] = float(accuracy)
        self.save()
        self.originChanged.emit()
        if moved:
            self.settingsChanged.emit()

    def origin_label(self) -> str:
        acc = self.origin_accuracy
        lat, lon = self.origin
        acc_txt = f" ±{int(acc)}m" if acc and acc > 0 else ""
        return f"{lat:.5f}, {lon:.5f} · {self.origin_source}{acc_txt}"

    # -- 시각 ------------------------------------------------------------
    def now(self) -> tuple[int, int, int]:
        """(hour, minute, weekday) — 설정에 따라 실제 시각 또는 시뮬레이션 시각."""
        if self.get("time_mode") == "manual":
            return int(self.get("manual_hour")), 0, int(self.get("manual_weekday"))
        n = datetime.now()
        return n.hour, n.minute, n.weekday()

    def clock_label(self) -> str:
        h, m, wd = self.now()
        days = "월화수목금토일"
        tag = "" if self.get("time_mode") == "real" else " · 시뮬레이션"
        return f"{days[wd]}요일 {h:02d}:{m:02d}{tag}"

    # -- 즐겨찾기 --------------------------------------------------------
    @property
    def favorites(self) -> list[str]:
        return list(self._data.get("favorites", []))

    def is_favorite(self, place_id: str) -> bool:
        return place_id in self._data.get("favorites", [])

    def toggle_favorite(self, place_id: str) -> bool:
        favs = list(self._data.get("favorites", []))
        if place_id in favs:
            favs.remove(place_id)
            added = False
        else:
            favs.append(place_id)
            added = True
        self._data["favorites"] = favs
        self.save()
        self.favoritesChanged.emit()
        return added

    # -- 마커 스타일 -----------------------------------------------------
    def marker_style_for(self, place) -> str:
        """자동 모드에서 어떤 마커를 쓸지.

        층·호수까지 아는 경우에만 화살표로 지점을 찍고, 그 밖에는 건물 전체를
        하이라이트한다. 은행처럼 큰 건물에 입점한 시설은 건물 전체가 냉방되는
        경우가 많아 건물 단위 표시가 더 유용하다.
        """
        style = self.get("marker_style")
        if style == MARKER_AUTO:
            precise = place.inside_mall and bool(place.floor_hint)
            return MARKER_ARROW if precise else MARKER_HIGHLIGHT
        return style
