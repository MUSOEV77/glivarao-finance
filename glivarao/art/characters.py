"""Original GLIVARAO cast, drawn procedurally in a hand-drawn style.

- Max   : narrator. Round glasses, brown hair tuft, green sweater.
- Penny : a talking copper coin with stick arms and legs.

Characters are drawn on a transparent RGBA canvas. `mouth` in [0,1] opens the mouth (driven by
narration loudness); `blink` closes the eyes; `boil` reseeds the line jitter.
"""
from __future__ import annotations

from PIL import Image

from .style import Ink

CANVAS = (520, 720)  # w, h at scale 1.0


def _canvas(scale: float) -> Image.Image:
    return Image.new("RGBA", (int(CANVAS[0] * scale), int(CANVAS[1] * scale)), (0, 0, 0, 0))


def _eyes(ink: Ink, s, cx, cy, gap, r, blink: bool, look=(0, 0)):
    for ex in (cx - gap, cx + gap):
        if blink:
            ink.line([(ex - r, cy), (ex + r, cy)], width=int(5 * s))
        else:
            ink.ellipse((ex - r, cy - r * 1.2, ex + r, cy + r * 1.2), fill="white", width=int(4 * s))
            pr = r * 0.5
            px, py = ex + look[0] * r * 0.4, cy + look[1] * r * 0.4
            ink.d.ellipse((px - pr, py - pr, px + pr, py + pr), fill=(38, 34, 46))


def _mouth(ink: Ink, s, cx, cy, w, mouth: float, mood: str):
    if mood == "worry" and mouth < 0.2:
        ink.line([(cx - w, cy + 6 * s), (cx, cy - 4 * s), (cx + w, cy + 6 * s)], width=int(5 * s))
        return
    if mouth < 0.15:
        ink.line([(cx - w, cy - 3 * s), (cx, cy + 8 * s), (cx + w, cy - 3 * s)], width=int(5 * s))
        return
    h = (10 + 34 * mouth) * s
    ink.poly([(cx - w, cy - 4 * s), (cx + w, cy - 4 * s), (cx + w * 0.6, cy + h), (cx - w * 0.6, cy + h)],
             fill=(120, 40, 50), width=int(5 * s))
    ink.ellipse((cx - w * 0.4, cy + h * 0.45, cx + w * 0.4, cy + h * 0.95), fill=(230, 110, 110), outline=None)


def _arms(ink: Ink, s, sx, sy, pose: str, side: int, color: str, width: int):
    """Arm from shoulder (sx, sy). side=-1 left, +1 right."""
    if pose == "cheer":
        pts = [(sx, sy), (sx + side * 110 * s, sy - 70 * s), (sx + side * 150 * s, sy - 170 * s)]
    elif pose == "point" and side == 1:
        pts = [(sx, sy), (sx + 110 * s, sy - 40 * s), (sx + 210 * s, sy - 90 * s)]
    elif pose == "think" and side == 1:
        pts = [(sx, sy), (sx + 40 * s, sy + 90 * s), (sx - 60 * s, sy - 30 * s)]
    elif pose == "worry":
        pts = [(sx, sy), (sx + side * 30 * s, sy + 110 * s), (sx - side * 40 * s, sy + 150 * s)]
    elif pose == "talk" and side == 1:
        pts = [(sx, sy), (sx + 70 * s, sy + 90 * s), (sx + 140 * s, sy + 40 * s)]
    else:
        pts = [(sx, sy), (sx + side * 40 * s, sy + 110 * s), (sx + side * 50 * s, sy + 210 * s)]
    if color == "ink":
        ink.line(pts, color="ink", width=width)
    else:  # outlined sleeve: dark stroke underneath, colour on top
        ink.line(pts, color="ink", width=width + 10, wobble=1.0)
        ink.line(pts, color=color, width=width, wobble=1.0)
    hx, hy = pts[-1]
    ink.ellipse((hx - 22 * s, hy - 22 * s, hx + 22 * s, hy + 22 * s), fill="skin", width=int(4 * s))


