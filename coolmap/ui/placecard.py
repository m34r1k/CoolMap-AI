"""쉼터 카드 — 점수 대신 '걸어서 몇 분 · 지금 열렸는지 · 얼마나 머물러도 되는지' 를 쉬운 말로.

    TopCard  — 가장 먼저 갈 곳 (홈 · 지도에서 고른 곳 · 물어보기 답). 큰 길찾기 버튼이 있다.
    PlaceRow — 목록 한 줄.

mobile/src/components/PlaceCard.tsx 와 같은 구성이다.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..ai import Analysis
from .. import icons, providers
from ..plain import REPORT_KINDS, directions_url, open_line, report_line, stay_line, tags, temp_line, walk_line
from ..theme import Palette
from .common import ClickableCard, IconButton, IconLabel, elide, ui_font


def set_style(widget: QWidget, qss: str) -> None:
    """스타일시트가 바뀔 때만 적용한다. setStyleSheet 는 같은 값이어도 스타일을 다시 계산해서 비싸다."""
    if widget.styleSheet() != qss:
        widget.setStyleSheet(qss)


#: '길찾기' 를 누르면 부를 함수 (장소 id). 메인 창이 앱 안 길 안내(지도 화면)로 연결한다.
#: 정해지지 않았으면 카카오맵 웹 길찾기를 연다.
_route_handler: Callable[[str], None] | None = None


def set_route_handler(fn: Callable[[str], None]) -> None:
    global _route_handler
    _route_handler = fn


def start_route(a: Analysis, origin: tuple[float, float] | None) -> None:
    if _route_handler is not None:
        _route_handler(a.place.id)
    else:
        open_directions(a, origin)


def open_directions(a: Analysis, origin: tuple[float, float] | None) -> None:
    """카카오맵 웹 길찾기를 기본 브라우저로 연다 (현재 위치 → 쉼터)."""
    QDesktopServices.openUrl(QUrl(directions_url(a, origin)))


def tag_label(text: str, tone: str, p: Palette) -> QLabel:
    color = {"good": p.good, "warn": p.warn}.get(tone, p.text_dim)
    lab = QLabel(text)
    lab.setFont(ui_font(13, QFont.Bold))
    lab.setStyleSheet(f"color: {color}; border: 2px solid {color}; border-radius: 9px; padding: 2px 8px;")
    return lab


class ReportDialog(QDialog):
    """'어떤 문제가 있나요?' — 큰 버튼으로 고른다 (mobile/src/components/Report.tsx)."""

    def __init__(self, place_id: str, name: str, p: Palette, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("쉼터 문제 알리기")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(10)
        title = QLabel("어떤 문제가 있나요?")
        title.setFont(ui_font(20, QFont.ExtraBold))
        sub = QLabel(name)
        sub.setFont(ui_font(15))
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {p.text_dim};")
        lay.addWidget(title)
        lay.addWidget(sub)
        for kind, label, _ in REPORT_KINDS:
            b = QPushButton(f"  {label}")
            b.setIcon(icons.qicon("siren", 22, p.bad))
            b.setMinimumHeight(56)
            b.setFont(ui_font(17, QFont.Bold))
            b.setStyleSheet("text-align: left; padding-left: 16px;")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=kind: self._send(place_id, k))
            lay.addWidget(b)
        cancel = QPushButton("취소")
        cancel.setMinimumHeight(48)
        cancel.setFont(ui_font(16, QFont.Bold))
        cancel.clicked.connect(self.reject)
        lay.addWidget(cancel)

    def _send(self, place_id: str, kind: str) -> None:
        providers.report_provider().add(place_id, kind)     # 결과 안내는 메인 창이 띄운다
        self.accept()


class SirenButton(QToolButton):
    """사이렌 아이콘 + '알리기'. 누르면 제보 창이 뜬다."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._pid, self._name = "", ""
        self._pal: Palette | None = None
        self.setText("알리기")
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(icons.icon_size(28))
        self.setFont(ui_font(12, QFont.Bold))
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("이 쉼터에 문제가 있으면 알려 주세요")
        self.setAutoRaise(True)
        self.clicked.connect(self._open)

    def set_place(self, place_id: str, name: str, p: Palette) -> None:
        self._pid, self._name, self._pal = place_id, name, p
        self.setIcon(icons.qicon("siren", 28, p.bad))
        set_style(self, f"QToolButton {{ color: {p.bad}; border: none; background: transparent; padding: 2px; }}")

    def _open(self) -> None:
        if self._pid and self._pal:
            ReportDialog(self._pid, self._name, self._pal, self.window()).exec()


