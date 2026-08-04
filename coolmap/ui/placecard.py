"""추천 목록 · 즐겨찾기에서 쓰는 장소 카드."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..ai import CROWD_ENABLED, Analysis
from ..theme import Palette
from .common import (
    ClickableCard,
    IconButton,
    IconLabel,
    MeterBar,
    Pill,
    crowd_color,
    mono,
    nuisance_color,
    ui_font,
)


class TempBox(QWidget):
    """실내 온도 표시 박스."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._temp = "--"
        self._caption = "실내"
        self._accent = QColor("#22D3EE")
        self._bg = QColor("#123243")
        self.setFixedSize(74, 60)

    def set_data(self, temp: str, caption: str = "실내") -> None:
        self._temp, self._caption = temp, caption
        self.update()

    def set_colors(self, accent: str, bg: str) -> None:
        self._accent = QColor(accent)
        self._bg = QColor(bg)
        self.update()

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self._bg)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 12, 12)
        p.setPen(self._accent)
        p.setFont(ui_font(19, QFont.ExtraBold))
        p.drawText(QRectF(0, 6, self.width(), 28), Qt.AlignCenter, self._temp)
        p.setFont(mono(8, QFont.DemiBold, 1.2))
        c = QColor(self._accent)
        c.setAlpha(170)
        p.setPen(c)
        p.drawText(QRectF(0, 34, self.width(), 16), Qt.AlignCenter, self._caption)
        p.end()


