"""외부 데이터 제공자 (지도 타일 · 날씨 · 건물 · AI).

캐시를 공유해야 하므로 앱 전체에서 하나의 인스턴스만 쓴다.
"""

from __future__ import annotations

_tiles = None
_weather = None
_buildings = None
_nuisance = None
_shelters = None
_location = None


def tile_provider():
    global _tiles
    if _tiles is None:
        from .tiles import TileProvider
        _tiles = TileProvider()
    return _tiles


def weather_provider():
    global _weather
    if _weather is None:
        from .weather import WeatherProvider
        _weather = WeatherProvider()
    return _weather


def building_provider():
    global _buildings
    if _buildings is None:
        from .buildings import BuildingProvider
        _buildings = BuildingProvider()
    return _buildings


def nuisance_ai():
    global _nuisance
    if _nuisance is None:
        from .gemini import NuisanceAI
        _nuisance = NuisanceAI()
    return _nuisance


def shelter_provider():
    global _shelters
    if _shelters is None:
        from .shelters import ShelterProvider
        _shelters = ShelterProvider()
    return _shelters


def location_provider():
    global _location
    if _location is None:
        from .location import LocationProvider
        _location = LocationProvider()
    return _location


def shutdown_all() -> None:
    for p in (_tiles, _weather, _buildings, _nuisance, _shelters, _location):
        if p is not None:
            try:
                p.shutdown()
            except Exception:
                pass