class InfoLine(QWidget):
    """아이콘 + 한 줄 정보."""

    def __init__(self, icon: str, parent: QWidget | None = None, size: int = 16):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.icon = IconLabel(icon, 20, "#9FB3C8", 2.0)
        self.text = QLabel("-")
        self.text.setFont(ui_font(size))
        self.text.setWordWrap(True)
        lay.addWidget(self.icon, 0, Qt.AlignTop)
        lay.addWidget(self.text, 1)

    def set(self, text: str, color: str, icon_color: str | None = None) -> None:
        self.text.setText(text)
        set_style(self.text, f"color: {color};")
        self.icon.set_color(icon_color or color)


class TopCard(ClickableCard):
    openRequested = Signal(str)
    closeRequested = Signal()

    def __init__(self, parent: QWidget | None = None, *, closable: bool = False):
        super().__init__(parent, padding=18, spacing=12)
        self._a: Analysis | None = None
        self._origin: tuple[float, float] | None = None
        lay = self.body()

        head = QHBoxLayout()
        head.setSpacing(12)
        self.cat_frame = QFrame()
        self.cat_frame.setFixedSize(48, 48)
        cf = QVBoxLayout(self.cat_frame)
        cf.setContentsMargins(0, 0, 0, 0)
        self.cat_icon = IconLabel("building", 24, "#22D3EE", 2.0)
        cf.addWidget(self.cat_icon, 0, Qt.AlignCenter)
        names = QVBoxLayout()
        names.setSpacing(2)
        self.name = QLabel("-")
        self.name.setFont(ui_font(21, QFont.ExtraBold))
        self.name.setWordWrap(True)
        self.category = QLabel("-")
        self.category.setFont(ui_font(14))
        names.addWidget(self.name)
        names.addWidget(self.category)
        head.addWidget(self.cat_frame, 0, Qt.AlignTop)
        head.addLayout(names, 1)
        self.siren = SirenButton()
        head.addWidget(self.siren, 0, Qt.AlignTop)
        self.close_btn = IconButton("close", 36, 16, tooltip="닫기")
        self.close_btn.clicked.connect(self.closeRequested.emit)
        self.close_btn.setVisible(closable)
        head.addWidget(self.close_btn, 0, Qt.AlignTop)
        lay.addLayout(head)

        self.tags = QHBoxLayout()
        self.tags.setSpacing(6)
        lay.addLayout(self.tags)

        self.report = InfoLine("siren")
        self.walk = InfoLine("walk")
        self.open = InfoLine("clock")
        self.temp = InfoLine("thermo")
        self.stay = InfoLine("star")
        for w in (self.report, self.walk, self.open, self.temp, self.stay):
            lay.addWidget(w)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.route_btn = QPushButton("  길찾기")
        self.route_btn.setObjectName("primary")
        self.route_btn.setCursor(Qt.PointingHandCursor)
        self.route_btn.setMinimumHeight(50)
        self.route_btn.clicked.connect(self._route)
        self.more_btn = QPushButton("자세히")
        self.more_btn.setCursor(Qt.PointingHandCursor)
        self.more_btn.setMinimumHeight(50)
        self.more_btn.setFont(ui_font(16, QFont.Bold))
        self.more_btn.clicked.connect(self._open)
        btns.addWidget(self.route_btn, 1)
        btns.addWidget(self.more_btn)
        lay.addLayout(btns)

        self.clicked.connect(self._open)

    def _open(self) -> None:
        if self._a:
            self.openRequested.emit(self._a.place.id)

    def _route(self) -> None:
        if self._a:
            start_route(self._a, self._origin)

    def set_analysis(self, a: Analysis, state) -> None:
        from .. import icons

        self._a = a
        self._origin = state.origin
        p = state.palette
        hour, minute, weekday = state.now()
        open_ = a.open_now

        self.name.setText(a.place.name)
        self.category.setText(a.place.category_label)
        set_style(self.category, f"color: {p.text_dim};")
        self.cat_icon.set_icon(a.place.icon)
        self.cat_icon.set_color(p.accent)
        set_style(self.cat_frame, f"background: {p.accent_soft}; border-radius: 24px;")
        set_style(self, f"QFrame#card {{ border: 2px solid {p.accent}; }}")

        while self.tags.count():
            item = self.tags.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for text, tone in tags(a):
            self.tags.addWidget(tag_label(text, tone, p))
        self.tags.addStretch(1)

        self.siren.set_place(a.place.id, a.place.name, p)
        r = providers.report_provider().get(a.place.id)
        self.report.setVisible(bool(r))
        if r:
            self.report.set(report_line(r), p.bad)
        self.walk.set(walk_line(a), p.text, p.text_dim)
        self.open.set(open_line(a, hour, minute, weekday), p.good if open_ else p.text_mute)
        self.temp.set(temp_line(a), p.text, p.text_dim)
        self.stay.set(stay_line(a), p.text, p.text_dim)
        self.temp.setVisible(open_)
        self.stay.setVisible(open_)

        self.route_btn.setIcon(icons.qicon("walk", 20, p.accent_ink))
        self.close_btn.set_color(p.text_dim)

    def apply_palette(self, p: Palette) -> None:
        pass


