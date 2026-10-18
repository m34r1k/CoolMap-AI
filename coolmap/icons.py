"""24x24 좌표계 위에 직접 그리는 벡터 아이콘 모음 (외부 리소스 없음)."""

from __future__ import annotations

import math
from typing import Callable, Dict

from PySide6.QtCore import QPointF, QRectF, Qt, QSize
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
)

Drawer = Callable[[QPainter], None]
_REGISTRY: Dict[str, Drawer] = {}


def _reg(name: str):
    def deco(fn: Drawer) -> Drawer:
        _REGISTRY[name] = fn
        return fn

    return deco


def _path(*points, close: bool = False) -> QPainterPath:
    path = QPainterPath(QPointF(points[0][0], points[0][1]))
    for x, y in points[1:]:
        path.lineTo(x, y)
    if close:
        path.closeSubpath()
    return path


def _stroke(p: QPainter, path: QPainterPath) -> None:
    p.strokePath(path, p.pen())


def _fill(p: QPainter, path: QPainterPath) -> None:
    p.fillPath(path, p.pen().color())


# --------------------------------------------------------------------------
# 내비게이션
# --------------------------------------------------------------------------
@_reg("home")
def _home(p: QPainter) -> None:
    _stroke(p, _path((3.5, 10.5), (12, 3.5), (20.5, 10.5)))
    _stroke(p, _path((5.5, 9.5), (5.5, 20), (18.5, 20), (18.5, 9.5)))
    _stroke(p, _path((9.8, 20), (9.8, 14), (14.2, 14), (14.2, 20)))


@_reg("chat")
def _chat(p: QPainter) -> None:
    """물어보기 — 물음표가 든 말풍선."""
    bubble = QPainterPath()
    bubble.addRoundedRect(3, 4, 18, 13, 4.5, 4.5)
    _stroke(p, bubble)
    _stroke(p, _path((8, 17), (7, 21), (12, 17)))
    q = QPainterPath(QPointF(9.8, 8.6))
    q.cubicTo(9.8, 6.6, 14.2, 6.6, 14.2, 8.6)
    q.cubicTo(14.2, 10.2, 12, 10.2, 12, 12)
    _stroke(p, q)
    dot = QPainterPath()
    dot.addEllipse(QPointF(12, 14.4), 0.95, 0.95)
    _fill(p, dot)


@_reg("siren")
def _siren(p: QPainter) -> None:
    """쉼터 제보 — 경광등 (둥근 몸통 · 받침 · 빛줄기)."""
    dome = QPainterPath(QPointF(6.5, 18))
    dome.lineTo(6.5, 13.5)
    dome.cubicTo(6.5, 10.2, 9, 8, 12, 8)
    dome.cubicTo(15, 8, 17.5, 10.2, 17.5, 13.5)
    dome.lineTo(17.5, 18)
    _stroke(p, dome)
    _stroke(p, _path((4.5, 20.5), (19.5, 20.5)))
    _stroke(p, _path((4.5, 18), (19.5, 18)))
    _stroke(p, _path((12, 2.5), (12, 4.8)))
    _stroke(p, _path((4.2, 5.6), (5.8, 7.2)))
    _stroke(p, _path((19.8, 5.6), (18.2, 7.2)))


@_reg("map")
def _map(p: QPainter) -> None:
    _stroke(p, _path((2.5, 6.5), (9, 4), (15, 7), (21.5, 4.5), (21.5, 17.5),
                     (15, 20), (9, 17), (2.5, 19.5), close=True))
    _stroke(p, _path((9, 4), (9, 17)))
    _stroke(p, _path((15, 7), (15, 20)))


@_reg("heart")
def _heart(p: QPainter) -> None:
    path = QPainterPath(QPointF(12, 20.3))
    path.cubicTo(3.5, 14.8, 2.2, 10.6, 4.6, 7.6)
    path.cubicTo(7.0, 4.6, 10.6, 5.4, 12, 8.3)
    path.cubicTo(13.4, 5.4, 17.0, 4.6, 19.4, 7.6)
    path.cubicTo(21.8, 10.6, 20.5, 14.8, 12, 20.3)
    _stroke(p, path)


