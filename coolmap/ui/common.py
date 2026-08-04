"""재사용 UI 컴포넌트."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..theme import KR_FONT, MONO_FONT, UI_FONT, Palette

CROWD_COLOR_KEYS = {
    "very_low": "good",
    "low": "good",
    "normal": "warn",
    "busy": "warn",
    "very_busy": "bad",
    "closed": "text_mute",
}

NUISANCE_COLOR_KEYS = {
    "very_low": "good",
    "low": "good",
    "normal": "warn",
    "high": "warn",
    "very_high": "bad",
}


def crowd_color(p: Palette, key: str) -> QColor:
    if key in ("very_low",):
        return QColor(p.good)
    if key == "low":
        return QColor(p.accent)
    return QColor(getattr(p, CROWD_COLOR_KEYS.get(key, "text_dim")))


def nuisance_color(p: Palette, key: str) -> QColor:
    return QColor(getattr(p, NUISANCE_COLOR_KEYS.get(key, "text_dim")))


def apply_palette_tree(root: QWidget, p: Palette) -> None:
    """apply_palette() 를 가진 모든 하위 위젯에 팔레트를 전파."""
    fn = getattr(root, "apply_palette", None)
    if callable(fn):
        fn(p)
    for w in root.findChildren(QWidget):
        fn = getattr(w, "apply_palette", None)
        if callable(fn):
            fn(p)


def set_prop(w: QWidget, name: str, value) -> None:
    """동적 QSS 속성을 바꾸고 스타일을 다시 적용."""
    w.setProperty(name, value)
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def add_shadow(widget: QWidget, blur: int = 34, alpha: int = 120, dy: int = 8) -> None:
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(eff)


def mono(size: int, weight: QFont.Weight = QFont.Normal, spacing: float = 1.4) -> QFont:
    """size 는 픽셀 단위 (QSS 의 px 와 맞춘다).

    Consolas 에는 한글 글리프가 없으므로 한글 폴백을 명시한다.
    """
    f = QFont(MONO_FONT)
    f.setFamilies([MONO_FONT, KR_FONT, UI_FONT])
    f.setPixelSize(size)
    f.setWeight(weight)
    f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def ui_font(size: int, weight: QFont.Weight = QFont.Normal) -> QFont:
    """size 는 픽셀 단위."""
    f = QFont(UI_FONT)
    f.setFamilies([UI_FONT, KR_FONT])
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


def elide(text: str, font: QFont, width: int) -> str:
    return QFontMetrics(font).elidedText(text, Qt.ElideRight, width)


# ---------------------------------------------------------------------------
class Card(QFrame):
    """기본 카드 컨테이너."""

    def __init__(self, parent: QWidget | None = None, *, flat: bool = False,
                 padding: int = 20, spacing: int = 14, shadow: bool = True):
        super().__init__(parent)
        self.setObjectName("cardFlat" if flat else "card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(padding, padding, padding, padding)
        lay.setSpacing(spacing)
        if shadow and not flat:
            add_shadow(self, blur=30, alpha=90, dy=6)

    def body(self) -> QVBoxLayout:
        return self.layout()


class IconLabel(QLabel):
    """벡터 아이콘 하나를 표시하는 라벨."""

    def __init__(self, name: str, size: int = 18, color: str = "#FFFFFF",
                 weight: float = 1.85, parent: QWidget | None = None):
        super().__init__(parent)
        self._name = name
        self._size = size
        self._color = color
        self._weight = weight
        self.setFixedSize(size, size)
        self._render()

    def _render(self) -> None:
        self.setPixmap(icons.icon_pixmap(self._name, self._size, self._color, self._weight))

    def set_icon(self, name: str) -> None:
        self._name = name
        self._render()

    def set_color(self, color: str) -> None:
        self._color = color
        self._render()


class IconButton(QPushButton):
    def __init__(self, name: str, size: int = 38, icon_size: int = 18,
                 color: str = "#FFFFFF", parent: QWidget | None = None,
                 tooltip: str = ""):
        super().__init__(parent)
        self.setObjectName("iconBtn")
        self._name = name
        self._icon_size = icon_size
        self._color = color
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        self._render()

    def _render(self) -> None:
        self.setIcon(icons.qicon(self._name, self._icon_size, self._color))
        self.setIconSize(QSize(self._icon_size, self._icon_size))

    def set_icon_name(self, name: str) -> None:
        self._name = name
        self._render()

    def set_color(self, color: str) -> None:
        self._color = color
        self._render()


class Pill(QWidget):
    """아이콘 + 텍스트의 알약형 배지."""

    def __init__(self, text: str, icon: str = "", parent: QWidget | None = None,
                 *, style: str = "soft", color: str = "#22D3EE",
                 bg: str = "#16202F", font_size: int = 11, mono_font: bool = True):
        super().__init__(parent)
        self._text = text
        self._icon = icon
        self._style = style
        self._color = QColor(color)
        self._bg = QColor(bg)
        self._font = mono(font_size, QFont.DemiBold) if mono_font else ui_font(font_size + 1, QFont.DemiBold)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._recalc()

    def _recalc(self) -> None:
        fm = QFontMetrics(self._font)
        w = fm.horizontalAdvance(self._text) + 24
        if self._icon:
            w += 20
        self.setFixedSize(w, 26)
        self.update()

    def set_text(self, text: str) -> None:
        self._text = text
        self._recalc()

    def set_colors(self, color: str, bg: str) -> None:
        self._color = QColor(color)
        self._bg = QColor(bg)
        self.update()

    def set_icon(self, name: str) -> None:
        self._icon = name
        self._recalc()

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        radius = r.height() / 2

        if self._style == "solid":
            p.setBrush(self._color)
            p.setPen(Qt.NoPen)
            fg = self._bg
        elif self._style == "outline":
            p.setBrush(Qt.NoBrush)
            pen = QPen(self._color)
            pen.setWidthF(1.2)
            p.setPen(pen)
            fg = self._color
        else:  # soft
            soft = QColor(self._color)
            soft.setAlpha(38)
            p.setBrush(soft)
            p.setPen(Qt.NoPen)
            fg = self._color
        p.drawRoundedRect(r, radius, radius)

        x = 11.0
        if self._icon:
            icons.draw_icon(p, self._icon, QRectF(x, (self.height() - 13) / 2, 13, 13), fg, 2.1)
            x += 18
        p.setFont(self._font)
        p.setPen(fg)
        p.drawText(QRectF(x, 0, self.width() - x - 8, self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self._text)
        p.end()


class MeterBar(QWidget):
    """가로 게이지."""

    def __init__(self, parent: QWidget | None = None, *, height: int = 8,
                 color: str = "#22D3EE", track: str = "#16202F"):
        super().__init__(parent)
        self._value = 0.0
        self._color = QColor(color)
        self._track = QColor(track)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self.update()

    def set_colors(self, color: str, track: str) -> None:
        self._color = QColor(color)
        self._track = QColor(track)
        self.update()

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        r = h / 2
        p.setPen(Qt.NoPen)
        p.setBrush(self._track)
        p.drawRoundedRect(QRectF(0, 0, self.width(), h), r, r)
        w = self.width() * self._value
        if w > 1:
            grad = QLinearGradient(0, 0, self.width(), 0)
            c2 = QColor(self._color)
            c2.setAlpha(210)
            grad.setColorAt(0.0, c2)
            grad.setColorAt(1.0, self._color)
            p.setBrush(grad)
            p.drawRoundedRect(QRectF(0, 0, max(w, h), h), r, r)
        p.end()


class StatTile(QFrame):
    """캡션 + 큰 숫자 타일."""

    def __init__(self, caption: str, value: str = "-", unit: str = "",
                 parent: QWidget | None = None, *, highlight: bool = False):
        super().__init__(parent)
        self.setObjectName("cardAccent" if highlight else "cardFlat")
        self._highlight = highlight
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 13, 16, 14)
        lay.setSpacing(5)
        self.caption = QLabel(caption)
        self.caption.setObjectName("label")
        self.caption.setAlignment(Qt.AlignCenter)
        row = QHBoxLayout()
        row.setSpacing(2)
        row.setAlignment(Qt.AlignCenter)
        self.value = QLabel(value)
        self.value.setFont(ui_font(23, QFont.ExtraBold))
        self.unit = QLabel(unit)
        self.unit.setObjectName("mute")
        self.unit.setFont(ui_font(10, QFont.DemiBold))
        row.addWidget(self.value, 0, Qt.AlignBottom)
        row.addWidget(self.unit, 0, Qt.AlignBottom)
        lay.addWidget(self.caption)
        lay.addLayout(row)

    def set_value(self, value: str, unit: str | None = None) -> None:
        self.value.setText(value)
        if unit is not None:
            self.unit.setText(unit)

    def set_value_color(self, color: str) -> None:
        self.value.setStyleSheet(f"color: {color};")


class SectionTitle(QWidget):
    """아이콘 + 제목 + 우측 액션."""

    def __init__(self, text: str, icon: str = "", parent: QWidget | None = None,
                 *, size: int = 20):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.icon = IconLabel(icon, 20, "#FFFFFF") if icon else None
        if self.icon:
            lay.addWidget(self.icon)
        self.label = QLabel(text)
        self.label.setFont(ui_font(size, QFont.ExtraBold))
        lay.addWidget(self.label)
        lay.addStretch(1)
        self._extra = lay

    def add_widget(self, w: QWidget) -> None:
        self._extra.addWidget(w)

    def apply_palette(self, p: Palette) -> None:
        if self.icon:
            self.icon.set_color(p.accent)


class GaugeArc(QWidget):
    """민폐도 등 0~100 점수를 보여주는 원호 게이지."""

    def __init__(self, parent: QWidget | None = None, *, size: int = 150):
        super().__init__(parent)
        self._value = 0
        self._label = ""
        self._sub = ""
        self._color = QColor("#22D3EE")
        self._track = QColor("#16202F")
        self._text = QColor("#E9F2F9")
        self._dim = QColor("#63788E")
        self.setFixedSize(size, size)

    def set_data(self, value: int, label: str, sub: str = "") -> None:
        self._value = value
        self._label = label
        self._sub = sub
        self.update()

    def set_colors(self, color: QColor, track: str, text: str, dim: str) -> None:
        self._color = QColor(color)
        self._track = QColor(track)
        self._text = QColor(text)
        self._dim = QColor(dim)
        self.update()

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        margin = 10
        d = min(w, h) - margin * 2
        rect = QRectF((w - d) / 2, (h - d) / 2, d, d)

        # 아래쪽 120°를 비운 240° 게이지 (210° 에서 시계방향)
        start, span = 210.0, 240.0

        pen = QPen(self._track)
        pen.setWidthF(10)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, int(start * 16), int(-span * 16))

        pen.setColor(self._color)
        p.setPen(pen)
        p.drawArc(rect, int(start * 16),
                  int(-span * 16 * max(0.0, min(1.0, self._value / 100.0))))

        p.setPen(self._text)
        p.setFont(ui_font(32, QFont.ExtraBold))
        p.drawText(QRectF(0, h * 0.30, w, h * 0.26), Qt.AlignCenter, str(self._value))
        p.setPen(self._color)
        p.setFont(ui_font(13, QFont.DemiBold))
        p.drawText(QRectF(0, h * 0.56, w, 20), Qt.AlignCenter, self._label)
        if self._sub:
            p.setPen(self._dim)
            p.setFont(mono(9, QFont.Normal, 0.4))
            p.drawText(QRectF(0, h * 0.73, w, 16), Qt.AlignCenter, self._sub)
        p.end()


class HourlyChart(QWidget):
    """24시간 혼잡도 예측 막대 그래프."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._values: list[float] = [0.0] * 24
        self._now = 12
        self._event_hours: set[int] = set()
        self._accent = QColor("#22D3EE")
        self._track = QColor("#16202F")
        self._dim = QColor("#63788E")
        self._warn = QColor("#FBBF24")
        self.setMinimumHeight(112)
        self.setMouseTracking(True)
        self._hover = -1

    def set_data(self, values: list[float], now: int, event_hours: set[int] | None = None) -> None:
        self._values = values
        self._now = now
        self._event_hours = event_hours or set()
        self.update()

    def set_colors(self, accent: str, track: str, dim: str, warn: str) -> None:
        self._accent = QColor(accent)
        self._track = QColor(track)
        self._dim = QColor(dim)
        self._warn = QColor(warn)
        self.update()

    def _bar_rect(self, i: int) -> QRectF:
        pad_bottom = 20
        gap = 3.0
        total = self.width()
        bw = (total - gap * 23) / 24
        x = i * (bw + gap)
        return QRectF(x, 0, bw, self.height() - pad_bottom)

    def mouseMoveEvent(self, ev) -> None:
        idx = -1
        for i in range(24):
            r = self._bar_rect(i)
            if r.x() - 1.5 <= ev.position().x() <= r.right() + 1.5:
                idx = i
                break
        if idx != self._hover:
            self._hover = idx
            if idx >= 0:
                v = self._values[idx]
                txt = "운영 종료" if v <= 0 else f"{idx:02d}:00 · 혼잡도 {int(v * 100)}%"
                self.setToolTip(txt)
            self.update()

    def leaveEvent(self, ev) -> None:
        self._hover = -1
        self.update()

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        avail = self.height() - 20
        for i in range(24):
            r = self._bar_rect(i)
            v = self._values[i]
            bh = max(3.0, avail * max(v, 0.03))
            bar = QRectF(r.x(), avail - bh, r.width(), bh)
            is_now = i == self._now
            if v <= 0:
                color = QColor(self._track)
                color.setAlpha(140)
            elif i in self._event_hours:
                color = QColor(self._warn)
                color.setAlpha(255 if is_now else 190)
            elif is_now:
                color = QColor(self._accent)
            else:
                color = QColor(self._accent)
                color.setAlpha(90 if i != self._hover else 165)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(bar, 3, 3)

            if is_now:
                p.setPen(QPen(self._accent, 1.4))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(bar.adjusted(-2, -3, 2, 0), 4, 4)

        p.setFont(mono(8, QFont.Normal, 0.6))
        for i in range(0, 24, 3):
            r = self._bar_rect(i)
            p.setPen(self._accent if i == self._now else self._dim)
            p.drawText(QRectF(r.x() - 8, self.height() - 17, r.width() + 16, 14),
                       Qt.AlignCenter, f"{i:02d}")
        p.end()