class PlaceRow(QFrame):
    """목록 한 줄. 누르면 clicked, 두 번 누르면 opened."""

    clicked = Signal(str)
    opened = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("cardFlat")
        self.setProperty("hoverable", True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(68)
        self._pid = ""
        self._name_text = "-"
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 12, 10)
        lay.setSpacing(12)

        self.icon = IconLabel("building", 22, "#22D3EE", 1.9)
        lay.addWidget(self.icon, 0, Qt.AlignVCenter)

        mid = QVBoxLayout()
        mid.setSpacing(2)
        self.name = QLabel("-")
        self.name.setFont(ui_font(17, QFont.Bold))
        self.name.setMinimumWidth(0)
        self.name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.meta = QLabel("-")
        self.meta.setFont(ui_font(14))
        self.meta.setTextFormat(Qt.RichText)
        self.sub = QLabel("")
        self.sub.setFont(ui_font(13))
        mid.addWidget(self.name)
        mid.addWidget(self.meta)
        mid.addWidget(self.sub)
        lay.addLayout(mid, 1)

        self.chev = IconLabel("chevron_right", 22, "#63788E", 2.0)
        lay.addWidget(self.chev, 0, Qt.AlignVCenter)

    def set_analysis(self, a: Analysis, state) -> None:
        p = state.palette
        hour, minute, weekday = state.now()
        open_ = a.open_now
        self._pid = a.place.id
        self.icon.set_icon(a.place.icon)
        # AI 추정 쉼터는 노란 아이콘과 'AI 추정' 글자로 공식 쉼터와 구분한다
        self.icon.set_color(p.text_mute if not open_ else p.warn if a.place.ai_guess else p.accent)
        self._name_text = a.place.name
        self._apply_name()
        set_style(self.name, f"color: {p.text if open_ else p.text_dim};")
        status = (f"<span style='color:{p.good}; font-weight:700'>지금 열림</span>" if open_
                  else f"<span style='color:{p.text_mute}; font-weight:700'>문 닫음</span>")
        guess = f" · <span style='color:{p.warn}'>AI 추정</span>" if a.place.ai_guess else ""
        if providers.report_provider().get(a.place.id):
            guess += f" · <span style='color:{p.bad}; font-weight:700'>제보 있음</span>"
        self.meta.setText(f"<span style='color:{p.text_dim}'>걸어서 {max(1, a.walk_min)}분 · </span>"
                          f"{status}<span style='color:{p.text_dim}'>{guess}</span>")
        self.sub.setVisible(not open_)
        self.sub.setText(open_line(a, hour, minute, weekday))
        set_style(self.sub, f"color: {p.text_mute};")
        self.chev.set_color(p.text_mute)

    def _apply_name(self) -> None:
        self.name.setText(elide(self._name_text, self.name.font(), max(90, self.width() - 90)))

    def resizeEvent(self, ev) -> None:
        self._apply_name()
        super().resizeEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton and self.rect().contains(ev.position().toPoint()):
            self.clicked.emit(self._pid)

    def mouseDoubleClickEvent(self, ev) -> None:
        self.opened.emit(self._pid)
