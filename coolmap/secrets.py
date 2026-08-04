"""API 키 로딩.

키는 **소스에 넣지 않는다.** 아래 순서로 찾는다.

1. 환경변수  COOLMAP_GEMINI_KEY / COOLMAP_KMA_KEY / COOLMAP_SHELTER_KEY
2. %APPDATA%\\CoolMap\\secrets.json
3. 프로젝트 루트의 secrets.json (개발용, .gitignore 대상)

secrets.json 형식:
{
  "gemini_api_key": "...",       // Google AI Studio
  "kma_service_key": "...",      // 공공데이터포털 (data.go.kr) 일반 인증키
  "shelter_service_key": "..."   // 재난안전데이터공유플랫폼 (safetydata.go.kr)
}

Encoding 값(%2B 등이 포함된 형태)을 넣어도 자동으로 디코딩한다.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from functools import lru_cache
from pathlib import Path

from .paths import secrets_file

_ENV = {
    "gemini_api_key": "COOLMAP_GEMINI_KEY",
    "kma_service_key": "COOLMAP_KMA_KEY",
    "shelter_service_key": "COOLMAP_SHELTER_KEY",
}


def secrets_path() -> Path:
    return secrets_file()


@lru_cache(maxsize=1)
def _load() -> dict:
    data: dict = {}
    for path in (secrets_path(), Path(__file__).resolve().parent.parent / "secrets.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            break
        except (OSError, ValueError):
            continue
    return data if isinstance(data, dict) else {}


def get(name: str, default: str = "") -> str:
    env = _ENV.get(name)
    if env and os.environ.get(env):
        return os.environ[env].strip()
    value = _load().get(name, default)
    return value.strip() if isinstance(value, str) else default


def gemini_key() -> str:
    return get("gemini_api_key")


def kma_key() -> str:
    """공공데이터포털 인증키.

    Encoding 값(%2B, %2F, %3D 포함)을 넣어도 되도록 디코딩해서 반환한다.
    requests/urlencode 가 다시 인코딩하므로 반드시 디코딩본을 써야 한다.
    """
    raw = get("kma_service_key")
    return urllib.parse.unquote(raw) if "%" in raw else raw


def write(values: dict) -> Path:
    """secrets.json 을 만들거나 갱신한다."""
    path = secrets_path()
    current = {}
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    current.update(values)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    _load.cache_clear()
    return path


def status() -> dict[str, bool]:
    return {"gemini": bool(gemini_key()), "kma": bool(kma_key())}