@_reg("heart_fill")
def _heart_fill(p: QPainter) -> None:
    path = QPainterPath(QPointF(12, 20.3))
    path.cubicTo(3.5, 14.8, 2.2, 10.6, 4.6, 7.6)
    path.cubicTo(7.0, 4.6, 10.6, 5.4, 12, 8.3)
    path.cubicTo(13.4, 5.4, 17.0, 4.6, 19.4, 7.6)
    path.cubicTo(21.8, 10.6, 20.5, 14.8, 12, 20.3)
    _fill(p, path)


@_reg("sparkle")
def _sparkle(p: QPainter) -> None:
    def star(cx, cy, r, inner):
        path = QPainterPath(QPointF(cx, cy - r))
        path.quadTo(cx + inner, cy - inner, cx + r, cy)
        path.quadTo(cx + inner, cy + inner, cx, cy + r)
        path.quadTo(cx - inner, cy + inner, cx - r, cy)
        path.quadTo(cx - inner, cy - inner, cx, cy - r)
        return path

    _fill(p, star(10, 11, 7.5, 1.6))
    _fill(p, star(18.5, 5.5, 3.4, 0.7))


@_reg("gear")
def _gear(p: QPainter) -> None:
    path = QPainterPath()
    r_out, r_in, teeth = 9.4, 7.4, 8
    for i in range(teeth * 2):
        ang = math.pi * i / teeth
        r = r_out if i % 2 == 0 else r_in
        x, y = 12 + r * math.cos(ang), 12 + r * math.sin(ang)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    _stroke(p, path)
    circle = QPainterPath()
    circle.addEllipse(QPointF(12, 12), 3.2, 3.2)
    _stroke(p, circle)


# --------------------------------------------------------------------------
# 모드
# --------------------------------------------------------------------------
@_reg("snow")
def _snow(p: QPainter) -> None:
    for k in range(3):
        ang = math.pi * k / 3
        dx, dy = math.cos(ang) * 8.6, math.sin(ang) * 8.6
        _stroke(p, _path((12 - dx, 12 - dy), (12 + dx, 12 + dy)))
        for sign in (-1, 1):
            ex, ey = 12 + dx * sign, 12 + dy * sign
            for off in (0.62, -0.62):
                bang = ang + math.pi + off if sign > 0 else ang + off
                _stroke(p, _path((ex, ey),
                                 (ex + math.cos(bang) * 3.2, ey + math.sin(bang) * 3.2)))


@_reg("flame")
def _flame(p: QPainter) -> None:
    outer = QPainterPath(QPointF(12, 2.6))
    outer.cubicTo(16.6, 7.2, 19.4, 9.6, 19.4, 13.6)
    outer.cubicTo(19.4, 17.8, 16.1, 21.2, 12, 21.2)
    outer.cubicTo(7.9, 21.2, 4.6, 17.8, 4.6, 13.6)
    outer.cubicTo(4.6, 10.4, 6.4, 8.4, 8.6, 5.8)
    outer.cubicTo(9.4, 8.2, 10.4, 9.4, 11.4, 10.0)
    outer.cubicTo(11.1, 6.9, 11.2, 4.8, 12, 2.6)
    _stroke(p, outer)
    inner = QPainterPath(QPointF(12, 21.2))
    inner.cubicTo(9.4, 21.2, 8.0, 19.3, 8.0, 17.3)
    inner.cubicTo(8.0, 15.0, 10.2, 14.2, 11.6, 11.6)
    inner.cubicTo(13.6, 14.4, 16.0, 15.2, 16.0, 17.3)
    inner.cubicTo(16.0, 19.3, 14.6, 21.2, 12, 21.2)
    _stroke(p, inner)


