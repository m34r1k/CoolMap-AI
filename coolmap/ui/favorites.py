"""즐겨찾기 화면."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..ai import analyze
from ..config import AppState
from ..catalog import find_by_id
from ..theme import Palette
from .common import EmptyState, mono
from .placecard import PlaceCard


class FavoritesView(QWidget):
    openPlace = Signal(str)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(32, 26, 32, 34)
        lay.setSpacing(20)

        head = QHBoxLayout()
        title = QLabel("즐겨찾기")
        title.setObjectName("h1")
        self.count = QLabel("")
        self.count.setObjectName("mute")
        self.count.setFont(mono(10))
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.count, 0, Qt.AlignBottom)
        lay.addLayout(head)

        self.sub = QLabel("자주 가는 쉼터를 모아 실시간 상태를 확인하세요.")
        self.sub.setObjectName("dim")
        lay.addWidget(self.sub)

        self.holder = QWidget()
        self.grid = QGridLayout(self.holder)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(18)
        for col in range(3):
            self.grid.setColumnStretch(col, 1)
        lay.addWidget(self.holder)

        self.empty = EmptyState(
            "heart", "아직 즐겨찾기가 없어요",
            "장소 상세 화면이나 추천 카드의 하트 버튼을 눌러 추가해 보세요.",
        )
        lay.addWidget(self.empty)
        lay.addStretch(1)

        self.cards: list[PlaceCard] = []

    def refresh(self) -> None:
        state = self.state
        p = state.palette
        hour, minute, weekday = state.now()
        favs = [q for q in (find_by_id(pid, state.mode, state.origin)
                            for pid in state.favorites) if q]
        analyses = [
            analyze(place, state.mode, hour, minute, weekday, state.target_temp,
                    origin=state.origin)
            for place in favs
        ]

        self.count.setText(f"{len(analyses)}곳")
        self.empty.setVisible(not analyses)
        self.holder.setVisible(bool(analyses))

        while len(self.cards) < len(analyses):
            c = PlaceCard(show_favorite=True)
            c.openRequested.connect(self.openPlace.emit)
            c.favoriteToggled.connect(self.state.toggle_favorite)
            c.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            i = len(self.cards)
            self.grid.addWidget(c, i // 3, i % 3)
            self.cards.append(c)

        for i, card in enumerate(self.cards):
            if i < len(analyses):
                card.setVisible(True)
                card.set_analysis(analyses[i], p, favorite=True)
            else:
                card.setVisible(False)

        unsupported = [p for p in favs if not p.supports(state.mode)]
        mode_word = "냉방" if state.mode == "cooling" else "난방"
        if unsupported:
            self.sub.setText(
                f"자주 가는 쉼터를 모아 실시간 상태를 확인하세요. "
                f"({len(unsupported)}곳은 {mode_word} 모드를 지원하지 않아 참고용으로 표시됩니다)"
            )
        else:
            self.sub.setText("자주 가는 쉼터를 모아 실시간 상태를 확인하세요.")

    def apply_palette(self, p: Palette) -> None:
        pass
