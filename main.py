"""CoolMap AI 실행 진입점.

실행:  python main.py
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from coolmap import providers
from coolmap.config import AppState
from coolmap.theme import UI_FONT
from coolmap.ui.window import MainWindow


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("CoolMap AI")
    app.setOrganizationName("CoolMap")
    base_font = QFont(UI_FONT)
    base_font.setPixelSize(14)
    app.setFont(base_font)

    state = AppState()
    window = MainWindow(state)
    window.show()
    code = app.exec()

    # 타일·쉼터·Gemini 조회는 백그라운드 스레드에서 돌고, 진행 중인 HTTP 요청은
    # 취소할 수 없다. 파이썬은 종료 시 이 스레드들을 join 하므로 창을 닫아도
    # 프로세스가 최대 1분 가까이 남는다. 캐시는 모두 원자적으로 기록되므로
    # 정리 후 즉시 종료한다.
    providers.shutdown_all()
    # PyInstaller --windowed 로 빌드하면 sys.stdout/stderr 가 None 이다
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            try:
                stream.flush()
            except Exception:
                pass
    os._exit(code)


if __name__ == "__main__":
    sys.exit(main())