@_reg("thermo")
def _thermo(p: QPainter) -> None:
    path = QPainterPath(QPointF(9.6, 14.2))
    path.lineTo(9.6, 5.6)
    path.arcTo(QRectF(9.6, 3.2, 4.8, 4.8), 180, -180)
    path.lineTo(14.4, 14.2)
    _stroke(p, path)
    circle = QPainterPath()
    circle.addEllipse(QPointF(12, 17.4), 3.9, 3.9)
    _stroke(p, circle)
    _stroke(p, _path((12, 8.4), (12, 15.4)))


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
@_reg("search")
def _search(p: QPainter) -> None:
    circle = QPainterPath()
    circle.addEllipse(QPointF(10.6, 10.6), 6.4, 6.4)
    _stroke(p, circle)
    _stroke(p, _path((15.4, 15.4), (20.5, 20.5)))


@_reg("filter")
def _filter(p: QPainter) -> None:
    _stroke(p, _path((3.5, 6.5), (20.5, 6.5)))
    _stroke(p, _path((6.5, 12), (17.5, 12)))
    _stroke(p, _path((9.5, 17.5), (14.5, 17.5)))


@_reg("user")
def _user(p: QPainter) -> None:
    circle = QPainterPath()
    circle.addEllipse(QPointF(12, 8.4), 4.1, 4.1)
    _stroke(p, circle)
    arc = QPainterPath()
    arc.arcMoveTo(QRectF(4, 13.4, 16, 14), 200)
    arc.arcTo(QRectF(4, 13.4, 16, 14), 200, 140)
    _stroke(p, arc)


@_reg("users")
def _users(p: QPainter) -> None:
    c1 = QPainterPath()
    c1.addEllipse(QPointF(9.4, 8.6), 3.4, 3.4)
    _stroke(p, c1)
    arc = QPainterPath()
    arc.arcMoveTo(QRectF(2.6, 13.2, 13.6, 12), 200)
    arc.arcTo(QRectF(2.6, 13.2, 13.6, 12), 200, 140)
    _stroke(p, arc)
    c2 = QPainterPath()
    c2.addEllipse(QPointF(17.4, 9.6), 2.6, 2.6)
    _stroke(p, c2)
    arc2 = QPainterPath()
    arc2.arcMoveTo(QRectF(13.4, 13.6, 9.6, 9), 60)
    arc2.arcTo(QRectF(13.4, 13.6, 9.6, 9), 60, 60)
    _stroke(p, arc2)


@_reg("target")
def _target(p: QPainter) -> None:
    for r in (8.4, 3.4):
        c = QPainterPath()
        c.addEllipse(QPointF(12, 12), r, r)
        _stroke(p, c)
    for a, b in (((12, 1.4), (12, 5.2)), ((12, 18.8), (12, 22.6)),
                 ((1.4, 12), (5.2, 12)), ((18.8, 12), (22.6, 12))):
        _stroke(p, _path(a, b))


@_reg("send")
def _send(p: QPainter) -> None:
    _fill(p, _path((3.2, 11.6), (20.8, 4.2), (13.6, 20.6), (11.2, 13.4), close=True))


@_reg("chevron_right")
def _chev_r(p: QPainter) -> None:
    _stroke(p, _path((9.5, 5), (16.5, 12), (9.5, 19)))


@_reg("chevron_left")
def _chev_l(p: QPainter) -> None:
    _stroke(p, _path((14.5, 5), (7.5, 12), (14.5, 19)))


@_reg("arrow_right")
def _arr_r(p: QPainter) -> None:
    _stroke(p, _path((4, 12), (19.5, 12)))
    _stroke(p, _path((13.5, 6), (19.5, 12), (13.5, 18)))


@_reg("arrow_left")
def _arr_l(p: QPainter) -> None:
    _stroke(p, _path((20, 12), (4.5, 12)))
    _stroke(p, _path((10.5, 6), (4.5, 12), (10.5, 18)))


