"""CoolMap AI 배포 빌드 스크립트.

    python build_release.py

dist/CoolMapAI/ 폴더와 dist/CoolMapAI-<버전>-win64.zip 을 만든다.

PySide6 전체는 600MB가 넘지만 이 앱은 QtCore/QtGui/QtWidgets/QtPositioning 만
쓰므로, WebEngine·Quick·Multimedia 등을 제외해 크기를 크게 줄인다.
API 키는 번들에 절대 포함되지 않는다 (앱 실행 후 설정 화면에서 입력).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = "CoolMapAI"

sys.path.insert(0, str(ROOT))
from coolmap import __version__  # noqa: E402

# 이 앱이 쓰지 않는 Qt 모듈 — 번들에서 제외해 용량을 줄인다.
#
# 주의해서 남겨야 하는 것들:
#   · shiboken6         — PySide6 의 핵심 바인딩. 제외하면 앱이 아예 안 뜬다.
#   · PySide6.QtQml     — QtPositioning 이 내부적으로 의존한다.
#   · PySide6.QtNetwork — 위치/네트워크 스택이 참조한다.
EXCLUDE_QT = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSerialPort",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtScxml",
    "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtUiTools",
]
EXCLUDE_OTHER = ["tkinter", "unittest", "pydoc", "doctest", "PIL", "numpy"]


def build() -> Path:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onedir",
        "--windowed",                 # 콘솔 창 없이 실행
        "--name", APP,
        "--hidden-import", "PySide6.QtPositioning",   # 위치 확인에 필요
    ]
    for m in EXCLUDE_QT + EXCLUDE_OTHER:
        args += ["--exclude-module", m]
    args.append(str(ROOT / "main.py"))

    print(">>", " ".join(args[:8]), "...")
    subprocess.run(args, check=True, cwd=ROOT)
    return ROOT / "dist" / APP


def prune(folder: Path) -> None:
    """번들에서 안전하게 뺄 수 있는 것만 정리한다.

    주의: DLL 을 임의로 지우면 앱이 아예 안 뜬다. 특히
      · opengl32sw.dll   — GPU 가 없는 가상 머신에서 Qt 렌더링에 반드시 필요
      · Qt6Qml.dll       — QtPositioning 이 의존
    이런 파일은 남겨야 한다. 모듈 제외는 PyInstaller 의 --exclude-module 에 맡기고,
    여기서는 실행에 영향이 없는 번역 파일만 정리한다.
    """
    removed = 0
    tr = folder / "_internal" / "PySide6" / "translations"
    if tr.exists():
        removed += sum(f.stat().st_size for f in tr.rglob("*") if f.is_file())
        shutil.rmtree(tr, ignore_errors=True)
    print(f"   정리: {removed / 1024 / 1024:.1f} MB (번역 파일만)")


def make_readme(folder: Path) -> None:
    (folder / "처음 실행 안내.txt").write_text(
        "CoolMap AI — 냉난방 쉼터 지도\n"
        f"버전 {__version__}\n"
        "\n"
        "실행 방법\n"
        f"  {APP}.exe 를 더블클릭하세요. 설치 과정은 없습니다.\n"
        "\n"
        "API 키 입력 (선택)\n"
        "  키가 없어도 실행되지만, 쉼터 목록은 데모 데이터로, 날씨는 모의값으로\n"
        "  동작합니다. 실데이터를 쓰려면 앱을 켠 뒤\n"
        "      설정 > API 키\n"
        "  에서 아래 키를 입력하고 '키 저장하고 적용'을 누르세요.\n"
        "\n"
        "    · 무더위쉼터 : https://www.safetydata.go.kr  (전국 쉼터 6만여 곳)\n"
        "    · 기상청     : https://www.data.go.kr        (실시간 기온)\n"
        "    · Gemini     : https://aistudio.google.com   (민폐도 산출)\n"
        "\n"
        "  입력한 키는 이 PC의 %APPDATA%\\CoolMap\\secrets.json 에만 저장됩니다.\n"
        "  실행 파일에는 어떤 키도 들어있지 않습니다.\n"
        "\n"
        "현재 위치\n"
        "  Windows 설정 > 개인 정보 및 보안 > 위치 에서 앱 위치 접근을 켜주세요.\n"
        "  가상 머신처럼 GPS/Wi-Fi가 없는 환경에서는 IP 기반 추정으로 대체되며,\n"
        "  지도에서 마우스 우클릭으로 현재 위치를 직접 지정할 수도 있습니다.\n"
        "\n"
        "지도 데이터 © OpenStreetMap contributors\n",
        encoding="utf-8",
    )


def zip_folder(folder: Path) -> Path:
    out = ROOT / "dist" / f"{APP}-v{__version__}-win64.zip"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in folder.rglob("*"):
            if f.is_file():
                z.write(f, Path(APP) / f.relative_to(folder))
    return out


def main() -> int:
    folder = build()
    prune(folder)
    make_readme(folder)
    size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
    print(f"\n폴더: {folder}  ({size / 1024 / 1024:.0f} MB)")
    archive = zip_folder(folder)
    print(f"압축: {archive}  ({archive.stat().st_size / 1024 / 1024:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
