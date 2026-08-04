"""CoolMap 테마 — 냉방(Cooling) / 난방(Heating) 두 벌의 팔레트와 QSS."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from string import Template

from PySide6.QtGui import QColor


COOLING = "cooling"
HEATING = "heating"


@dataclass(frozen=True)
class Palette:
    key: str
    label: str
    tagline: str
    mode_icon: str

    # 강조색
    accent: str
    accent_bright: str
    accent_deep: str
    accent_ink: str
    accent_soft: str

    # 표면
    bg: str
    panel: str
    card: str
    card_alt: str
    hover: str
    border: str
    border_soft: str

    # 글자
    text: str
    text_dim: str
    text_mute: str

    # 상태
    good: str
    warn: str
    bad: str

    # 지도
    map_bg: str
    map_block: str
    map_building: str
    map_building_edge: str
    map_road: str
    map_road_major: str
    map_water: str
    map_park: str

    def qcolor(self, name: str) -> QColor:
        return QColor(getattr(self, name))

    def rgba(self, name: str, alpha: float) -> QColor:
        c = QColor(getattr(self, name))
        c.setAlphaF(alpha)
        return c


COOLING_PALETTE = Palette(
    key=COOLING,
    label="냉방 모드",
    tagline="폭염 대응 · 시원한 쉼터를 찾습니다",
    mode_icon="snow",
    accent="#22D3EE",
    accent_bright="#7DE9F8",
    accent_deep="#0E7490",
    accent_ink="#032630",
    accent_soft="#123243",
    bg="#070C14",
    panel="#0B111C",
    card="#111A28",
    card_alt="#16202F",
    hover="#1A2637",
    border="#1E2A3D",
    border_soft="#152030",
    text="#E9F2F9",
    text_dim="#9FB3C8",
    text_mute="#63788E",
    good="#34D399",
    warn="#FBBF24",
    bad="#F87171",
    map_bg="#0A1220",
    map_block="#0E1826",
    map_building="#16233A",
    map_building_edge="#23334B",
    map_road="#0C1725",
    map_road_major="#132234",
    map_water="#0B2436",
    map_park="#0F2620",
)

HEATING_PALETTE = Palette(
    key=HEATING,
    label="난방 모드",
    tagline="한파 대응 · 따뜻한 쉼터를 찾습니다",
    mode_icon="flame",
    accent="#FF7043",
    accent_bright="#FFA981",
    accent_deep="#B2401C",
    accent_ink="#2C0B03",
    accent_soft="#3D1B12",
    bg="#100708",
    panel="#170B0C",
    card="#211112",
    card_alt="#2A1719",
    hover="#331D1E",
    border="#3B2225",
    border_soft="#2C1719",
    text="#FCEEE9",
    text_dim="#D2AEA4",
    text_mute="#9A736B",
    good="#7BC96F",
    warn="#F7C948",
    bad="#FF6B6B",
    map_bg="#150A0B",
    map_block="#1B0F10",
    map_building="#281719",
    map_building_edge="#3D2426",
    map_road="#180D0E",
    map_road_major="#241416",
    map_water="#16232C",
    map_park="#1B2417",
)

PALETTES = {COOLING: COOLING_PALETTE, HEATING: HEATING_PALETTE}


def palette_for(mode: str) -> Palette:
    return PALETTES.get(mode, COOLING_PALETTE)


UI_FONT = "Segoe UI"
MONO_FONT = "Consolas"
KR_FONT = "Malgun Gothic"   # Consolas/Segoe UI 에 없는 한글 글리프 폴백


_QSS = Template(
    """
* { outline: 0; }

/* 전역 규칙에 font-family/size 를 두면 위젯의 setFont() 를 덮어써 버린다.
   기본 글꼴은 QApplication.setFont() 로 지정하고, 여기서는 색만 상속시킨다. */
QWidget {
    color: $text;
}

QWidget#root, QMainWindow {
    background: $bg;
}

QToolTip {
    background: $card_alt;
    color: $text;
    border: 1px solid $border;
    padding: 6px 9px;
    border-radius: 6px;
}

/* ---------- 사이드바 ---------- */
QFrame#sidebar {
    background: $panel;
    border-right: 1px solid $border_soft;
}
QLabel#brandTitle {
    color: $accent;
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.5px;
}
QLabel#brandSub {
    color: $text_mute;
    font-family: "$mono_font", "$kr_font";
    font-size: 10px;
    letter-spacing: 2px;
}
QPushButton#navItem {
    background: transparent;
    border: none;
    border-radius: 14px;
    color: $text_dim;
    font-size: 16px;
    font-weight: 600;
    text-align: left;
    padding: 13px 16px;
}
QPushButton#navItem:hover {
    background: $hover;
    color: $text;
}
QPushButton#navItem[active="true"] {
    background: $accent;
    color: $accent_ink;
    font-weight: 700;
}

/* ---------- 상단 바 ---------- */
QFrame#topbar {
    background: $panel;
    border-bottom: 1px solid $border_soft;
}
QLineEdit#search {
    background: $card;
    border: 1px solid $border;
    border-radius: 20px;
    padding: 10px 16px 10px 40px;
    color: $text;
    selection-background-color: $accent;
    selection-color: $accent_ink;
}
QLineEdit#search:focus { border: 1px solid $accent; }
QLineEdit {
    background: $card;
    border: 1px solid $border;
    border-radius: 10px;
    padding: 9px 12px;
    color: $text;
    selection-background-color: $accent;
    selection-color: $accent_ink;
}
QLineEdit:focus { border: 1px solid $accent; }