@_reg("share")
def _share(p: QPainter) -> None:
    for cx, cy in ((17.6, 5.6), (17.6, 18.4), (6.4, 12)):
        c = QPainterPath()
        c.addEllipse(QPointF(cx, cy), 2.7, 2.7)
        _stroke(p, c)
    _stroke(p, _path((8.8, 10.8), (15.2, 6.8)))
    _stroke(p, _path((8.8, 13.2), (15.2, 17.2)))


@_reg("clock")
def _clock(p: QPainter) -> None:
    c = QPainterPath()
    c.addEllipse(QPointF(12, 12), 8.6, 8.6)
    _stroke(p, c)
    _stroke(p, _path((12, 6.8), (12, 12.4), (16, 14.4)))


@_reg("walk")
def _walk(p: QPainter) -> None:
    head = QPainterPath()
    head.addEllipse(QPointF(13, 4.4), 2.1, 2.1)
    _stroke(p, head)
    _stroke(p, _path((13.4, 8), (11.2, 13.4), (14.6, 15.4), (15.6, 20.6)))
    _stroke(p, _path((11.2, 13.4), (8.4, 20.6)))
    _stroke(p, _path((13.2, 9.4), (17.4, 11.4)))
    _stroke(p, _path((12.4, 9.6), (8.2, 10.6)))


@_reg("pin")
def _pin(p: QPainter) -> None:
    path = QPainterPath(QPointF(12, 21.4))
    path.cubicTo(6.2, 14.6, 4.6, 12.2, 4.6, 9.6)
    path.cubicTo(4.6, 5.5, 7.9, 2.6, 12, 2.6)
    path.cubicTo(16.1, 2.6, 19.4, 5.5, 19.4, 9.6)
    path.cubicTo(19.4, 12.2, 17.8, 14.6, 12, 21.4)
    _stroke(p, path)
    c = QPainterPath()
    c.addEllipse(QPointF(12, 9.5), 2.8, 2.8)
    _stroke(p, c)


@_reg("droplet")
def _droplet(p: QPainter) -> None:
    path = QPainterPath(QPointF(12, 2.8))
    path.cubicTo(16.8, 8.4, 19, 11.2, 19, 14.4)
    path.cubicTo(19, 18.3, 15.9, 21.2, 12, 21.2)
    path.cubicTo(8.1, 21.2, 5, 18.3, 5, 14.4)
    path.cubicTo(5, 11.2, 7.2, 8.4, 12, 2.8)
    _stroke(p, path)


@_reg("wind")
def _wind(p: QPainter) -> None:
    a = QPainterPath(QPointF(3, 8.4))
    a.lineTo(12.6, 8.4)
    a.arcTo(QRectF(11.2, 4.2, 4.6, 4.6), 270, 250)
    _stroke(p, a)
    b = QPainterPath(QPointF(3, 13))
    b.lineTo(16.4, 13)
    b.arcTo(QRectF(15, 8.8, 4.6, 4.6), 270, 250)
    _stroke(p, b)
    c = QPainterPath(QPointF(4.6, 17.6))
    c.lineTo(12.2, 17.6)
    c.arcTo(QRectF(10.8, 15.4, 4.2, 4.2), 270, 250)
    _stroke(p, c)


@_reg("star")
def _star(p: QPainter) -> None:
    path = QPainterPath()
    for i in range(10):
        ang = -math.pi / 2 + math.pi * i / 5
        r = 9.2 if i % 2 == 0 else 4.0
        x, y = 12 + r * math.cos(ang), 12 + r * math.sin(ang)
        path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
    path.closeSubpath()
    _fill(p, path)


@_reg("bulb")
def _bulb(p: QPainter) -> None:
    c = QPainterPath()
    c.addEllipse(QPointF(12, 9.6), 5.8, 5.8)
    _stroke(p, c)
    _stroke(p, _path((9.4, 14.4), (9.4, 18), (14.6, 18), (14.6, 14.4)))
    _stroke(p, _path((10, 20.6), (14, 20.6)))