class TagRow(QWidget):
    """편의시설 태그 묶음 (자동 줄바꿈)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tags: list[str] = []
        self._font = mono(10, QFont.DemiBold)
        self._fg = QColor("#9FB3C8")
        self._bg = QColor("#16202F")
        self._border = QColor("#1E2A3D")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def set_tags(self, tags: list[str]) -> None:
        self._tags = tags
        self.updateGeometry()
        self.update()

    def set_colors(self, fg: str, bg: str, border: str) -> None:
        self._fg = QColor(fg)
        self._bg = QColor(bg)
        self._border = QColor(border)
        self.update()

    def _layout_tags(self, width: int) -> list[tuple[QRectF, str]]:
        fm = QFontMetrics(self._font)
        out: list[tuple[QRectF, str]] = []
        x = y = 0.0
        for t in self._tags:
            w = fm.horizontalAdvance(t) + 22
            if x + w > width and x > 0:
                x = 0.0
                y += 32
            out.append((QRectF(x, y, w, 27), t))
            x += w + 8
        return out

    def sizeHint(self) -> QSize:
        rects = self._layout_tags(max(self.width(), 200))
        h = int(rects[-1][0].bottom()) if rects else 0
        return QSize(200, h + 2)

    def resizeEvent(self, ev) -> None:
        self.updateGeometry()
        super().resizeEvent(ev)

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self._font)
        for rect, text in self._layout_tags(self.width()):
            p.setPen(QPen(self._border, 1))
            p.setBrush(self._bg)
            p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 13, 13)
            p.setPen(self._fg)
            p.drawText(rect, Qt.AlignCenter, text)
        p.end()


class ClickableCard(Card):
    """클릭 가능한 카드."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None, **kwargs):
        super().__init__(parent, **kwargs)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False

    def enterEvent(self, ev) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, ev) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton and self.rect().contains(ev.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(ev)


class HeroBanner(QWidget):
    """장소 상세의 대표 이미지 자리 — 카테고리별 그라디언트 + 아이콘."""

    def __init__(self, parent: QWidget | None = None, height: int = 260):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._icon = "building"
        self._c1 = QColor("#0E7490")
        self._c2 = QColor("#070C14")
        self._accent = QColor("#22D3EE")

    def set_data(self, icon: str, c1: str, c2: str, accent: str) -> None:
        self._icon = icon
        self._c1 = QColor(c1)
        self._c2 = QColor(c2)
        self._accent = QColor(accent)
        self.update()

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        grad = QLinearGradient(0, 0, w * 0.8, h)
        grad.setColorAt(0.0, self._c1)
        grad.setColorAt(1.0, self._c2)
        p.fillRect(self.rect(), grad)

        # 장식 그리드
        pen = QPen(QColor(255, 255, 255, 12))
        pen.setWidth(1)
        p.setPen(pen)
        step = 34
        for x in range(0, w + step, step):
            p.drawLine(x, 0, x - h // 2, h)
        for y in range(0, h, step):
            p.drawLine(0, y, w, y)

        # 은은한 원형 글로우
        glow = QColor(self._accent)
        glow.setAlpha(30)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(w * 0.78, h * 0.35), h * 0.55, h * 0.55)

        size = min(120, h * 0.5)
        icons.draw_icon(p, self._icon,
                        QRectF(w * 0.5 - size / 2, h * 0.5 - size / 2, size, size),
                        QColor(255, 255, 255, 62), 1.4)

        # 하단 페이드
        fade = QLinearGradient(0, h * 0.45, 0, h)
        c = QColor(self._c2)
        c.setAlpha(0)
        fade.setColorAt(0.0, c)
        c2 = QColor(self._c2)
        c2.setAlpha(235)
        fade.setColorAt(1.0, c2)
        p.fillRect(QRectF(0, h * 0.45, w, h * 0.55), fade)
        p.end()


class EmptyState(QWidget):
    def __init__(self, icon: str, title: str, sub: str, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)
        self._icon = IconLabel(icon, 46, "#63788E", 1.5)
        lay.addWidget(self._icon, 0, Qt.AlignCenter)
        t = QLabel(title)
        t.setFont(ui_font(17, QFont.Bold))
        t.setAlignment(Qt.AlignCenter)
        s = QLabel(sub)
        s.setObjectName("mute")
        s.setAlignment(Qt.AlignCenter)
        s.setWordWrap(True)
        lay.addWidget(t)
        lay.addWidget(s)

    def apply_palette(self, p: Palette) -> None:
        self._icon.set_color(p.text_mute)
