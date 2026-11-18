"""Animated hand-drawn financial charts.

`draw_chart(spec, w, h, progress, boil)` returns an RGBA frame; `progress` in [0,1] animates the
reveal (lines draw left-to-right, bars grow, pie wedges sweep). compound_growth values are
computed exactly from the spec's params, so those charts are always numerically correct.
"""
from __future__ import annotations

import math

from PIL import Image

from ..models import ChartSpec
from .style import SERIES, Ink, c, font


def compound_series(principal: float, rate: float, years: float, monthly: float = 0.0):
    """Year-end balances with monthly compounding & contributions. Returns (years, balance, contributed)."""
    yrs, bal, contrib = [0], [principal], [principal]
    b, total = principal, principal
    for m in range(1, int(round(years * 12)) + 1):
        b = b * (1 + rate / 12) + monthly
        total += monthly
        if m % 12 == 0:
            yrs.append(m // 12)
            bal.append(b)
            contrib.append(total)
    return yrs, bal, contrib


def fmt_value(v: float, unit: str) -> str:
    if unit == "%":
        return f"{v:g}%"
    if unit == "$":
        if abs(v) >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if abs(v) >= 10_000:
            return f"${v / 1000:.0f}K"
        return f"${v:,.0f}"
    return f"{v:,.4g}"


def _ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _frame(ink: Ink, w, h, title, source, pad):
    ink.rect((10, 10, w - 10, h - 10), fill="white", width=6)
    size = 46
    while size > 26 and font(size).getlength(title) > w - 2 * pad:
        size -= 2
    ink.text((pad, 28 + (46 - size) // 2), title, size)
    if source:
        ink.text((w - pad, h - 30), f"Source: {source}", 26, color="grey", anchor="rb")


def _axes(ink: Ink, box, ymax, unit):
    x0, y0, x1, y1 = box
    ink.line([(x0, y0 - 10), (x0, y1)], width=5)
    ink.line([(x0, y1), (x1 + 10, y1)], width=5)
    for i in range(1, 5):
        y = y1 - (y1 - y0) * i / 4
        ink.line([(x0 + 4, y), (x1, y)], color="paper_dark", width=2, wobble=0.6)
        ink.text((x0 - 12, y), fmt_value(ymax * i / 4, unit), 26, color="grey", anchor="rm")


def _compound(ink: Ink, spec: ChartSpec, box, t):
    p = spec.params
    yrs, bal, contrib = compound_series(p.get("principal", 0), p.get("rate", 0.07), p.get("years", 30),
                                        p.get("monthly", 0))
    x0, y0, x1, y1 = box
    ymax = max(bal) * 1.1 or 1
    _axes(ink, box, ymax, "$")
    n = len(yrs) - 1 or 1
    k = _ease(t) * n

    def pt(i, v):
        return x0 + (x1 - x0) * i / n, y1 - (y1 - y0) * v / ymax

    idx = [i for i in range(len(yrs)) if i <= k] or [0]
    if len(idx) > 1:
        ink.poly([pt(i, contrib[i]) for i in idx] + [pt(idx[-1], 0), pt(0, 0)], fill="blue_light", outline=None)
        ink.poly([pt(i, bal[i]) for i in idx] + [pt(i, contrib[i]) for i in reversed(idx)], fill="green_light",
                 outline=None)
        ink.line([pt(i, bal[i]) for i in idx], color="green", width=9)
        ink.line([pt(i, contrib[i]) for i in idx], color="blue", width=6)
    last = idx[-1]
    lx, ly = pt(last, bal[last])
    ink.ellipse((lx - 12, ly - 12, lx + 12, ly + 12), fill="gold", width=4)
    ink.text((lx - 22, max(ly, y0 + 70)), fmt_value(bal[last], "$"), 40, color="green", anchor="rb")
    for i in range(0, len(yrs), max(1, n // 6)):
        ink.text((pt(i, 0)[0], y1 + 14), f"Yr {yrs[i]}", 26, color="grey", anchor="mt")
    ink.rect((x0 + 20, y0, x0 + 44, y0 + 24), fill="green_light", width=3)
    ink.text((x0 + 54, y0 + 12), "Growth", 28, anchor="lm")
    ink.rect((x0 + 190, y0, x0 + 214, y0 + 24), fill="blue_light", width=3)
    ink.text((x0 + 224, y0 + 12), "Money you put in", 28, anchor="lm")


def _bars(ink: Ink, spec: ChartSpec, box, t):
    x0, y0, x1, y1 = box
    vals = spec.values or [1]
    ymax = max(vals) * 1.15 or 1
    _axes(ink, box, ymax, spec.unit)
    n = len(vals)
    slot = (x1 - x0) / n
    for i, v in enumerate(vals):
        ti = _ease(t * 1.4 - i * 0.4 / max(1, n - 1)) if n > 1 else _ease(t)
        bh = (y1 - y0) * v / ymax * ti
        bx0, bx1 = x0 + slot * i + slot * 0.18, x0 + slot * (i + 1) - slot * 0.18
        if bh > 4:
            ink.rect((bx0, y1 - bh, bx1, y1), fill=SERIES[i % len(SERIES)])
            ink.hatch((bx0 + 8, y1 - bh + 8, bx0 + 30, y1 - 4), color="white", spacing=14, width=2)
        if ti > 0.9:
            ink.text(((bx0 + bx1) / 2, y1 - bh - 12), fmt_value(v, spec.unit), 38, anchor="mb")
        label = spec.labels[i] if i < len(spec.labels) else ""
        ink.text(((bx0 + bx1) / 2, y1 + 14), label, 30, anchor="mt")


def _lines(ink: Ink, spec: ChartSpec, box, t):
    x0, y0, x1, y1 = box
    vals = spec.values or [0, 1]
    lo, hi = min(0, min(vals)), max(vals) * 1.1 or 1
    _axes(ink, box, hi, spec.unit)
    n = len(vals) - 1 or 1
    k = _ease(t) * n
    pts = [(x0 + (x1 - x0) * i / n, y1 - (y1 - y0) * (v - lo) / (hi - lo)) for i, v in enumerate(vals) if i <= k]
    if len(pts) > 1:
        ink.line(pts, color="blue", width=9)
    if pts:
        ink.ellipse((pts[-1][0] - 11, pts[-1][1] - 11, pts[-1][0] + 11, pts[-1][1] + 11), fill="gold", width=4)
        ink.text((pts[-1][0], pts[-1][1] - 24), fmt_value(vals[len(pts) - 1], spec.unit), 36, anchor="mb")
    step = max(1, len(spec.labels) // 6)
    for i in range(0, len(spec.labels), step):
        ink.text((x0 + (x1 - x0) * i / n, y1 + 14), spec.labels[i], 26, color="grey", anchor="mt")


def _pie(ink: Ink, spec: ChartSpec, box, t):
    x0, y0, x1, y1 = box
    r = min(x1 - x0, y1 - y0) / 2 * 0.95
    cx, cy = x0 + r + 20, (y0 + y1) / 2
    total = sum(spec.values) or 1
    sweep = 360 * _ease(t)
    start = -90.0
    for i, v in enumerate(spec.values):
        ang = 360 * v / total
        a1 = start + min(ang, max(0.0, sweep - (start + 90)))
        if a1 > start:
            pts = [(cx, cy)] + [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
                                for a in [start + (a1 - start) * j / 24 for j in range(25)]]
            ink.poly(pts, fill=SERIES[i % len(SERIES)])
        start += ang
    for i, v in enumerate(spec.values):
        ly = y0 + 40 + i * 70
        ink.rect((cx + r + 60, ly, cx + r + 100, ly + 40), fill=SERIES[i % len(SERIES)], width=4)
        label = spec.labels[i] if i < len(spec.labels) else ""
        ink.text((cx + r + 115, ly + 20), f"{label}  {fmt_value(v, spec.unit)}", 38, anchor="lm")


DRAW = {"compound_growth": _compound, "bar_compare": _bars, "line_series": _lines, "pie_split": _pie}


def draw_chart(spec: ChartSpec, w: int, h: int, progress: float = 1.0, boil: int = 0) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ink = Ink(img, seed=boil * 17 + 9, wobble=1.6, width=5)
    pad = 60
    source = "" if spec.kind == "compound_growth" else spec.source
    if spec.kind == "compound_growth":
        p = spec.params
        source = f"Calculated: {p.get('rate', 0) * 100:g}%/yr, monthly compounding (hypothetical)"
    _frame(ink, w, h, spec.title, source, pad)
    box = (pad + 130, 150, w - pad - 20, h - 110)
    DRAW.get(spec.kind, _bars)(ink, spec, box, progress)
    return img


__all__ = ["draw_chart", "compound_series", "fmt_value", "c", "font"]
