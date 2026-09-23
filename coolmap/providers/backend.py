"""CoolMap 서버 (Supabase).

사용자가 API 키를 넣지 않아도 앱이 바로 동작하도록, 공공 API 는 서버가 대신
받아 두고 앱은 여기서 읽는다.

여기에는 **공개용 키(anon / publishable)만** 둔다. 이 키는 원래 앱에 넣어 배포하는
용도라 저장소에 올라가도 된다 — 서버 테이블은 RLS 로 읽기만 허용돼 있다.
service_role / secret 키는 절대 여기에 넣지 않는다.

환경변수 COOLMAP_SUPABASE_URL / COOLMAP_SUPABASE_KEY 나 secrets.json 의
supabase_url / supabase_key 로 덮어쓸 수 있다 (다른 프로젝트로 테스트할 때).
"""

from __future__ import annotations

import gzip
import json
import urllib.parse
import urllib.request

from .. import secrets

SUPABASE_URL = "https://kgquzsmtjrlneveddaqv.supabase.co"
SUPABASE_KEY = "sb_publishable_XZ6EgdFDKkjHA5xbeixGtA_sZVkbW1V"


def url() -> str:
    return (secrets.get("supabase_url") or SUPABASE_URL).rstrip("/")


def key() -> str:
    return secrets.get("supabase_key") or SUPABASE_KEY


def enabled() -> bool:
    return bool(url() and key())


def rest(table: str, params: dict, headers: dict | None = None,
         timeout: float = 30) -> tuple[list | dict, dict]:
    """PostgREST 조회. (본문, 응답 헤더) 를 돌려준다."""
    q = urllib.parse.urlencode(params, safe=",.()")
    req = urllib.request.Request(
        f"{url()}/rest/v1/{table}?{q}",
        headers={
            # apikey 하나만으로 anon 권한이 된다 (구형 anon JWT · 신형 publishable 둘 다)
            "apikey": key(),
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": "CoolMapAI/1.0",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8")), dict(r.headers)