@_reg("check")
def _check(p: QPainter) -> None:
    _stroke(p, _path((5, 12.6), (10, 17.4), (19, 6.8)))


@_reg("check_circle")
def _check_circle(p: QPainter) -> None:
    c = QPainterPath()
    c.addEllipse(QPointF(12, 12), 8.8, 8.8)
    _stroke(p, c)
    _stroke(p, _path((7.8, 12.2), (10.8, 15.2), (16.2, 8.8)))


@_reg("info")
def _info(p: QPainter) -> None:
    c = QPainterPath()
    c.addEllipse(QPointF(12, 12), 8.8, 8.8)
    _stroke(p, c)
    _stroke(p, _path((12, 11), (12, 16.4)))
    dot = QPainterPath()
    dot.addEllipse(QPointF(12, 7.8), 0.95, 0.95)
    _fill(p, dot)


@_reg("alert")
def _alert(p: QPainter) -> None:
    _stroke(p, _path((12, 3.2), (21.6, 20.2), (2.4, 20.2), close=True))
    _stroke(p, _path((12, 9.4), (12, 14.6)))
    dot = QPainterPath()
    dot.addEllipse(QPointF(12, 17.4), 0.95, 0.95)
    _fill(p, dot)


@_reg("plus")
def _plus(p: QPainter) -> None:
    _stroke(p, _path((12, 5), (12, 19)))
    _stroke(p, _path((5, 12), (19, 12)))


@_reg("minus")
def _minus(p: QPainter) -> None:
    _stroke(p, _path((5, 12), (19, 12)))


@_reg("close")
def _close(p: QPainter) -> None:
    _stroke(p, _path((6, 6), (18, 18)))
    _stroke(p, _path((18, 6), (6, 18)))


@_reg("layers")
def _layers(p: QPainter) -> None:
    _stroke(p, _path((12, 3.4), (21, 8.2), (12, 13), (3, 8.2), close=True))
    _stroke(p, _path((3, 12.4), (12, 17.2), (21, 12.4)))
    _stroke(p, _path((3, 16.2), (12, 21), (21, 16.2)))


@_reg("refresh")
def _refresh(p: QPainter) -> None:
    arc = QPainterPath()
    arc.arcMoveTo(QRectF(3.6, 3.6, 16.8, 16.8), 60)
    arc.arcTo(QRectF(3.6, 3.6, 16.8, 16.8), 60, 280)
    _stroke(p, arc)
    _stroke(p, _path((16.4, 2.4), (17.4, 7.4), (12.4, 7.6)))


# --------------------------------------------------------------------------
# 장소 카테고리
# --------------------------------------------------------------------------
@_reg("book")
def _book(p: QPainter) -> None:
    _stroke(p, _path((4, 4.6), (10.4, 6.2), (10.4, 20), (4, 18.4), close=True))
    _stroke(p, _path((20, 4.6), (13.6, 6.2), (13.6, 20), (20, 18.4), close=True))
    _stroke(p, _path((10.4, 6.2), (13.6, 6.2)))


@_reg("bag")
def _bag(p: QPainter) -> None:
    _stroke(p, _path((5, 7.6), (19, 7.6), (20.2, 20.6), (3.8, 20.6), close=True))
    arc = QPainterPath()
    arc.arcMoveTo(QRectF(8.2, 2.6, 7.6, 8), 0)
    arc.arcTo(QRectF(8.2, 2.6, 7.6, 8), 0, 180)
    _stroke(p, arc)


@_reg("train")
def _train(p: QPainter) -> None:
    _stroke(p, _path((5.4, 3.6), (18.6, 3.6), (18.6, 17.4), (5.4, 17.4), close=True))
    _stroke(p, _path((5.4, 10.4), (18.6, 10.4)))
    _stroke(p, _path((7.6, 20.4), (5.4, 17.4)))
    _stroke(p, _path((16.4, 20.4), (18.6, 17.4)))
    for cx in (9.2, 14.8):
        d = QPainterPath()
        d.addEllipse(QPointF(cx, 14), 1.0, 1.0)
        _fill(p, d)


