"""Jointed 2D cut-out rigs for the GLIVARAO cast (same designs as v1: Max and Penny).

A Pose is a set of joint angles plus facial state. Limbs are drawn as hand-inked strokes each
frame; torso and head are cached sprites (3 "line boil" variants) rotated at their pivots. This
gives smooth, continuous motion with a consistent hand-drawn look.

Angle conventions (degrees):
  shoulder: 0 = arm hanging down, positive = raised outward (away from the body)
  elbow:    bend added to the shoulder angle (positive continues the outward/upward rotation)
  hip:      signed swing in screen x (+ = toward screen right); knee bends the shin
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from functools import lru_cache

from PIL import Image

from ..art.style import Ink

INK = (38, 34, 46)
SKIN = (241, 196, 160)
PANTS = (64, 74, 112)
SHOE = (70, 52, 44)


@dataclass
class Pose:
    torso: float = 0.0
    head: float = 0.0
    l_sh: float = 10.0
    l_el: float = 12.0
    r_sh: float = 10.0
    r_el: float = 12.0
    l_hip: float = -3.0
    l_knee: float = 0.0
    r_hip: float = 3.0
    r_knee: float = 0.0
    bob: float = 0.0
    l_hand: str = "rest"
    r_hand: str = "rest"
    # face
    mouth: float = 0.0        # 0 closed .. 1 wide open
    mouth_w: float = 0.0      # -1 narrow (O) .. 1 wide (E)
    smile: float = 0.5        # -1 frown .. 1 big smile
    brow: float = 0.0         # 0 neutral .. 1 raised
    worry: float = 0.0        # 0 .. 1 inner brows up
    blink: float = 0.0        # 0 open .. 1 closed
    look_x: float = 0.0
    look_y: float = 0.0

    def blend(self, other: "Pose", t: float) -> "Pose":
        out = Pose()
        for f in fields(Pose):
            a, b = getattr(self, f.name), getattr(other, f.name)
            if isinstance(a, str):
                setattr(out, f.name, b if t >= 0.5 else a)
            else:
                setattr(out, f.name, a + (b - a) * t)
        return out


def _rot(x: float, y: float, deg: float) -> tuple[float, float]:
    r = math.radians(deg)
    return x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)


# ------------------------------------------------------------------ sprites (cached)
@lru_cache(maxsize=64)
def _max_torso(s: float, boil: int) -> Image.Image:
    w, h = int(320 * s), int(380 * s)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ink = Ink(img, seed=boil * 31 + 1, wobble=1.3 * s, width=max(2, int(6 * s)))
    cx, by = w / 2, h - 20 * s  # pivot = hips (bottom centre)
    ink.rect((cx - 26 * s, by - 335 * s, cx + 26 * s, by - 280 * s), fill=(222, 166, 128), width=int(4 * s))
    ink.poly([(cx - 98 * s, by), (cx - 104 * s, by - 232 * s), (cx - 97 * s, by - 268 * s),
              (cx - 72 * s, by - 291 * s), (cx + 72 * s, by - 291 * s), (cx + 97 * s, by - 268 * s),
              (cx + 104 * s, by - 232 * s), (cx + 98 * s, by)], fill="green")
    ink.line([(cx - 44 * s, by - 290 * s), (cx, by - 252 * s), (cx + 44 * s, by - 290 * s)],
             color="green_light", width=int(8 * s))
    ink.line([(cx - 96 * s, by - 18 * s), (cx + 96 * s, by - 18 * s)], color="green_light", width=int(6 * s))
    return img


@lru_cache(maxsize=64)
def _max_head(s: float, boil: int) -> Image.Image:
    w, h = int(330 * s), int(340 * s)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ink = Ink(img, seed=boil * 37 + 3, wobble=1.3 * s, width=max(2, int(6 * s)))
    cx = w / 2
    ink.ellipse((cx - 132 * s, 150 * s, cx - 100 * s, 205 * s), fill="skin", width=int(4 * s))
    ink.ellipse((cx + 100 * s, 150 * s, cx + 132 * s, 205 * s), fill="skin", width=int(4 * s))
    ink.ellipse((cx - 115 * s, 45 * s, cx + 115 * s, 300 * s), fill="skin")
    ink.poly([(cx - 110 * s, 125 * s), (cx - 90 * s, 55 * s), (cx - 20 * s, 25 * s), (cx + 40 * s, 15 * s),
              (cx + 100 * s, 55 * s), (cx + 115 * s, 125 * s), (cx + 60 * s, 85 * s), (cx, 100 * s),
              (cx - 60 * s, 80 * s)], fill="hair")
    ink.line([(cx, 195 * s), (cx - 10 * s, 222 * s), (cx + 5 * s, 227 * s)], width=int(4 * s))
    return img


@lru_cache(maxsize=64)
def _coin(s: float, boil: int) -> Image.Image:
    r = 125 * s
    w = int(2 * r + 30 * s)
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    ink = Ink(img, seed=boil * 41 + 7, wobble=1.3 * s, width=max(2, int(7 * s)))
    c = w / 2
    ink.ellipse((c - r, c - r, c + r, c + r), fill="copper")
    ink.ellipse((c - r * 0.82, c - r * 0.82, c + r * 0.82, c + r * 0.82), fill="copper_light", width=int(4 * s))
    ink.line([(c - r * 0.55, c - r * 0.35), (c - r * 0.35, c - r * 0.6)], color="white", width=int(9 * s))
    return img


@lru_cache(maxsize=384)  # capped: each entry is a full sprite; 2048 cost ~0.5 GB per worker
def _rotated(kind: str, s: float, boil: int, angle: float) -> Image.Image:
    base = {"torso": _max_torso, "head": _max_head, "coin": _coin}[kind](s, boil)
    return base.rotate(angle, resample=Image.BICUBIC, expand=True) if angle else base


def _paste_rotated(dst: Image.Image, kind: str, s: float, boil: int, angle: float, pivot_dst, pivot_src):
    """Rotate sprite about its own pivot and paste so the pivot lands on pivot_dst."""
    angle = round(angle * 2) / 2
    base = {"torso": _max_torso, "head": _max_head, "coin": _coin}[kind](s, boil)
    img = _rotated(kind, s, boil, angle)
    bw, bh = base.size
    ox, oy = pivot_src[0] - bw / 2, pivot_src[1] - bh / 2
    rx, ry = _rot(ox, oy, -angle)  # PIL rotates counter-clockwise for positive angles
    x = pivot_dst[0] - (img.width / 2 + rx)
    y = pivot_dst[1] - (img.height / 2 + ry)
    dst.paste(img, (int(round(x)), int(round(y))), img)


# ------------------------------------------------------------------ face
def _face(ink: Ink, s: float, cx: float, cy: float, p: Pose, eye_gap: float, eye_r: float, glasses: bool,
          mouth_y: float, mouth_w: float):
    d = ink.d
    for side in (-1, 1):
        ex = cx + side * eye_gap
        ink.ellipse((ex - eye_r, cy - eye_r * 1.2, ex + eye_r, cy + eye_r * 1.2), fill="white",
                    width=max(2, int(4 * s)))
        pr = eye_r * 0.5
        px, py = ex + p.look_x * eye_r * 0.45, cy + p.look_y * eye_r * 0.45
        d.ellipse((px - pr, py - pr, px + pr, py + pr), fill=INK)
        if p.blink > 0.02:  # eyelid comes down from the top
            lid = p.blink * eye_r * 2.5
            d.chord((ex - eye_r - 1, cy - eye_r * 1.25, ex + eye_r + 1, cy - eye_r * 1.25 + lid * 1.9),
                    0, 360, fill=SKIN if glasses else (236, 178, 112))
            d.line([(ex - eye_r, cy - eye_r * 1.2 + lid * 0.95), (ex + eye_r, cy - eye_r * 1.2 + lid * 0.95)],
                   fill=INK, width=max(2, int(4 * s)))
        if glasses:
            gr = eye_r * 2.2
            ink.ellipse((ex - gr, cy - gr, ex + gr, cy + gr), width=max(2, int(5 * s)))
        by = cy - eye_r * (2.9 if glasses else 2.0) - p.brow * 12 * s
        inner_lift = -p.worry * 12 * s  # worried: the inner end (toward the nose) rises
        ink.line([(ex - side * 24 * s, by + inner_lift), (ex + side * 24 * s, by)],
                 width=max(2, int(6 * s)), wobble=0.6)
    if glasses:
        ink.line([(cx - eye_gap + eye_r * 2.2, cy), (cx + eye_gap - eye_r * 2.2, cy)], width=max(2, int(4 * s)))
    _mouth(ink, s, cx, mouth_y, mouth_w, p)


def _mouth(ink: Ink, s: float, cx: float, cy: float, w: float, p: Pose):
    d = ink.d
    width = w * (1 + 0.25 * p.mouth_w)
    if p.mouth < 0.1:
        curve = p.smile * 12 * s
        ink.line([(cx - width, cy - curve * 0.4), (cx, cy + curve), (cx + width, cy - curve * 0.4)],
                 width=max(2, int(5 * s)), wobble=0.5)
        return
    h = (8 + 36 * p.mouth) * s
    top = cy - 6 * s - p.smile * 3 * s
    pts = [(cx - width, top), (cx + width, top), (cx + width * 0.7, top + h * 0.75), (cx, top + h),
           (cx - width * 0.7, top + h * 0.75)]
    d.polygon(pts, fill=(112, 36, 48))
    if p.mouth > 0.35:
        d.ellipse((cx - width * 0.45, top + h * 0.5, cx + width * 0.45, top + h * 0.98), fill=(232, 112, 112))
        d.rectangle((cx - width * 0.6, top + 1, cx + width * 0.6, top + 6 * s), fill=(255, 253, 247))
    ink.line(pts + [pts[0]], width=max(2, int(5 * s)), wobble=0.5)


# ------------------------------------------------------------------ hands & limbs
def _hand(ink: Ink, s: float, x: float, y: float, direction: float, shape: str, color=SKIN):
    """direction: absolute forearm angle (deg, 0 = down)."""
    r = 21 * s
    dx, dy = math.sin(math.radians(direction)), math.cos(math.radians(direction))
    if shape == "point":
        ink.line([(x, y), (x + dx * 46 * s, y + dy * 46 * s)], color=INK, width=int(15 * s), wobble=0.4)
        ink.line([(x, y), (x + dx * 44 * s, y + dy * 44 * s)], color=color, width=int(9 * s), wobble=0.4)
    elif shape == "open":
        for spread in (-32, -12, 10, 30):
            a = math.radians(direction + spread)
            ink.line([(x, y), (x + math.sin(a) * 34 * s, y + math.cos(a) * 34 * s)], color=INK,
                     width=int(12 * s), wobble=0.3)
            ink.line([(x, y), (x + math.sin(a) * 32 * s, y + math.cos(a) * 32 * s)], color=color,
                     width=int(7 * s), wobble=0.3)
    elif shape == "thumb":
        ink.line([(x, y), (x, y - 40 * s)], color=INK, width=int(15 * s), wobble=0.3)
        ink.line([(x, y), (x, y - 38 * s)], color=color, width=int(9 * s), wobble=0.3)
    ink.ellipse((x - r, y - r, x + r, y + r), fill=color, width=max(2, int(4 * s)))


def _limb(ink: Ink, s: float, a, b, c, color, width: float, outline=True):
    if outline:
        ink.line([a, b, c], color=INK, width=int(width + 10 * s), wobble=0.8)
    ink.line([a, b, c], color=color, width=int(width), wobble=0.8)


def _chain(origin, a1: float, l1: float, a2: float, l2: float, side: int):
    """Two-bone chain; side=+1 bends toward screen right, -1 toward left."""
    x0, y0 = origin
    x1 = x0 + side * math.sin(math.radians(a1)) * l1
    y1 = y0 + math.cos(math.radians(a1)) * l1
    x2 = x1 + side * math.sin(math.radians(a1 + a2)) * l2
    y2 = y1 + math.cos(math.radians(a1 + a2)) * l2
    return (x0, y0), (x1, y1), (x2, y2), a1 + a2


# ------------------------------------------------------------------ characters
CANVAS = {"max": (780, 1120), "penny": (640, 760)}
ROOT = {"max": (390, 660), "penny": (320, 560)}  # hips/base position inside the canvas at s=1


def draw_max(p: Pose, s: float = 1.0, boil: int = 0) -> Image.Image:
    W, H = int(CANVAS["max"][0] * s), int(CANVAS["max"][1] * s)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ink = Ink(img, seed=boil * 53 + 11, wobble=1.2 * s, width=max(2, int(6 * s)))
    rx, ry = ROOT["max"][0] * s, ROOT["max"][1] * s + p.bob * s

    # legs (behind torso)
    for side, hip, knee in ((-1, p.l_hip, p.l_knee), (1, p.r_hip, p.r_knee)):
        hipx = rx + side * 46 * s
        sgn = 1 if hip >= 0 else -1
        a, b, c, ang = _chain((hipx, ry - 10 * s), abs(hip), 165 * s, -knee * sgn * 0.5, 160 * s, sgn)
        _limb(ink, s, a, b, c, PANTS, 44 * s)
        fx = c[0] + side * 22 * s
        ink.ellipse((fx - 40 * s, c[1] - 14 * s, fx + 40 * s, c[1] + 22 * s), fill=SHOE, width=max(2, int(5 * s)))

    # torso sprite rotated about the hips
    t_sprite = _max_torso(s, boil)
    piv_src = (t_sprite.width / 2, t_sprite.height - 20 * s)
    _paste_rotated(img, "torso", s, boil, -p.torso, (rx, ry), piv_src)

    def torso_pt(x, y):
        dx, dy = _rot(x * s, y * s, p.torso)
        return rx + dx, ry + dy

    # head sprite + face on a head canvas, rotated about the neck
    neck = torso_pt(0, -318)
    head = _max_head(s, boil).copy()
    hink = Ink(head, seed=boil * 59 + 5, wobble=1.0 * s, width=max(2, int(6 * s)))
    hc = head.width / 2
    _face(hink, s, hc, 172 * s, p, 48 * s, 15 * s, True, 248 * s, 28 * s)
    hr = head.rotate(-(p.head + p.torso), resample=Image.BICUBIC, expand=True)
    hpx, hpy = hc, 318 * s  # neck pivot in head canvas
    ox, oy = hpx - head.width / 2, hpy - head.height / 2
    rxo, ryo = _rot(ox, oy, p.head + p.torso)
    img.paste(hr, (int(neck[0] - (hr.width / 2 + rxo)), int(neck[1] - (hr.height / 2 + ryo))), hr)

    # arms (in front)
    for side, sh, el, hand in ((-1, p.l_sh, p.l_el, p.l_hand), (1, p.r_sh, p.r_el, p.r_hand)):
        shoulder = torso_pt(side * 84, -262)
        a, b, c, ang = _chain(shoulder, sh - side * p.torso, 128 * s, el, 116 * s, side)
        _limb(ink, s, a, b, c, (46, 139, 87), 34 * s)
        _hand(ink, s, c[0], c[1], side * ang, hand)
    return img


def draw_penny(p: Pose, s: float = 1.0, boil: int = 0) -> Image.Image:
    W, H = int(CANVAS["penny"][0] * s), int(CANVAS["penny"][1] * s)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ink = Ink(img, seed=boil * 61 + 13, wobble=1.2 * s, width=max(2, int(6 * s)))
    rx, ry = ROOT["penny"][0] * s, ROOT["penny"][1] * s + p.bob * s
    center = (rx, ry - 125 * s)
    for side, hip, knee in ((-1, p.l_hip, p.l_knee), (1, p.r_hip, p.r_knee)):
        sgn = 1 if hip >= 0 else -1
        a, b, c, _ = _chain((rx + side * 50 * s, ry - 20 * s), abs(hip), 75 * s, -knee * sgn * 0.5, 72 * s, sgn)
        ink.line([a, b, c], width=int(9 * s))
        fx = c[0] + side * 18 * s
        ink.ellipse((fx - 26 * s, c[1] - 10 * s, fx + 26 * s, c[1] + 14 * s), fill=INK, outline=None)
    for side, sh, el, hand in ((-1, p.l_sh, p.l_el, p.l_hand), (1, p.r_sh, p.r_el, p.r_hand)):
        sx, sy = center[0] + side * 112 * s, center[1] + 20 * s
        a, b, c, ang = _chain((sx, sy), sh + 15, 70 * s, el, 66 * s, side)
        ink.line([a, b, c], width=int(9 * s))
        _hand(ink, s, c[0], c[1], side * ang, hand, color=(255, 253, 247))
    coin = _coin(s, boil)
    _paste_rotated(img, "coin", s, boil, -p.torso, center, (coin.width / 2, coin.height / 2))
    fx, fy = _rot(0, -30 * s, p.torso)
    _face(ink, s, center[0] + fx, center[1] + fy, p, 50 * s, 19 * s, False, center[1] + 55 * s, 32 * s)
    return img


def draw(name: str, p: Pose, s: float, boil: int) -> Image.Image:
    return draw_max(p, s, boil) if name == "max" else draw_penny(p, s, boil)