def draw_max(pose="talk", mouth=0.0, blink=False, boil=0, scale=1.0) -> Image.Image:
    s = scale
    img = _canvas(s)
    ink = Ink(img, seed=boil * 31 + 1, wobble=2.0 * s, width=int(6 * s))
    cx = 260 * s
    # body / sweater
    ink.poly([(cx - 120 * s, 690 * s), (cx - 95 * s, 430 * s), (cx + 95 * s, 430 * s), (cx + 120 * s, 690 * s)],
             fill="green")
    ink.line([(cx - 50 * s, 440 * s), (cx, 480 * s), (cx + 50 * s, 440 * s)], color="green_light", width=int(8 * s))
    for side, sx in ((-1, cx - 92 * s), (1, cx + 92 * s)):
        _arms(ink, s, sx, 455 * s, pose, side, "green", int(34 * s))
    # neck + head
    ink.rect((cx - 28 * s, 385 * s, cx + 28 * s, 440 * s), fill="skin_shade", width=int(4 * s))
    ink.ellipse((cx - 115 * s, 150 * s, cx + 115 * s, 405 * s), fill="skin")
    ink.ellipse((cx - 132 * s, 255 * s, cx - 100 * s, 310 * s), fill="skin", width=int(4 * s))  # ears
    ink.ellipse((cx + 100 * s, 255 * s, cx + 132 * s, 310 * s), fill="skin", width=int(4 * s))
    # hair tuft
    ink.poly([(cx - 110 * s, 230 * s), (cx - 90 * s, 160 * s), (cx - 20 * s, 130 * s), (cx + 40 * s, 120 * s),
              (cx + 100 * s, 160 * s), (cx + 115 * s, 230 * s), (cx + 60 * s, 190 * s), (cx, 205 * s),
              (cx - 60 * s, 185 * s)], fill="hair")
    look = (0.6, -0.4) if pose in ("point", "think") else (0, 0)
    _eyes(ink, s, cx, 280 * s, 48 * s, 16 * s, blink, look)
    for gx in (cx - 48 * s, cx + 48 * s):  # round glasses
        ink.ellipse((gx - 36 * s, 244 * s, gx + 36 * s, 316 * s), width=int(5 * s))
    ink.line([(cx - 12 * s, 278 * s), (cx + 12 * s, 278 * s)], width=int(4 * s))
    brow = -10 if pose == "worry" else (-4 if pose == "think" else 0)
    for side in (-1, 1):
        bx = cx + side * 48 * s
        ink.line([(bx - 26 * s, (232 + (brow if side == -1 else 0)) * s),
                  (bx + 26 * s, (232 + (brow if side == 1 else 0)) * s)], width=int(6 * s))
    ink.line([(cx, 300 * s), (cx - 10 * s, 325 * s), (cx + 4 * s, 330 * s)], width=int(4 * s))  # nose
    _mouth(ink, s, cx, 352 * s, 30 * s, mouth, pose)
    return img


def draw_penny(pose="talk", mouth=0.0, blink=False, boil=0, scale=1.0) -> Image.Image:
    s = scale
    img = _canvas(s)
    ink = Ink(img, seed=boil * 37 + 2, wobble=2.0 * s, width=int(6 * s))
    cx, cy, r = 260 * s, 330 * s, 175 * s
    # legs
    for side in (-1, 1):
        ink.line([(cx + side * 60 * s, cy + r - 20 * s), (cx + side * 75 * s, 650 * s),
                  (cx + side * 115 * s, 660 * s)], width=int(9 * s))
    for side, sx in ((-1, cx - r + 15 * s), (1, cx + r - 15 * s)):
        _arms(ink, s, sx, cy + 30 * s, pose, side, "ink", int(9 * s))
    ink.ellipse((cx - r, cy - r, cx + r, cy + r), fill="copper", width=int(7 * s))
    ink.ellipse((cx - r * 0.82, cy - r * 0.82, cx + r * 0.82, cy + r * 0.82), fill="copper_light",
                width=int(4 * s))
    # shine
    ink.line([(cx - r * 0.55, cy - r * 0.35), (cx - r * 0.35, cy - r * 0.6)], color="white", width=int(10 * s))
    _eyes(ink, s, cx, cy - 30 * s, 50 * s, 20 * s, blink)
    _mouth(ink, s, cx, cy + 55 * s, 34 * s, mouth, pose)
    return img


def draw_character(name: str, **kw) -> Image.Image:
    return {"max": draw_max, "penny": draw_penny}[name](**kw)