@_reg("bus")
def _bus(p: QPainter) -> None:
    _stroke(p, _path((4.6, 4.4), (19.4, 4.4), (19.4, 16.6), (4.6, 16.6), close=True))
    _stroke(p, _path((4.6, 10.2), (19.4, 10.2)))
    _stroke(p, _path((3.2, 7.6), (3.2, 11.4)))
    _stroke(p, _path((20.8, 7.6), (20.8, 11.4)))
    for cx in (8.2, 15.8):
        c = QPainterPath()
        c.addEllipse(QPointF(cx, 18.4), 1.8, 1.8)
        _stroke(p, c)
    for cx in (8.0, 16.0):
        d = QPainterPath()
        d.addEllipse(QPointF(cx, 13.4), 0.95, 0.95)
        _fill(p, d)


@_reg("cart")
def _cart(p: QPainter) -> None:
    _stroke(p, _path((2.6, 3.6), (5.4, 3.6), (7.8, 14.6), (18.6, 14.6)))
    _stroke(p, _path((6.4, 6.6), (21.0, 6.6), (19.4, 12.4), (7.6, 12.4)))
    for cx in (9.4, 17.4):
        c = QPainterPath()
        c.addEllipse(QPointF(cx, 18.6), 1.7, 1.7)
        _stroke(p, c)


@_reg("building")
def _building(p: QPainter) -> None:
    _stroke(p, _path((4.4, 20.6), (4.4, 6.4), (12.6, 3.4), (12.6, 20.6)))
    _stroke(p, _path((12.6, 9.6), (19.6, 9.6), (19.6, 20.6)))
    _stroke(p, _path((2.6, 20.6), (21.4, 20.6)))
    for y in (9.0, 12.4, 15.8):
        _stroke(p, _path((7.0, y), (10.0, y)))
    for y in (13.4, 16.8):
        _stroke(p, _path((15.2, y), (17.6, y)))


@_reg("cup")
def _cup(p: QPainter) -> None:
    _stroke(p, _path((4.6, 7.4), (16.4, 7.4), (15.2, 18.6), (5.8, 18.6), close=True))
    arc = QPainterPath()
    arc.arcMoveTo(QRectF(15.4, 8.4, 5.6, 6.4), 90)
    arc.arcTo(QRectF(15.4, 8.4, 5.6, 6.4), 90, -180)
    _stroke(p, arc)
    _stroke(p, _path((4.0, 21.4), (17.0, 21.4)))


@_reg("film")
def _film(p: QPainter) -> None:
    _stroke(p, _path((3.4, 5.4), (20.6, 5.4), (20.6, 18.6), (3.4, 18.6), close=True))
    _stroke(p, _path((8.2, 5.4), (8.2, 18.6)))
    _stroke(p, _path((15.8, 5.4), (15.8, 18.6)))
    for y in (8.4, 12, 15.6):
        _stroke(p, _path((3.4, y), (8.2, y)))
        _stroke(p, _path((15.8, y), (20.6, y)))


@_reg("tree")
def _tree(p: QPainter) -> None:
    _stroke(p, _path((12, 2.6), (18.4, 11.4), (5.6, 11.4), close=True))
    _stroke(p, _path((12, 7.4), (19.4, 16.6), (4.6, 16.6), close=True))
    _stroke(p, _path((12, 16.6), (12, 21.4)))


@_reg("bank")
def _bank(p: QPainter) -> None:
    _stroke(p, _path((2.8, 9.4), (12, 3.6), (21.2, 9.4)))
    _stroke(p, _path((2.8, 20.6), (21.2, 20.6)))
    for x in (6.6, 12, 17.4):
        _stroke(p, _path((x, 11.4), (x, 18.2)))


