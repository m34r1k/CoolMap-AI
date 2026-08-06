"""앱이 사용할 쉼터 목록을 결정한다.

우선순위
1. 행정안전부 무더위쉼터 실데이터 (providers.shelter_provider)
2. 없으면 데모 데이터 (data.PLACES)

난방 모드는 한파쉼터 데이터가 별도라 아직 실데이터가 없다.
무더위쉼터로 지정된 '실내 시설'만 참고용으로 보여주고, 그 사실을 UI에 명시한다.
"""

from __future__ import annotations

from . import providers
from .data import PLACES, USER_HOME
from .models import COOLING, HEATING, Place

def source_label(mode: str) -> str:
    sp = providers.shelter_provider(mode)
    return sp.label if sp.loaded else "데모 데이터"


def is_live(mode: str) -> bool:
    return providers.shelter_provider(mode).loaded


#: 최근에 목록으로 내보낸 장소 (id -> Place).
#: 상세 화면·즐겨찾기는 좌표를 모른 채 id 로만 조회하므로, 여기서 바로 찾는다.
_INDEX: dict[str, Place] = {}
_INDEX_MAX = 4000


def _remember(places: list[Place]) -> list[Place]:
    for p in places:
        _INDEX[p.id] = p
    if len(_INDEX) > _INDEX_MAX:
        for key in list(_INDEX)[: len(_INDEX) - _INDEX_MAX]:
            _INDEX.pop(key, None)
    return places


def places_for(mode: str, origin: tuple[float, float] | None = None,
               radius_m: float = 2500, limit: int = 60) -> list[Place]:
    """현재 모드에서 보여줄 쉼터 목록."""
    sp = providers.shelter_provider(mode)
    origin = origin or USER_HOME

    if sp.loaded:
        found = sp.nearby(origin, mode, radius_m=radius_m, limit=limit)
        if mode == HEATING:
            # 야외 쉼터는 난방 모드에서 의미가 없다
            found = [p for p in found if p.category != "park"]
        if found:
            return _remember(found)

    # 폴백 — 데모 데이터
    return _remember([p for p in PLACES if p.supports(mode)])


def all_names() -> list[str]:
    """검색 자동완성용."""
    sp = providers.shelter_provider(COOLING)
    if sp.loaded:
        return [p.name for p in places_for(COOLING, radius_m=5000, limit=400)]
    return [p.name for p in PLACES]


def find_by_id(place_id: str, mode: str,
               origin: tuple[float, float] | None = None) -> Place | None:
    """id 로 장소를 찾는다.

    예전에는 origin 없이 places_for() 를 다시 호출해서, 사용자가 서울 밖에 있으면
    서울시청 주변만 뒤지다가 아무것도 못 찾았다 (상세 보기가 열리지 않던 원인).
    이제는 목록에 실렸던 장소를 그대로 기억해 두고 거기서 찾는다.
    """
    hit = _INDEX.get(place_id)
    if hit is not None:
        return hit

    # 캐시에 없으면(앱 재시작 직후 즐겨찾기 등) 위치 기준으로 넓게 조회
    sp = providers.shelter_provider(mode)
    if sp.loaded:
        for p in _remember(sp.nearby(origin or USER_HOME, mode,
                                     radius_m=8000, limit=2000)):
            if p.id == place_id:
                return p

    for p in PLACES:
        if p.id == place_id:
            return p
    return None
