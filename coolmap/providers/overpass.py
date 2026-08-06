"""Overpass API 공용 클라이언트.

건물 외곽선(buildings)과 지도 위 상호(candidates)를 서로 다른 제공자가
받아오지만, 상대는 자원봉사로 운영되는 하나의 공용 서버다.
요청 간격과 재시도를 여기 한 곳에서 관리해, 제공자가 늘어나도
서버가 받는 부담은 늘지 않게 한다.

공개 인스턴스는 자주 죽고, 망에 따라 특정 호스트만 막히기도 한다
(실제로 개발 중 overpass-api.de 와 kumi 양쪽이 동시에 닿지 않는 망을 만났다).
그래서 여러 미러를 두고, 한 번 성공한 곳을 기억해 다음부터 먼저 시도한다.
지역 한정 인스턴스는 한국 질의에 빈 결과를 주므로 넣지 않는다 — 조용히
아무것도 안 뜨는 게 실패보다 나쁘다.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

#: 전 세계 데이터를 가진 공개 인스턴스만. 앞쪽이 우선.
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
USER_AGENT = "CoolMapAI/1.0 (desktop shelter map)"

MIN_INTERVAL = 1.2      # 요청 간 최소 간격 (초)

#: (타임아웃, 라운드 시작 전 대기) 목록.
#: 1라운드는 짧게 — 닿지 않는 호스트를 빨리 포기하고 살아 있는 미러를 찾는다.
#: 이후는 넉넉히 + 쉬어 가며 — 미러가 과부하로 504 를 내는 경우가 잦은데,
#: 몇 초 뒤 같은 질의가 그냥 통과하는 일이 많다.
ROUNDS = ((10, 0.0), (45, 2.5), (45, 6.0))

_gate = threading.Lock()
_last = 0.0
_preferred = 0          # 마지막으로 성공한 엔드포인트


def _order() -> list[int]:
    pref = _preferred
    return [pref] + [i for i in range(len(ENDPOINTS)) if i != pref]


def request(query: str) -> dict:
    """Overpass 질의를 보내고 파싱된 응답을 준다.

    살아 있는 미러를 짧은 타임아웃으로 먼저 찾고, 그래도 다 실패하면
    넉넉한 타임아웃으로 한 번 더 돈다. 끝내 안 되면 예외를 올리고,
    쿨다운은 호출부가 관리한다.
    """
    global _last, _preferred
    # 대기까지 잠금 안에서 한다 — 여러 제공자가 동시에 몰려도 간격이 유지된다
    with _gate:
        wait = MIN_INTERVAL - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.time()

    data = urllib.parse.urlencode({"data": query}).encode()
    error = ""
    for timeout, pause in ROUNDS:
        if pause:
            time.sleep(pause)
        for i in _order():
            try:
                req = urllib.request.Request(
                    ENDPOINTS[i], data=data, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    parsed = json.loads(r.read().decode("utf-8", "replace"))
                _preferred = i          # 다음 요청은 여기부터
                return parsed
            except Exception as exc:
                error = f"{ENDPOINTS[i].split('/')[2]} {type(exc).__name__}: {exc}"
    raise RuntimeError(error or "overpass unreachable")


def current_endpoint() -> str:
    """지금 쓰고 있는 미러의 호스트명 (설정 화면 표시용)."""
    return ENDPOINTS[_preferred].split("/")[2]