/* ---------- 카드 ---------- */
QFrame#card {
    background: $card;
    border: 1px solid $border_soft;
    border-radius: 18px;
}
QFrame#cardFlat {
    background: $card_alt;
    border: 1px solid $border_soft;
    border-radius: 14px;
}
QFrame#cardFlat[selected="true"] {
    background: $accent_soft;
    border: 1px solid $accent;
}
QFrame#cardFlat[hoverable="true"]:hover {
    border: 1px solid $accent_deep;
}
QFrame#cardAccent {
    background: $accent_soft;
    border: 1px solid $accent_deep;
    border-radius: 14px;
}
QFrame#divider {
    background: $border_soft;
    border: none;
    max-height: 1px;
    min-height: 1px;
}

QLabel#h1 { font-size: 30px; font-weight: 800; letter-spacing: -0.6px; }
QLabel#h2 { font-size: 21px; font-weight: 750; letter-spacing: -0.3px; }
QLabel#h3 { font-size: 16px; font-weight: 700; }
QLabel#body { color: $text_dim; font-size: 14px; }
QLabel#dim   { color: $text_dim; }
QLabel#mute  { color: $text_mute; }
QLabel#accent { color: $accent; font-weight: 700; }
QLabel#label {
    color: $text_mute;
    font-family: "$mono_font", "$kr_font";
    font-size: 10px;
    letter-spacing: 1.6px;
}
QLabel#bigNum {
    color: $accent;
    font-size: 30px;
    font-weight: 800;
}

/* ---------- 버튼 ---------- */
QPushButton {
    background: $card_alt;
    border: 1px solid $border;
    border-radius: 12px;
    padding: 10px 16px;
    color: $text;
    font-weight: 600;
}
QPushButton:hover { background: $hover; border-color: $accent_deep; }
QPushButton:pressed { background: $card; }
QPushButton:disabled { color: $text_mute; background: $card; }

QPushButton#primary {
    background: $accent;
    color: $accent_ink;
    border: none;
    border-radius: 22px;
    padding: 13px 22px;
    font-size: 15px;
    font-weight: 800;
}
QPushButton#primary:hover { background: $accent_bright; }
QPushButton#primary:pressed { background: $accent_deep; color: $text; }

QPushButton#ghost {
    background: transparent;
    border: 1px solid $border;
    border-radius: 16px;
    padding: 8px 14px;
    color: $text_dim;
}
QPushButton#ghost:hover { color: $text; border-color: $accent; }

QPushButton#chip {
    background: $card_alt;
    border: 1px solid $border;
    border-radius: 15px;
    padding: 7px 13px;
    color: $text_dim;
    font-family: "$mono_font", "$kr_font";
    font-size: 11px;
    font-weight: 600;
}
QPushButton#chip:hover { color: $text; border-color: $accent_deep; }
QPushButton#chip[active="true"] {
    background: $accent_soft;
    border-color: $accent;
    color: $accent;
}

QPushButton#iconBtn {
    background: $card_alt;
    border: 1px solid $border_soft;
    border-radius: 19px;
    padding: 0;
}
QPushButton#iconBtn:hover { border-color: $accent; }

QPushButton#modeOption {
    background: $card_alt;
    border: 1px solid $border;
    border-radius: 14px;
    padding: 14px 16px;
    font-size: 16px;
    font-weight: 700;
    text-align: left;
    color: $text_dim;
}
QPushButton#modeOption:hover { border-color: $accent_deep; color: $text; }
QPushButton#modeOption[active="true"] {
    background: $accent;
    border-color: $accent;
    color: $accent_ink;
}

/* ---------- 입력 ---------- */
QComboBox {
    background: $card_alt;
    border: 1px solid $border;
    border-radius: 10px;
    padding: 8px 12px;
    color: $text;
    min-width: 150px;
}
QComboBox:hover { border-color: $accent_deep; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: $card_alt;
    border: 1px solid $border;
    border-radius: 8px;
    color: $text;
    selection-background-color: $accent_soft;
    selection-color: $accent;
    padding: 4px;
    outline: 0;
}
QCheckBox { color: $text_dim; spacing: 10px; }
QCheckBox::indicator {
    width: 18px; height: 18px;
    border-radius: 5px;
    border: 1px solid $border;
    background: $card_alt;
}
QCheckBox::indicator:checked {
    background: $accent;
    border-color: $accent;
    image: none;
}
QSlider::groove:horizontal {
    height: 5px; border-radius: 3px; background: $card_alt;
}
QSlider::sub-page:horizontal { background: $accent; border-radius: 3px; }
QSlider::handle:horizontal {
    width: 16px; height: 16px; margin: -6px 0;
    border-radius: 8px; background: $accent; border: 3px solid $panel;
}

QTextEdit, QPlainTextEdit {
    background: $card;
    border: 1px solid $border;
    border-radius: 12px;
    color: $text;
    padding: 8px;
    selection-background-color: $accent;
    selection-color: $accent_ink;
}

/* ---------- 스크롤 ---------- */
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QScrollBar:vertical {
    background: transparent; width: 10px; margin: 4px 2px 4px 0;
}
QScrollBar::handle:vertical {
    background: $border; border-radius: 5px; min-height: 40px;
}
QScrollBar::handle:vertical:hover { background: $accent_deep; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0 4px 2px 4px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 5px; min-width: 40px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""
)


def build_qss(p: Palette) -> str:
    values = asdict(p)
    values["ui_font"] = UI_FONT
    values["mono_font"] = MONO_FONT
    values["kr_font"] = KR_FONT
    return _QSS.substitute(values)
