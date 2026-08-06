"""지도 캔버스 — OSM 타일 위에 실제 건물 하이라이트 / 화살표 마커를 렌더링."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from .. import icons, providers
from ..ai import Analysis
from ..config import MARKER_ARROW, AppState
from ..geo import TILE_SIZE, resolution
from ..models import Place
from ..theme import Palette
from .common import crowd_color, mono, ui_font

MIN_ZOOM = 12.0
MAX_ZOOM = 18.6
DEFAULT_ZOOM = 15.4


class MapCanvas(QWidget):
    placeClicked = Signal(str)
    placeActivated = Signal(str)
    viewChanged = Signal()
    originPicked = Signal(float, float)   # 우클릭으로 현재 위치 지정

    def __init__(self, state: AppState, parent: QWidget | None = None,
                 *, compact: bool = False):
        super().__init__(parent)
        self.state = state
        self.compact = compact
        self.setMouseTracking(True)
        self.setMinimumSize(320, 220)
        self.setCursor(Qt.ArrowCursor if compact else Qt.OpenHandCursor)

        self._palette: Palette = state.palette
        self._analyses: dict[str, Analysis] = {}
        self._places: list[Place] = []
        self._events: list = []
        self._selected: str | None = None
        self._hover: str | None = None

        self._center = state.origin
        self._zoom = DEFAULT_ZOOM
        self._drag_from: QPointF | None = None
        self._drag_center: tuple[float, float] | None = None
        self._user_moved = False

        self._hit_zones: list[tuple[QRectF, str]] = []
        self._phase = 0.0
        self.radius = 0.0

        self.tiles = providers.tile_provider()
        self.buildings = providers.building_provider()
        self.tiles.tileReady.connect(self._deferred_update)
        self.buildings.updated.connect(self._deferred_update)
        self._building_cache: dict[str, dict | None] = {}

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    # -- 데이터 ----------------------------------------------------------
    def set_data(self, analyses: list[Analysis], events: list) -> None:
        self._analyses = {a.place.id: a for a in analyses}
        self._places = [a.place for a in analyses]
        self._events = events
        self.update()

    def apply_palette(self, p: Palette) -> None:
        self._palette = p
        self.tiles.set_mode(p.key)
        self.update()

    def set_selected(self, place_id: str | None) -> None:
        self._selected = place_id
        self.update()

    def _deferred_update(self) -> None:
        # 워커 스레드에서 오는 신호 → 다음 이벤트 루프에서 리페인트
        QTimer.singleShot(0, self.update)

    def _tick(self) -> None:
        if not self.state.get("animations"):
            return
        self._phase += 0.04
        self.update()

    # -- 투영 -------------------------------------------------------------
    def _world_px(self, lat: float, lon: float, zoom: float | None = None) -> tuple[float, float]:
        z = self._zoom if zoom is None else zoom
        n = TILE_SIZE * (2.0 ** z)
        lat = max(-85.05112878, min(85.05112878, lat))
        x = (lon + 180.0) / 360.0 * n
        y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
        return x, y

    def to_screen(self, lat: float, lon: float) -> QPointF:
        wx, wy = self._world_px(lat, lon)
        cx, cy = self._world_px(*self._center)
        return QPointF(self.width() / 2 + wx - cx, self.height() / 2 + wy - cy)

    def to_latlon(self, pt: QPointF) -> tuple[float, float]:
        cx, cy = self._world_px(*self._center)
        n = TILE_SIZE * (2.0 ** self._zoom)
        wx = cx + pt.x() - self.width() / 2
        wy = cy + pt.y() - self.height() / 2
        lon = wx / n * 360.0 - 180.0
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * wy / n))))
        return lat, lon

    def meters_per_pixel(self) -> float:
        return resolution(self._center[0], int(round(self._zoom))) * \
            (2 ** (int(round(self._zoom)) - self._zoom))

    def visible_bounds(self) -> tuple[float, float, float, float]:
        """(min_lat, min_lon, max_lat, max_lon)"""
        tl = self.to_latlon(QPointF(0, 0))
        br = self.to_latlon(QPointF(self.width(), self.height()))
        return min(tl[0], br[0]), min(tl[1], br[1]), max(tl[0], br[0]), max(tl[1], br[1])

    # -- 뷰 조작 ----------------------------------------------------------
    def fit_all(self) -> None:
        """모든 쉼터가 들어오도록 맞춘다."""
        if not self._places or self.width() < 10:
            self._center, self._zoom = self.state.origin, DEFAULT_ZOOM
            self.update()
            return
        origin = self.state.origin
        lats = [p.lat for p in self._places] + [origin[0]]
        lons = [p.lon for p in self._places] + [origin[1]]
        self._center = ((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2)

        pad = 70 if not self.compact else 34
        for z in [x / 4 for x in range(int(MAX_ZOOM * 4), int(MIN_ZOOM * 4) - 1, -1)]:
            self._zoom = z
            xs = [self._world_px(la, lo)[0] for la, lo in zip(lats, lons)]
            ys = [self._world_px(la, lo)[1] for la, lo in zip(lats, lons)]
            if (max(xs) - min(xs) < self.width() - pad * 2
                    and max(ys) - min(ys) < self.height() - pad * 2):
                break
        self._user_moved = False
        self.update()
        self.viewChanged.emit()

    def center_on(self, latlon: tuple[float, float], zoom: float | None = None) -> None:
        self._user_moved = True
        self._center = latlon
        if zoom is not None:
            self._zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        self.update()
        self.viewChanged.emit()

    def zoom_by(self, factor: float, anchor: QPointF | None = None) -> None:
        self._user_moved = True
        delta = math.log2(factor)
        if anchor is None:
            self._zoom = max(MIN_ZOOM, min(MAX_ZOOM, self._zoom + delta))
        else:
            before = self.to_latlon(anchor)
            self._zoom = max(MIN_ZOOM, min(MAX_ZOOM, self._zoom + delta))
            after = self.to_latlon(anchor)
            self._center = (self._center[0] + before[0] - after[0],
                            self._center[1] + before[1] - after[1])
        self.update()
        self.viewChanged.emit()

    @property
    def zoom_percent(self) -> int:
        return int((self._zoom - MIN_ZOOM) / (MAX_ZOOM - MIN_ZOOM) * 100)

    # -- 입력 -------------------------------------------------------------
    def resizeEvent(self, ev) -> None:
        if not self._user_moved:
            self.fit_all()
        super().resizeEvent(ev)

    def wheelEvent(self, ev) -> None:
        if self.compact:
            return
        self.zoom_by(1.0016 ** ev.angleDelta().y(), ev.position())

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.RightButton and not self.compact:
            lat, lon = self.to_latlon(ev.position())
            self.originPicked.emit(lat, lon)
            return
        if ev.button() != Qt.LeftButton:
            return
        hit = self._hit_test(ev.position())
        if hit:
            self._selected = hit
            self.placeClicked.emit(hit)
            self.update()
            return
        if not self.compact:
            self._drag_from = ev.position()
            self._drag_center = self._center
            self._user_moved = True
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, ev) -> None:
        if self._drag_from is not None and self._drag_center is not None:
            n = TILE_SIZE * (2.0 ** self._zoom)
            dx = ev.position().x() - self._drag_from.x()
            dy = ev.position().y() - self._drag_from.y()
            cx, cy = self._world_px(*self._drag_center)
            cx -= dx
            cy -= dy
            lon = cx / n * 360.0 - 180.0
            lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * cy / n))))
            self._center = (lat, lon)
            self.update()
            return
        hit = self._hit_test(ev.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.PointingHandCursor if hit else
                           (Qt.ArrowCursor if self.compact else Qt.OpenHandCursor))
            a = self._analyses.get(hit) if hit else None
            self.setToolTip(
                f"{a.place.name}\n실내 {a.indoor}°C · 민폐도 {a.nuisance.score}" if a else ""
            )
            self.update()

    def mouseReleaseEvent(self, ev) -> None:
        self._drag_from = None
        self._drag_center = None
        self.setCursor(Qt.ArrowCursor if self.compact else Qt.OpenHandCursor)
        self.viewChanged.emit()

    def mouseDoubleClickEvent(self, ev) -> None:
        hit = self._hit_test(ev.position())
        if hit:
            self.placeActivated.emit(hit)

    def _hit_test(self, pos: QPointF) -> str | None:
        for rect, pid in reversed(self._hit_zones):
            if rect.contains(pos):
                return pid
        return None

    # -- 렌더링 ------------------------------------------------------------
    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        pal = self._palette

        if self.radius > 0:
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(self.rect()), self.radius, self.radius)
            p.setClipPath(clip)
        p.fillRect(self.rect(), QColor(pal.map_bg))

        self._draw_tiles(p, pal)
        if self.state.get("show_event_zones"):
            self._draw_events(p, pal)

        self._hit_zones = []
        self._draw_markers(p, pal)
        self._draw_user(p, pal)
        self._draw_overlay(p, pal)
        p.end()

    # ------------------------------------------------------------------
    def _draw_tiles(self, p: QPainter, pal: Palette) -> None:
        level = int(min(self.tiles.max_zoom, max(0, math.floor(self._zoom))))
        scale = 2.0 ** (self._zoom - level)
        size = TILE_SIZE * scale

        ccx, ccy = self._world_px(*self._center, zoom=level)
        half_w = self.width() / 2 / scale
        half_h = self.height() / 2 / scale
        x0 = int(math.floor((ccx - half_w) / TILE_SIZE))
        x1 = int(math.floor((ccx + half_w) / TILE_SIZE))
        y0 = int(math.floor((ccy - half_h) / TILE_SIZE))
        y1 = int(math.floor((ccy + half_h) / TILE_SIZE))
        n_tiles = 2 ** level

        missing = 0
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                if ty < 0 or ty >= n_tiles:
                    continue
                wrapped = tx % n_tiles
                sx = (tx * TILE_SIZE - ccx) * scale + self.width() / 2
                sy = (ty * TILE_SIZE - ccy) * scale + self.height() / 2
                pm = self.tiles.get(level, wrapped, ty)
                if pm is None:
                    missing += 1
                    continue
                p.drawPixmap(QRectF(sx, sy, size + 1, size + 1), pm,
                             QRectF(0, 0, TILE_SIZE, TILE_SIZE))
        self._tiles_missing = missing

    def _draw_events(self, p: QPainter, pal: Palette) -> None:
        mpp = self.meters_per_pixel()
        if mpp <= 0:
            return
        for ev in self._events:
            c = self.to_screen(ev.lat, ev.lon)
            r = ev.radius / mpp
            if r < 8:
                continue
            grad = QRadialGradient(c, r)
            c1 = QColor(pal.warn)
            c1.setAlpha(44)
            grad.setColorAt(0.0, c1)
            c2 = QColor(pal.warn)
            c2.setAlpha(0)
            grad.setColorAt(1.0, c2)
            p.setPen(Qt.NoPen)
            p.setBrush(grad)
            p.drawEllipse(c, r, r)

            pen = QPen(QColor(pal.warn))
            pen.setWidthF(1.5)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            pulse = 1.0 + math.sin(self._phase * 1.4) * 0.012
            p.drawEllipse(c, r * pulse, r * pulse)

    # ------------------------------------------------------------------
    def _building_for(self, place: Place) -> dict | None:
        cached = self._building_cache.get(place.id, "miss")
        if cached != "miss":
            return cached
        b = self.buildings.building_at(place.lat, place.lon)
        if b is not None:
            self._building_cache[place.id] = b
        return b

    def _draw_markers(self, p: QPainter, pal: Palette) -> None:
        # 보이는 영역의 건물 셀을 미리 채운다
        if self._zoom >= 14.5:
            self.buildings.buildings_in(*self.visible_bounds())

        label_rects: list[QRectF] = []
        ordered = sorted(self._places,
                         key=lambda pl: (pl.id == self._selected, pl.id == self._hover))
        for place in ordered:
            a = self._analyses.get(place.id)
            if a is None:
                continue
            if not self.state.get("show_closed") and not a.crowd.open_now:
                continue
            style = self.state.marker_style_for(place)
            selected = place.id == self._selected
            hovered = place.id == self._hover

            if style == MARKER_ARROW:
                anchor = self._draw_arrow_marker(p, pal, place, a, selected, hovered)
            else:
                anchor = self._draw_highlight_marker(p, pal, place, a, selected, hovered)

            if self.state.get("map_labels") and not self.compact:
                self._draw_label(p, pal, place, a, anchor, label_rects, selected, hovered)
            else:
                self._hit_zones.append(
                    (QRectF(anchor.x() - 16, anchor.y() - 16, 32, 32), place.id))

    def _accent_for(self, pal: Palette, a: Analysis) -> QColor:
        return QColor(pal.text_mute) if not a.crowd.open_now else QColor(pal.accent)

    @staticmethod
    def _outline_pen(color: QColor, width: float, guess: bool) -> QPen:
        """마커 외곽선. AI 추정 쉼터는 점선으로 그려 공식 쉼터와 구분한다."""
        pen = QPen(color)
        pen.setWidthF(width)
        pen.setJoinStyle(Qt.RoundJoin)
        if guess:
            pen.setStyle(Qt.CustomDashLine)
            pen.setDashPattern([4.0, 3.0])
        return pen

    def _draw_highlight_marker(self, p: QPainter, pal: Palette, place: Place,
                               a: Analysis, selected: bool, hovered: bool) -> QPointF:
        """실제 건물 외곽선을 하이라이트 (없으면 원형으로 폴백)."""
        color = self._accent_for(pal, a)
        center = self.to_screen(place.lat, place.lon)
        b = self._building_for(place)
        # AI 추정 쉼터는 공식 쉼터보다 약하게 — 눈에는 띄되 먼저 읽히지는 않게
        guess = place.ai_guess

        if b is None or self._zoom < 14.5:
            # 건물 데이터가 없거나 줌아웃 상태 → 원형 하이라이트
            r = max(13.0, min(34.0, 26.0 / max(self.meters_per_pixel(), 0.05)))
            r = max(13.0, min(40.0, r))
            p.setPen(QPen(QColor(0, 0, 0, 120), 4.0))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(center, r, r)
            for w, alpha in ((13, 26), (8, 38), (4, 58)):
                pen = QPen(QColor(color.red(), color.green(), color.blue(),
                                  int(alpha * (0.55 if guess else 1.0))))
                pen.setWidthF(w)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(center, r, r)
            fill = QColor(color)
            fill.setAlpha(34 if guess else 66)
            p.setBrush(fill)
            p.setPen(self._outline_pen(color, 2.4 if selected else 1.9, guess))
            p.drawEllipse(center, r, r)
            return QPointF(center.x(), center.y() - r)

        poly = QPolygonF([self.to_screen(la, lo) for la, lo in b["poly"]])
        rect = poly.boundingRect()
        pulse = (math.sin(self._phase * 1.6) * 0.5 + 0.5) if selected else 0.5
        strength = (1.0 if (selected or hovered) else 0.72) * (0.55 if guess else 1.0)

        # 지도 위 어디서든 도형이 분리돼 보이도록 어두운 테두리를 먼저 깐다
        shade = QPen(QColor(0, 0, 0, 120))
        shade.setWidthF(4.5)
        shade.setJoinStyle(Qt.RoundJoin)
        p.setPen(shade)
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(poly)

        for w, alpha in ((14, 22), (9, 34), (5, 54)):
            pen = QPen(QColor(color.red(), color.green(), color.blue(),
                              int(alpha * strength)))
            pen.setWidthF(w)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(poly)

        fill = QColor(color)
        if guess:
            fill.setAlpha(int(40 + 16 * pulse) if selected else 30)
        else:
            fill.setAlpha(int(74 + 28 * pulse) if selected else 60)
        p.setBrush(fill)
        p.setPen(self._outline_pen(color, 2.6 if selected else 2.0, guess))
        p.drawPolygon(poly)

        if selected and rect.width() > 24:
            pen = QPen(QColor(pal.accent_bright))
            pen.setWidthF(2.4)
            p.setPen(pen)
            arm = min(15.0, rect.width() * 0.3)
            for cx, cy, sx, sy in (
                (rect.left(), rect.top(), 1, 1), (rect.right(), rect.top(), -1, 1),
                (rect.left(), rect.bottom(), 1, -1), (rect.right(), rect.bottom(), -1, -1),
            ):
                p.drawLine(QPointF(cx, cy), QPointF(cx + arm * sx, cy))
                p.drawLine(QPointF(cx, cy), QPointF(cx, cy + arm * sy))

        return QPointF(rect.center().x(), rect.top())

    def _draw_arrow_marker(self, p: QPainter, pal: Palette, place: Place,
                           a: Analysis, selected: bool, hovered: bool) -> QPointF:
        """상가 내부 업소 — 정확한 지점을 화살표로 지시."""
        color = self._accent_for(pal, a)
        target = self.to_screen(place.lat, place.lon)

        seed = sum(ord(c) for c in place.id)
        angle = math.radians(214 + (seed % 4) * 33)
        dist = 76 + (seed % 3) * 10
        bob = math.sin(self._phase * 2.0 + seed) * 3.0 if (selected or hovered) else 0.0
        tail = QPointF(target.x() + math.cos(angle) * (dist + bob),
                       target.y() + math.sin(angle) * (dist + bob))

        b = self._building_for(place)
        if b is not None and self._zoom >= 14.5:
            poly = QPolygonF([self.to_screen(la, lo) for la, lo in b["poly"]])
            pen = QPen(QColor(color.red(), color.green(), color.blue(), 95))
            pen.setWidthF(1.5)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(QColor(color.red(), color.green(), color.blue(),
                              40 if selected else 26))
            p.drawPolygon(poly)

        path = QPainterPath(tail)
        mid = QPointF((tail.x() + target.x()) / 2, (tail.y() + target.y()) / 2)
        normal = QPointF(-(target.y() - tail.y()), target.x() - tail.x())
        length = math.hypot(normal.x(), normal.y()) or 1.0
        ctrl = QPointF(mid.x() + normal.x() / length * 16,
                       mid.y() + normal.y() / length * 16)
        path.quadTo(ctrl, target)

        shade = QPen(QColor(0, 0, 0, 130))
        shade.setWidthF(6.0)
        shade.setCapStyle(Qt.RoundCap)
        p.setPen(shade)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        glow = QPen(QColor(color.red(), color.green(), color.blue(), 70))
        glow.setWidthF(7.0)
        glow.setCapStyle(Qt.RoundCap)
        p.setPen(glow)
        p.drawPath(path)

        pen = self._outline_pen(color, 2.4 if selected else 2.0, place.ai_guess)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawPath(path)

        head_angle = math.atan2(target.y() - ctrl.y(), target.x() - ctrl.x())
        size = 13.0 if selected else 11.0
        left = QPointF(target.x() - math.cos(head_angle - 0.42) * size,
                       target.y() - math.sin(head_angle - 0.42) * size)
        right = QPointF(target.x() - math.cos(head_angle + 0.42) * size,
                        target.y() - math.sin(head_angle + 0.42) * size)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPolygon(QPolygonF([target, left, right]))

        ring = QPen(QColor(color.red(), color.green(), color.blue(), 150))
        ring.setWidthF(1.4)
        p.setPen(ring)
        p.setBrush(Qt.NoBrush)
        r = 8 + (math.sin(self._phase * 2.2) + 1) * 3 if selected else 8
        p.drawEllipse(target, r, r)

        if place.floor_hint:
            fm = QFontMetrics(mono(9, QFont.Bold))
            w = fm.horizontalAdvance(place.floor_hint) + 14
            badge = QRectF(target.x() + 12, target.y() - 9, w, 18)
            p.setBrush(color)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(badge, 9, 9)
            p.setPen(QColor(pal.accent_ink) if a.crowd.open_now else QColor(pal.bg))
            p.setFont(mono(9, QFont.Bold))
            p.drawText(badge, Qt.AlignCenter, place.floor_hint)

        self._hit_zones.append((QRectF(target.x() - 14, target.y() - 14, 28, 28), place.id))
        return tail

    def _draw_label(self, p: QPainter, pal: Palette, place: Place, a: Analysis,
                    anchor: QPointF, taken: list[QRectF],
                    selected: bool, hovered: bool) -> None:
        name_font = ui_font(11, QFont.Bold)
        meta_font = mono(9, QFont.DemiBold, 0.8)
        fm = QFontMetrics(name_font)
        fm2 = QFontMetrics(meta_font)

        meta = (f"{a.indoor:.0f}°C · 민폐도 {a.nuisance.score}"
                if a.crowd.open_now else "운영 종료")
        if place.ai_guess:
            # 공식 쉼터가 아니라는 사실이 라벨만 보고도 드러나야 한다
            meta = f"AI 추정 · {meta}"
        w = max(fm.horizontalAdvance(place.name), fm2.horizontalAdvance(meta)) + 44
        h = 40
        rect = QRectF(anchor.x() - w / 2, anchor.y() - h - 14, w, h)
        rect.moveLeft(max(6.0, min(rect.left(), self.width() - w - 6)))
        rect.moveTop(max(6.0, rect.top()))

        if not (selected or hovered):
            for t in taken:
                if rect.intersects(t.adjusted(-4, -4, 4, 4)):
                    self._hit_zones.append(
                        (QRectF(anchor.x() - 14, anchor.y() - 14, 28, 28), place.id))
                    self._draw_mini_dot(p, pal, a, anchor)
                    return
        taken.append(rect)

        color = self._accent_for(pal, a)
        # 지도 위에 얹히므로 살짝 그림자를 깔아 띄운다
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawRoundedRect(rect.adjusted(1.5, 2.0, 1.5, 2.5), 10, 10)

        bg = QColor(pal.panel)
        bg.setAlpha(252)
        p.setBrush(bg)
        pen = self._outline_pen(color if (selected or hovered) else QColor(pal.border),
                                1.8 if selected else 1.3, place.ai_guess)
        p.setPen(pen)
        p.drawRoundedRect(rect, 10, 10)

        leader_a = QPointF(rect.center().x(), rect.bottom())
        leader_b = QPointF(anchor.x(), anchor.y() - 3)
        p.setPen(QPen(QColor(0, 0, 0, 110), 3.0))
        p.drawLine(leader_a, leader_b)
        pen = QPen(QColor(color.red(), color.green(), color.blue(), 190))
        pen.setWidthF(1.5)
        p.setPen(pen)
        p.drawLine(leader_a, leader_b)

        icons.draw_icon(p, place.icon,
                        QRectF(rect.left() + 9, rect.top() + 11, 15, 15), color, 2.0)

        p.setFont(name_font)
        p.setPen(QColor(pal.text))
        p.drawText(QRectF(rect.left() + 30, rect.top() + 5, rect.width() - 36, 17),
                   Qt.AlignVCenter | Qt.AlignLeft, place.name)
        p.setFont(meta_font)
        p.setPen(QColor(pal.text_dim))
        p.drawText(QRectF(rect.left() + 30, rect.top() + 21, rect.width() - 36, 14),
                   Qt.AlignVCenter | Qt.AlignLeft, meta)

        p.setPen(Qt.NoPen)
        p.setBrush(crowd_color(pal, a.nuisance.key))
        p.drawEllipse(QPointF(rect.right() - 12, rect.top() + 13), 3.6, 3.6)
        if a.crowd.by_event:
            p.setBrush(QColor(pal.warn))
            p.drawEllipse(QPointF(rect.right() - 12, rect.top() + 26), 3.0, 3.0)

        self._hit_zones.append((rect, place.id))

    def _draw_mini_dot(self, p: QPainter, pal: Palette, a: Analysis, anchor: QPointF) -> None:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawEllipse(anchor, 7.5, 7.5)
        accent = self._accent_for(pal, a)
        if a.place.ai_guess:
            # 속을 비워 공식 쉼터의 채운 점과 구분한다
            p.setPen(QPen(accent, 2.0))
            p.setBrush(QColor(pal.bg))
        else:
            p.setPen(QPen(QColor(pal.bg), 2))
            p.setBrush(accent)
        p.drawEllipse(anchor, 5.5, 5.5)

    def _draw_user(self, p: QPainter, pal: Palette) -> None:
        pos = self.to_screen(*self.state.origin)
        accent = QColor(pal.accent_bright)

        if self.state.get("animations"):
            radius = 46 + (self._phase * 26) % 92
            alpha = int(max(0, 90 - (radius - 46) * 0.95))
            pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), alpha))
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(pos, radius, radius)

        grad = QRadialGradient(pos, 34)
        c = QColor(accent)
        c.setAlpha(70)
        grad.setColorAt(0.0, c)
        c2 = QColor(accent)
        c2.setAlpha(0)
        grad.setColorAt(1.0, c2)
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawEllipse(pos, 34, 34)

        p.setBrush(accent)
        p.setPen(QPen(QColor(pal.map_bg), 3))
        p.drawEllipse(pos, 7.5, 7.5)

        if not self.compact:
            p.setFont(mono(9, QFont.DemiBold))
            p.setPen(QColor(pal.text_dim))
            p.drawText(QRectF(pos.x() - 60, pos.y() + 12, 120, 16),
                       Qt.AlignCenter, "현재 위치")

    def _draw_overlay(self, p: QPainter, pal: Palette) -> None:
        """축척 · 저작자 표시 · 오프라인 안내."""
        # 저작자 표시는 OSM 이용 조건상 필수
        p.setFont(mono(8, QFont.Normal, 0.3))
        attr = self.tiles.attribution
        fm = QFontMetrics(mono(8, QFont.Normal, 0.3))
        tw = fm.horizontalAdvance(attr) + 12
        # 미리보기(compact)에서는 하단에 버튼/설명이 있으므로 우측 상단에 표시
        box = (QRectF(self.width() - tw - 6, 6, tw, 15) if self.compact
               else QRectF(self.width() - tw - 6, self.height() - 20, tw, 15))
        bg = QColor(pal.bg)
        bg.setAlpha(170)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(box, 3, 3)
        p.setPen(QColor(pal.text_mute))
        p.drawText(box, Qt.AlignCenter, attr)

        if self.compact:
            return

        # 축척
        mpp = self.meters_per_pixel()
        if mpp <= 0:
            return
        target_px = 110
        meters = target_px * mpp
        nice = 10 ** math.floor(math.log10(max(meters, 1)))
        for m in (1, 2, 5, 10):
            if nice * m >= meters:
                nice *= m
                break
        width = nice / mpp
        x0, y0 = 18, self.height() - 22
        pen = QPen(QColor(pal.text_dim))
        pen.setWidthF(1.6)
        p.setPen(pen)
        p.drawLine(QPointF(x0, y0), QPointF(x0 + width, y0))
        p.drawLine(QPointF(x0, y0 - 4), QPointF(x0, y0 + 4))
        p.drawLine(QPointF(x0 + width, y0 - 4), QPointF(x0 + width, y0 + 4))
        p.setFont(mono(9))
        label = f"{int(nice)}m" if nice < 1000 else f"{nice / 1000:.0f}km"
        p.drawText(QRectF(x0, y0 - 22, width, 16), Qt.AlignCenter, label)

        if self.tiles.offline:
            p.setFont(mono(10, QFont.DemiBold))
            p.setPen(QColor(pal.warn))
            p.drawText(QRectF(0, 12, self.width(), 18), Qt.AlignCenter,
                       "지도 타일을 불러올 수 없습니다 (오프라인)")
