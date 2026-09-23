"""앱이 사용할 쉼터 목록을 결정한다.

우선순위
1. 행정안전부 실데이터 (냉방=무더위쉼터 / 난방=한파쉼터)
2. 없으면 데모 데이터 (data.PLACES)

여기에 더해, 지도에 상호만 떠 있고 공식 목록에는 없는 장소를
Gemini 가 판단해 'AI 추정 쉼터'로 덧붙일 수 있다 (include_ai).
공식 쉼터와 겹치는 것은 걸러 내고, 항상 공식 쉼터를 앞에 둔다.
"""

from __future__ import annotations

from . import providers
from .data import PLACES, USER_HOME
from .geo import haversine
from .models import COOLING, HEATING, Place

#: 중복 판정 거리 — 이름이 완전히 같을 때 / 한쪽이 다른 쪽 이름을 품을 때
DEDUPE_SAME_M = 800.0
DEDUPE_PART_M = 300.0
#: 품고 있는 쪽 대비 짧은 이름의 최소 길이 비율
DEDUPE_RATIO = 0.5


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


def _squash(name: str) -> str:
    """이름 비교용 정규화 — 공백·괄호·지점 표기를 없앤다."""
    out = []
    for ch in name:
        if ch.isspace() or ch in "()[]-·,.'\"":
            continue
        out.append(ch)
    return "".join(out)


def _same_place(a: Place, b: Place) -> bool:
    """두 장소가 같은 시설인지.

    거리만으로 판정하면 안 된다. 큰 건물 안에 다른 시설이 입점해 있는 일이
    흔해서, 실제로 홈플러스가 그 안의 농협 지점(16m)과 같은 곳으로 묶여
    지도에서 사라졌다. 마트를 띄우려고 만든 기능이 마트를 지운 셈이다.

    이름이 실제로 대응할 때만 같은 곳으로 본다.
    """
    an, bn = _squash(a.name), _squash(b.name)
    if not an or not bn:
        return False
    dist = haversine(a.latlon, b.latlon)
    if an == bn:
        return dist <= DEDUPE_SAME_M
    if an in bn or bn in an:
        # '판교역' 과 '판교역서편(07407)정류장' 은 이름이 겹쳐도 다른 시설이다.
        # 짧은 쪽이 긴 쪽의 상당 부분을 차지할 때만 같은 곳으로 본다.
        ratio = min(len(an), len(bn)) / max(len(an), len(bn))
        return ratio >= DEDUPE_RATIO and dist <= DEDUPE_PART_M
    return False


def _merge_ai(official: list[Place], mode: str, origin: tuple[float, float],
              radius_m: float, limit: int) -> list[Place]:
    """AI 추정 쉼터를 공식 목록 뒤에 덧붙인다.

    같은 곳이 두 번 뜨면 사용자는 둘 중 뭘 믿어야 할지 알 수 없다.
    겹치면 공식 쪽만 남긴다 — 공식 정보가 언제나 더 정확하다.
    """
    guesses = providers.candidate_provider().nearby(
        origin, mode, radius_m=radius_m, limit=limit)
    if not guesses:
        return official

    out = list(official)
    for g in guesses:
        if mode == HEATING and g.category == "park":
            continue        # 야외 쉼터는 난방 모드에서 의미가 없다
        if not any(_same_place(g, p) for p in official):
            out.append(g)
    return out


def places_for(mode: str, origin: tuple[float, float] | None = None,
               radius_m: float = 2500, limit: int = 60,
               include_ai: bool = False) -> list[Place]:
    """현재 모드에서 보여줄 쉼터 목록."""
    sp = providers.shelter_provider(mode)
    origin = origin or USER_HOME

    found: list[Place] = []
    if sp.loaded:
        found = sp.nearby(origin, mode, radius_m=radius_m, limit=limit)
        if mode == HEATING:
            # 야외 쉼터는 난방 모드에서 의미가 없다
            found = [p for p in found if p.category != "park"]

    if not sp.loaded:
        # 데이터가 아예 없을때만 데모 데이터를 쓴다.
        found = [p for p in PLACES if p.supports(mode)]

    if include_ai:
        found = _merge_ai(found, mode, origin, radius_m, max(20, limit // 2))
    return _remember(found)


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

    # AI 추정 쉼터 (앱 재시작 후 즐겨찾기로 들어온 경우)
    if place_id.startswith("G"):
        cp = providers.candidate_provider()
        for p in _remember(cp.nearby(origin or USER_HOME, mode,
                                     radius_m=5000, limit=200)):
            if p.id == place_id:
                return p

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