@_reg("market")
def _market(p: QPainter) -> None:
    _stroke(p, _path((3.2, 9.4), (20.8, 9.4), (19.4, 20.6), (4.6, 20.6), close=True))
    _stroke(p, _path((3.2, 9.4), (5.8, 3.6), (18.2, 3.6), (20.8, 9.4)))
    _stroke(p, _path((9.4, 9.4), (9.4, 14.2)))
    _stroke(p, _path((14.6, 9.4), (14.6, 14.2)))


@_reg("hospital")
def _hospital(p: QPainter) -> None:
    _stroke(p, _path((4.4, 6.4), (19.6, 6.4), (19.6, 20.6), (4.4, 20.6), close=True))
    _stroke(p, _path((12, 9.6), (12, 17.4)))
    _stroke(p, _path((8.1, 13.5), (15.9, 13.5)))
    _stroke(p, _path((7.2, 6.4), (7.2, 3.4), (16.8, 3.4), (16.8, 6.4)))


@_reg("gov")
def _gov(p: QPainter) -> None:
    _stroke(p, _path((3.4, 20.6), (20.6, 20.6)))
    _stroke(p, _path((5.2, 20.6), (5.2, 8.4), (18.8, 8.4), (18.8, 20.6)))
    _stroke(p, _path((3.6, 8.4), (12, 3.4), (20.4, 8.4)))
    _stroke(p, _path((10, 20.6), (10, 14.4), (14, 14.4), (14, 20.6)))


# --------------------------------------------------------------------------
# 하늘 (plain.sky_line 의 아이콘 이름 앞에 "w_" 를 붙여 쓴다)
# --------------------------------------------------------------------------
def _circle(cx: float, cy: float, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), r, r)
    return path


def _cloud(dx: float = 0.0, dy: float = 0.0, scale: float = 1.0) -> QPainterPath:
    """바닥이 평평한 구름 윤곽 (원 셋 + 몸통을 합친 것)."""
    body = QPainterPath()
    body.addRect(QRectF(7.5, 12.5, 9.5, 6.0))
    path = (_circle(7.5, 14.5, 4.0).united(_circle(12.5, 10.5, 5.2))
            .united(_circle(17.0, 14.7, 3.8)).united(body))
    t = QTransform()
    t.translate(dx, dy)
    t.scale(scale, scale)
    return t.map(path.simplified())