class PlaceCard(ClickableCard):
    """AI 추천 / 즐겨찾기 카드."""

    openRequested = Signal(str)
    favoriteToggled = Signal(str)

    def __init__(self, parent: QWidget | None = None, *, show_favorite: bool = False):
        super().__init__(parent, padding=18, spacing=12)
        self.setMinimumWidth(280)
        self._analysis: Analysis | None = None
        self._pal: Palette | None = None
        self._show_favorite = show_favorite
        self._fav = False
        lay = self.body()

        # 1행 — 이름 + 카테고리 아이콘
        top = QHBoxLayout()
        top.setSpacing(10)
        name_box = QVBoxLayout()
        name_box.setSpacing(5)
        self.name = QLabel("-")
        self.name.setFont(ui_font(16, QFont.ExtraBold))
        self.name.setWordWrap(True)
        walk = QHBoxLayout()
        walk.setSpacing(6)
        self.walk_icon = IconLabel("walk", 13, "#9FB3C8", 2.1)
        self.walk = QLabel("-")
        self.walk.setFont(mono(10, QFont.DemiBold, 0.6))
        self.walk.setObjectName("dim")
        walk.addWidget(self.walk_icon)
        walk.addWidget(self.walk)
        walk.addStretch(1)
        name_box.addWidget(self.name)
        name_box.addLayout(walk)

        self.cat_icon = IconLabel("building", 20, "#22D3EE", 1.9)
        self.cat_frame = QFrame()
        self.cat_frame.setObjectName("cardFlat")
        self.cat_frame.setFixedSize(40, 40)
        cf = QVBoxLayout(self.cat_frame)
        cf.setContentsMargins(0, 0, 0, 0)
        cf.addWidget(self.cat_icon, 0, Qt.AlignCenter)

        top.addLayout(name_box, 1)
        top.addWidget(self.cat_frame, 0, Qt.AlignTop)
        lay.addLayout(top)

        # 2행 — 온도 + 쾌적 점수
        score_frame = QFrame()
        score_frame.setObjectName("cardFlat")
        sf = QHBoxLayout(score_frame)
        sf.setContentsMargins(10, 10, 14, 10)
        sf.setSpacing(12)
        self.temp = TempBox()
        sf.addWidget(self.temp)
        right = QVBoxLayout()
        right.setSpacing(7)
        head = QHBoxLayout()
        self.score_label = QLabel("쾌적 점수")
        self.score_label.setFont(mono(10, QFont.DemiBold, 0.8))
        self.score_label.setObjectName("dim")
        self.score_value = QLabel("-/100")
        self.score_value.setFont(mono(10, QFont.Bold, 0.8))
        head.addWidget(self.score_label)
        head.addStretch(1)
        head.addWidget(self.score_value)
        self.score_bar = MeterBar(height=7)
        right.addStretch(1)
        right.addLayout(head)
        right.addWidget(self.score_bar)
        right.addStretch(1)
        sf.addLayout(right, 1)
        lay.addWidget(score_frame)

        # 3행 — 혼잡 / 민폐도 배지
        pills = QHBoxLayout()
        pills.setSpacing(7)
        self.crowd_pill = Pill("혼잡 -", "users")
        self.nuis_pill = Pill("민폐도 -", "star")
        pills.addWidget(self.crowd_pill)
        pills.addWidget(self.nuis_pill)
        pills.addStretch(1)
        lay.addLayout(pills)

        # 4행 — 사유 + 액션
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.reason_icon = IconLabel("bulb", 14, "#22D3EE", 2.0)
        self.reason = QLabel("-")
        self.reason.setObjectName("dim")
        self.reason.setFont(ui_font(11))
        self.reason.setWordWrap(True)
        bottom.addWidget(self.reason_icon, 0, Qt.AlignTop)
        bottom.addWidget(self.reason, 1)
        self.fav_btn = IconButton("heart", 32, 15, tooltip="즐겨찾기")
        self.fav_btn.setVisible(show_favorite)
        self.fav_btn.clicked.connect(self._toggle_fav)
        self.go_btn = IconButton("arrow_right", 32, 16, tooltip="상세 보기")
        self.go_btn.clicked.connect(lambda: self._analysis and self.openRequested.emit(self._analysis.place.id))
        bottom.addWidget(self.fav_btn, 0, Qt.AlignBottom)
        bottom.addWidget(self.go_btn, 0, Qt.AlignBottom)
        lay.addLayout(bottom)

        self.clicked.connect(lambda: self._analysis and self.openRequested.emit(self._analysis.place.id))

    def _toggle_fav(self) -> None:
        if self._analysis:
            self.favoriteToggled.emit(self._analysis.place.id)

    # ------------------------------------------------------------------
    def set_analysis(self, a: Analysis, pal: Palette, *, favorite: bool = False) -> None:
        self._analysis = a
        self._pal = pal
        place = a.place

        self.name.setText(place.name)
        self.walk.setText(f"{a.distance_label} ({a.walk_min}분)")
        self.cat_icon.set_icon(place.icon)

        if a.crowd.open_now:
            self.temp.set_data(f"{a.indoor:.0f}°C", "실내")
        else:
            self.temp.set_data("--", "운영종료")
        self.score_value.setText(f"{a.comfort}/100")
        self.score_bar.set_value(a.comfort / 100.0)

        if CROWD_ENABLED:
            cc = crowd_color(pal, a.crowd.key)
            self.crowd_pill.set_text(f"혼잡 {a.crowd.level}" if a.crowd.open_now else "운영 종료")
            self.crowd_pill.set_colors(cc.name(), pal.card)
        else:
            self.crowd_pill.set_text("혼잡도 준비 중")
            self.crowd_pill.set_colors(pal.text_mute, pal.card)

        nc = nuisance_color(pal, a.nuisance.key)
        self.nuis_pill.set_text(f"민폐도 {a.nuisance.score}")
        self.nuis_pill.set_colors(nc.name(), pal.card)

        if a.crowd.by_event:
            self.reason.setText(
                a.crowd.headline if CROWD_ENABLED
                else "인근에서 행사가 진행 중이에요 (평소보다 붐빌 수 있음)"
            )
            self.reason_icon.set_icon("alert")
            self.reason_icon.set_color(pal.warn)
            self.reason.setStyleSheet(f"color: {pal.warn};")
        else:
            self.reason.setText(
                f"{a.nuisance.level} · 권장 체류 {a.nuisance.stay_label}"
            )
            self.reason_icon.set_icon("star")
            self.reason_icon.set_color(pal.accent)
            self.reason.setStyleSheet(f"color: {pal.text_dim};")

        self._paint_palette(pal)
        self.set_favorite(favorite)

    def set_favorite(self, on: bool) -> None:
        self._fav = on
        if not self._show_favorite:
            return
        self.fav_btn.set_icon_name("heart_fill" if on else "heart")
        pal = self._pal
        if pal:
            self.fav_btn.set_color(pal.accent if on else pal.text_dim)

    def _paint_palette(self, p: Palette) -> None:
        """색상만 갱신 (데이터 재계산 없음)."""
        self.temp.set_colors(p.accent, p.accent_soft)
        self.score_bar.set_colors(p.accent, p.card_alt)
        self.cat_icon.set_color(p.accent)
        self.walk_icon.set_color(p.text_mute)
        self.go_btn.set_color(p.text_dim)
        self.fav_btn.set_color(p.accent if self._fav else p.text_dim)

    def apply_palette(self, p: Palette) -> None:
        self._pal = p
        self._paint_palette(p)
