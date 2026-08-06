"""외부 데이터 제공자 (지도 타일 · 날씨 · 건물 · AI).

캐시를 공유해야 하므로 앱 전체에서 하나의 인스턴스만 쓴다.
"""

from __future__ import annotations

_tiles = None
_weather = None
_buildings = None
_nuisance = None
_shelters: dict = {}
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


def shelter_provider(mode: str = "cooling"):
    """모드별 쉼터 제공자 (냉방=무더위쉼터 / 난방=한파쉼터)."""
    from .shelters import DATASETS, ShelterProvider

    ds = DATASETS.get(mode) or DATASETS["cooling"]
    if ds.mode not in _shelters:
        _shelters[ds.mode] = ShelterProvider(ds)
    return _shelters[ds.mode]


def all_shelter_providers():
    from .shelters import DATASETS

    return [shelter_provider(m) for m in DATASETS]


def location_provider():
    global _location
    if _location is None:
        from .location import LocationProvider
        _location = LocationProvider()
    return _location


def shutdown_all() -> None:
    for p in (_tiles, _weather, _buildings, _nuisance, _location,
              *_shelters.values()):
        if p is not None:
            try:
                p.shutdown()
            except Exception:
                pass
