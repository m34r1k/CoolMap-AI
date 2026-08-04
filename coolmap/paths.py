"""앱 데이터 경로.

QStandardPaths 는 QApplication 의 이름 설정 시점에 따라 결과가 달라지므로,
설정·캐시·키 파일 위치는 여기서 고정한다.

Windows : %APPDATA%\\CoolMap\\
그 외    : ~/.coolmap/
"""

from __future__ import annotations

import os
from pathlib import Path


def app_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "CoolMap" if appdata else Path.home() / ".coolmap"
    base.mkdir(parents=True, exist_ok=True)
    return base


def cache_dir(name: str) -> Path:
    d = app_dir() / "cache" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings_file() -> Path:
    """설정 파일 경로.

    COOLMAP_SETTINGS_FILE 로 덮어쓸 수 있다. 테스트가 실제 사용자 설정을
    건드리지 않도록 하기 위한 장치다 (캐시·키는 그대로 공유한다).
    """
    override = os.environ.get("COOLMAP_SETTINGS_FILE")
    if override:
        path = Path(override)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return app_dir() / "settings.json"


def secrets_file() -> Path:
    return app_dir() / "secrets.json"
