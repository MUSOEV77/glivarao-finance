"""Editorial data graphics (documentary style), animated by `progress` in [0, 1].

Drawn at 2x and downsampled for clean anti-aliased lines. Numbers come only from the ChartSpec:
compound_growth is computed exactly from its params, so it is always numerically correct.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from ..models import ChartSpec
from .charts import compound_series, fmt_value
from .editorial_style import PAL, draw_text, face, fit_lines, tone

SS = 2  # supersampling factor


def _e(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _seg(t: float, a: float, b: float) -> float:
    return _e((t - a) / max(1e-6, b - a))


def _nice_max(v: float) -> float:
    if v <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(v))
    for m in (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= m * mag:
            return m * mag
    return 10 * mag


def _header(d, w, spec_title, s, compact):
    tsize = (44 if compact else 56) * s
    lines, size = fit_lines(spec_title, "serif", tsize, w - 20 * s, 2, 26 * s)
    y = 0
    for ln in lines:
        draw_text(d, (0, y), ln, "serif", size, "ink")
        y += int(size * 1.12)
    return y + 18 * s


def _grid(d, box, ymax, unit, s, ticks=4):
    x0, y0, x1, y1 = box
    for i in range(ticks + 1):
        y = y1 - (y1 - y0) * i / ticks
        d.line([(x0, y), (x1, y)], fill=(*PAL["rule"], 255 if i == 0 else 150), width=(2 if i == 0 else 1) * s)
        if i:
            draw_text(d, (x0 - 14 * s, y), fmt_value(ymax * i / ticks, unit), "sans_med", 26 * s, "sub", anchor="rm")


def _callout(d, x, y, label, color, s, side="left", sub=None):
    r = 9 * s
    d.ellipse((x - r, y - r, x + r, y + r), fill=PAL[color], outline=PAL["white"], width=3 * s)
    f = face("sans_xbold", 40 * s)
    tw = f.getlength(label)
    tx = x - tw - 22 * s if side == "left" else x + 22 * s
    draw_text(d, (tx, y - 34 * s), label, "sans_xbold", 40 * s, color)
    if sub:
        draw_text(d, (tx, y + 14 * s), sub, "sans_med", 22 * s, "sub")


def _compound(d, spec: ChartSpec, box, t, s):
    p = spec.params
    yrs, bal, contrib = compound_series(p.get("principal", 0), p.get("rate", 0.07), p.get("years", 30),
                                        p.get("monthly", 0))
    x0, y0, x1, y1 = box
    ymax = _nice_max(max(bal) * 1.05)
    _grid(d, box, ymax, "$", s)
    n = len(yrs) - 1 or 1
    X = lambda i: x0 + (x1 - x0) * i / n  # noqa: E731
    Y = lambda v: y1 - (y1 - y0) * v / ymax  # noqa: E731
    k = max(1, int(round(n * _seg(t, 0.0, 0.85))))
    pts_b = [(X(i), Y(bal[i])) for i in range(k + 1)]
    pts_c = [(X(i), Y(contrib[i])) for i in range(k + 1)]
    d.polygon(pts_b + pts_c[::-1], fill=(*PAL["green_l"], 200))
    d.polygon(pts_c + [(pts_c[-1][0], y1), (x0, y1)], fill=(*PAL["navy_l"], 210))
    d.line(pts_c, fill=PAL["navy"], width=4 * s, joint="curve")
    d.line(pts_b, fill=PAL["green"], width=6 * s, joint="curve")
    step = 5 if n > 12 else (2 if n > 6 else 1)
    for i in range(0, n + 1, step):
        draw_text(d, (X(i), y1 + 16 * s), f"Year {yrs[i]}" if i == 0 else str(yrs[i]), "sans_med", 26 * s, "sub",
                  anchor="ma")
    # legend
    lx, ly = x0 + 10 * s, y0 + 6 * s
    for col, lab in (("green_l", "Growth"), ("navy_l", "Money you put in")):
        d.rectangle((lx, ly, lx + 26 * s, ly + 26 * s), fill=PAL[col])
        draw_text(d, (lx + 38 * s, ly + 13 * s), lab, "sans_semi", 24 * s, "ink", anchor="lm")
        lx += 70 * s + face("sans_semi", 24 * s).getlength(lab)
    if t >= 0.85:
        a = _seg(t, 0.85, 1.0)
        if a > 0.05:
            _callout(d, *pts_b[-1], fmt_value(bal[k], "$"), "green", s,
                     sub=f"you put in {fmt_value(contrib[k], '$')}")


def _bars(d, spec: ChartSpec, box, t, s):
    vals = spec.values or [0]
    labels = spec.labels or [""] * len(vals)
    x0, y0, x1, y1 = box
    ymax = _nice_max(max(vals) * 1.12)
    _grid(d, box, ymax, spec.unit, s)
    n = len(vals)
    slot = (x1 - x0) / n
    bw = min(slot * 0.52, 260 * s)
    hi = vals.index(max(vals))
    accent = tone(spec.title + " " + " ".join(labels))
    accent = "crimson" if accent == "crimson" else ("green" if accent == "green" else "navy")
    for i, v in enumerate(vals):
        pr = _seg(t, 0.08 * i, 0.55 + 0.08 * i)
        cx = x0 + slot * (i + 0.5)
        top = y1 - (y1 - y0) * (v / ymax) * pr
        col = accent if i == hi else "navy_l"
        d.rectangle((cx - bw / 2, top, cx + bw / 2, y1), fill=PAL[col])
        if pr > 0.05:
            draw_text(d, (cx, top - 14 * s), fmt_value(v * pr, spec.unit), "sans_xbold", 40 * s,
                      accent if i == hi else "ink", anchor="md")
        lines, size = fit_lines(labels[i], "sans_semi", 30 * s, slot - 16 * s, 2, 18 * s)
        for k, ln in enumerate(lines):
            draw_text(d, (cx, y1 + 16 * s + k * size * 1.15), ln, "sans_semi", size, "ink", anchor="ma")


def _lines(d, spec: ChartSpec, box, t, s):
    vals = spec.values or [0, 0]
    labels = spec.labels or [str(i) for i in range(len(vals))]
    x0, y0, x1, y1 = box
    lo = min(0, min(vals))
    ymax = _nice_max(max(vals) * 1.1)
    _grid(d, box, ymax, spec.unit, s)
    n = len(vals) - 1 or 1
    X = lambda i: x0 + (x1 - x0) * i / n  # noqa: E731
    Y = lambda v: y1 - (y1 - y0) * (v - lo) / (ymax - lo)  # noqa: E731
    frac = n * _seg(t, 0, 0.85)
    k = int(frac)
    pts = [(X(i), Y(vals[i])) for i in range(k + 1)]
    if k < n:
        f = frac - k
        pts.append((X(k) + (X(k + 1) - X(k)) * f, Y(vals[k] + (vals[k + 1] - vals[k]) * f)))
    col = tone(spec.title)
    if len(pts) > 1:
        d.polygon(pts + [(pts[-1][0], y1), (x0, y1)], fill=(*PAL[col + "_l"], 120))
        d.line(pts, fill=PAL[col], width=6 * s, joint="curve")
    for i in sorted({0, n // 2, n}):
        draw_text(d, (X(i), y1 + 16 * s), labels[i], "sans_med", 26 * s, "sub", anchor="ma")
    if t >= 0.85 and pts:
        _callout(d, *pts[-1], fmt_value(vals[-1], spec.unit), col, s)


def _split(d, spec: ChartSpec, box, t, s):
    """Pie data drawn as an editorial 100% bar: easier to compare than wedges."""
    vals = spec.values or [1]
    labels = spec.labels or [""] * len(vals)
    total = sum(vals) or 1
    x0, y0, x1, y1 = box
    cols = ["navy", "green", "crimson", "amber", "sub"]
    bar_top, bar_h = y0 + (y1 - y0) * 0.22, (y1 - y0) * 0.26
    x = x0
    for i, v in enumerate(vals):
        w = (x1 - x0) * v / total
        pr = _seg(t, 0.12 * i, 0.5 + 0.12 * i)
        d.rectangle((x, bar_top, x + w * pr, bar_top + bar_h), fill=PAL[cols[i % len(cols)]])
        if pr > 0.4:
            pct = f"{v / total * 100:.0f}%"
            draw_text(d, (x + 4 * s, bar_top + bar_h + 26 * s), pct, "sans_xbold", 56 * s, cols[i % len(cols)])
            lines, size = fit_lines(labels[i], "sans_semi", 26 * s, max(w - 16 * s, 120 * s), 2, 18 * s)
            for k, ln in enumerate(lines):
                draw_text(d, (x + 4 * s, bar_top + bar_h + 98 * s + k * size * 1.15), ln, "sans_semi", size, "ink")
        if i:
            d.line([(x, bar_top - 10 * s), (x, bar_top + bar_h + 10 * s)], fill=PAL["paper"], width=6 * s)
        x += w


DRAW = {"compound_growth": _compound, "bar_compare": _bars, "line_series": _lines, "pie_split": _split}


def source_line(spec: ChartSpec) -> str:
    if spec.kind == "compound_growth":
        p = spec.params
        return f"Calculation: {p.get('rate', 0) * 100:g}% a year, compounded monthly. Hypothetical, not a forecast."
    return f"Source: {spec.source}" if spec.source else ""


def draw_editorial_chart(spec: ChartSpec, w: int, h: int, progress: float = 1.0, compact: bool = False) -> Image.Image:
    s = SS
    img = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    top = _header(d, w * s, spec.title, s, compact)
    src = source_line(spec)
    bottom_pad = (44 + (40 if src else 0)) * s + (44 * s if spec.kind in ("bar_compare",) else 0)
    left = 120 * s if spec.kind != "pie_split" else 0
    box = (left, top + 40 * s, w * s - 30 * s, h * s - bottom_pad)
    DRAW.get(spec.kind, _bars)(d, spec, box, progress, s)
    if src:
        lines, size = fit_lines(src, "sans", 24 * s, w * s, 1, 14 * s)
        draw_text(d, (0, h * s - 8 * s), lines[0], "sans", size, "sub", anchor="ld")
    return img.resize((w, h), Image.LANCZOS)


__all__ = ["draw_editorial_chart", "source_line"]