def _sun_rays(p: QPainter, cx: float, cy: float, r0: float, r1: float, angles) -> None:
    for deg in angles:
        a = math.radians(deg)
        _stroke(p, _path((cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                         (cx + math.cos(a) * r1, cy + math.sin(a) * r1)))


def _moon(cx: float, cy: float, r: float) -> QPainterPath:
    return _circle(cx, cy, r).subtracted(_circle(cx + r * 0.55, cy - r * 0.45, r * 0.85))


@_reg("w_sunny")
def _w_sunny(p: QPainter) -> None:
    _stroke(p, _circle(12, 12, 4.2))
    _sun_rays(p, 12, 12, 7.0, 9.6, range(0, 360, 45))


@_reg("w_night")
def _w_night(p: QPainter) -> None:
    _stroke(p, _moon(11.5, 12.5, 8.0))


@_reg("w_partly")
def _w_partly(p: QPainter) -> None:
    cloud = _cloud(4.2, 4.6, 0.82)
    _stroke(p, _circle(8.6, 8.6, 3.4).subtracted(cloud))
    _sun_rays(p, 8.6, 8.6, 5.4, 7.4, (135, 180, 225, 270, 315))
    _stroke(p, cloud)


@_reg("w_partly_night")
def _w_partly_night(p: QPainter) -> None:
    cloud = _cloud(4.2, 4.6, 0.82)
    _stroke(p, _moon(8.4, 8.4, 5.2).subtracted(cloud))
    _stroke(p, cloud)


@_reg("w_cloudy")
def _w_cloudy(p: QPainter) -> None:
    _stroke(p, _cloud(-0.2, 0.2))


def _sky_cloud(p: QPainter) -> None:
    """비·눈 아이콘의 위쪽 구름."""
    _stroke(p, _cloud(1.0, -3.4, 0.92))


@_reg("w_rain")
def _w_rain(p: QPainter) -> None:
    _sky_cloud(p)
    for x in (8.6, 12.6, 16.6):
        _stroke(p, _path((x, 16.6), (x - 1.6, 21.0)))


@_reg("w_snow")
def _w_snow(p: QPainter) -> None:
    _sky_cloud(p)
    for x, y in ((8.2, 18.0), (12.4, 20.4), (16.6, 18.0)):
        _fill(p, _circle(x, y, 1.15))


@_reg("w_sleet")
def _w_sleet(p: QPainter) -> None:
    _sky_cloud(p)
    _stroke(p, _path((9.0, 16.6), (7.4, 21.0)))
    _fill(p, _circle(12.6, 19.2, 1.15))
    _stroke(p, _path((17.0, 16.6), (15.4, 21.0)))


@_reg("umbrella")
def _umbrella(p: QPainter) -> None:
    top = QPainterPath(QPointF(3.2, 12))
    top.cubicTo(3.6, 6.8, 7.6, 3.6, 12, 3.6)
    top.cubicTo(16.4, 3.6, 20.4, 6.8, 20.8, 12)
    top.cubicTo(19.4, 10.8, 17.4, 10.8, 16.4, 12)
    top.cubicTo(15.2, 10.8, 13.2, 10.8, 12, 12)
    top.cubicTo(10.8, 10.8, 8.8, 10.8, 7.6, 12)
    top.cubicTo(6.6, 10.8, 4.6, 10.8, 3.2, 12)
    _stroke(p, top)
    handle = QPainterPath(QPointF(12, 12))
    handle.lineTo(12, 18.6)
    handle.arcTo(QRectF(8.4, 16.8, 3.6, 3.6), 0, -180)
    _stroke(p, handle)


# --------------------------------------------------------------------------
# 렌더링 API
# --------------------------------------------------------------------------
def has_icon(name: str) -> bool:
    return name in _REGISTRY


def draw_icon(
    painter: QPainter,
    name: str,
    rect: QRectF,
    color: QColor | str,
    weight: float = 1.85,
) -> None:
    """rect 안에 아이콘을 그린다 (24x24 좌표계를 rect 크기로 스케일)."""
    drawer = _REGISTRY.get(name) or _REGISTRY["pin"]
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.translate(rect.x(), rect.y())
    painter.scale(rect.width() / 24.0, rect.height() / 24.0)
    pen = QPen(QColor(color))
    pen.setWidthF(weight)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    drawer(painter)
    painter.restore()


_PIXMAPS: dict[tuple, QPixmap] = {}


def icon_pixmap(name: str, size: int, color: QColor | str, weight: float = 1.85) -> QPixmap:
    """아이콘 그림. 같은 (이름 · 크기 · 색 · 굵기) 는 한 번만 그린다 — 목록을 갱신할 때마다
    수백 개를 다시 그리던 비용을 없앤다. QPixmap 은 암묵적 공유라 돌려줘도 안전하다."""
    key = (name, size, QColor(color).rgba(), weight)
    pm = _PIXMAPS.get(key)
    if pm is None:
        if len(_PIXMAPS) > 2000:
            _PIXMAPS.clear()
        pm = _PIXMAPS[key] = _render_pixmap(name, size, color, weight)
    return pm


def _render_pixmap(name: str, size: int, color: QColor | str, weight: float) -> QPixmap:
    ratio = 2.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    draw_icon(painter, name, QRectF(0, 0, size, size), color, weight)
    painter.end()
    return pm


def qicon(name: str, size: int, color: QColor | str, weight: float = 1.85) -> QIcon:
    return QIcon(icon_pixmap(name, size, color, weight))


def icon_size(size: int) -> QSize:
    return QSize(size, size)
