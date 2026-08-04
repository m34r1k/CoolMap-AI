"""좌표계 변환.

- WGS84 (위경도) ↔ 웹 메르카토르 (EPSG:3857) — 지도 렌더링용
- 위경도 → 슬리피 맵 타일 좌표 (z/x/y) — OSM 타일용
- 위경도 ↔ 기상청 격자 (nx, ny) — Lambert Conformal Conic
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS = 6378137.0
MAX_LAT = 85.05112878


@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float

    def as_tuple(self) -> tuple[float, float]:
        return self.lat, self.lon


# ---------------------------------------------------------------------------
# 웹 메르카토르
# ---------------------------------------------------------------------------
def lonlat_to_meters(lon: float, lat: float) -> tuple[float, float]:
    """위경도 → EPSG:3857 (미터)."""
    lat = max(-MAX_LAT, min(MAX_LAT, lat))
    x = math.radians(lon) * EARTH_RADIUS
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * EARTH_RADIUS
    return x, y


def meters_to_lonlat(x: float, y: float) -> tuple[float, float]:
    """EPSG:3857 (미터) → 위경도."""
    lon = math.degrees(x / EARTH_RADIUS)
    lat = math.degrees(2 * math.atan(math.exp(y / EARTH_RADIUS)) - math.pi / 2)
    return lon, lat


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    """두 위경도(lat, lon) 사이 거리 (미터)."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS * math.asin(math.sqrt(h))


# ---------------------------------------------------------------------------
# 슬리피 맵 타일 (OSM/XYZ)
# ---------------------------------------------------------------------------
TILE_SIZE = 256


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[float, float]:
    """위경도 → 타일 좌표 (소수부 포함)."""
    lat = max(-MAX_LAT, min(MAX_LAT, lat))
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def tile_to_lonlat(x: float, y: float, z: int) -> tuple[float, float]:
    """타일 좌표 → 위경도 (타일 좌상단)."""
    n = 2.0 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


def resolution(lat: float, z: int) -> float:
    """해당 줌/위도에서 픽셀당 미터."""
    return (2 * math.pi * EARTH_RADIUS * math.cos(math.radians(lat))) / (TILE_SIZE * 2 ** z)


# ---------------------------------------------------------------------------
# 기상청 격자 (Lambert Conformal Conic)
# 기상청 「동네예보 격자 정보」 표준 변환식
# ---------------------------------------------------------------------------
_RE = 6371.00877     # 지구 반경 (km)
_GRID = 5.0          # 격자 간격 (km)
_SLAT1 = 30.0        # 표준 위도 1
_SLAT2 = 60.0        # 표준 위도 2
_OLON = 126.0        # 기준점 경도
_OLAT = 38.0         # 기준점 위도
_XO = 43             # 기준점 X 좌표
_YO = 136            # 기준점 Y 좌표


def _lcc_constants():
    degrad = math.pi / 180.0
    re = _RE / _GRID
    slat1 = _SLAT1 * degrad
    slat2 = _SLAT2 * degrad
    olon = _OLON * degrad
    olat = _OLAT * degrad

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)
    return degrad, re, sn, sf, ro, olon


def latlon_to_kma_grid(lat: float, lon: float) -> tuple[int, int]:
    """위경도 → 기상청 격자 (nx, ny)."""
    degrad, re, sn, sf, ro, olon = _lcc_constants()
    ra = math.tan(math.pi * 0.25 + lat * degrad * 0.5)
    ra = re * sf / (ra ** sn)
    theta = lon * degrad - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    nx = int(math.floor(ra * math.sin(theta) + _XO + 0.5))
    ny = int(math.floor(ro - ra * math.cos(theta) + _YO + 0.5))
    return nx, ny


def kma_grid_to_latlon(nx: int, ny: int) -> tuple[float, float]:
    """기상청 격자 → 위경도 (격자 중심)."""
    degrad, re, sn, sf, ro, olon = _lcc_constants()
    xn = nx - _XO
    yn = ro - ny + _YO
    ra = math.sqrt(xn * xn + yn * yn)
    if sn < 0.0:
        ra = -ra
    alat = (re * sf / ra) ** (1.0 / sn)
    alat = 2.0 * math.atan(alat) - math.pi * 0.5

    if abs(xn) <= 0.0:
        theta = 0.0
    elif abs(yn) <= 0.0:
        theta = math.pi * 0.5
        if xn < 0.0:
            theta = -theta
    else:
        theta = math.atan2(xn, yn)
    alon = theta / sn + olon
    return alat / degrad, alon / degrad
