"""GLIVARAO doodle style: our own hand-drawn explainer look.

Off-white paper, black marker doodles, a simple stick-style mascot ("Max": round head, round glasses, three-hair
tuft, green sweater with a gold coin pin), hand-drawn charts and arrows, brand colors deep green #1f8a4c + gold,
and a small GLIVARAO mark in a corner. Everything here is drawn by code, so Max looks exactly the same in every
video and thumbnail, costs nothing and never shows a real face or anyone else's logo or character.

The same drawings produce the Max style reference sheet (data/character/doodle_reference.png) that is sent with
every Nano Banana request in this style, so AI scene art keeps Max on-model.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"
PAPER = (247, 243, 232)
INK = (26, 26, 26)
GREEN = (31, 138, 76)        # brand deep green #1f8a4c
GOLD = (224, 165, 38)        # brand gold accent #e0a526
GREY = (150, 150, 146)       # history lines
SOFT = (226, 220, 204)       # pencil shading on paper
EMOTIONS = ("happy", "worried", "shocked", "thinking", "confident", "cheering", "sad")
VERSION = "doodle-v1"


# ------------------------------------------------------------------------------------------- basics
@lru_cache(maxsize=16)
def hand(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / "PatrickHand-Regular.ttf"), size)


@lru_cache(maxsize=8)
def paper(w: int, h: int, seed: int = 7) -> Image.Image:
    """Off-white paper with a faint grain and a few fibers (deterministic)."""
    rng = np.random.default_rng(seed)
    base = np.empty((h, w, 3), dtype=np.float32)
    base[:] = PAPER
    base += rng.normal(0, 2.2, (h, w, 1))
    low = rng.normal(0, 3.0, (h // 32 + 2, w // 32 + 2, 1)).astype(np.float32)
    low = np.asarray(Image.fromarray(((low[..., 0] + 12) * 8).clip(0, 255).astype(np.uint8)).resize(
        (w, h), Image.BICUBIC), dtype=np.float32)[..., None] / 8 - 12
    base += low * 0.6
    img = Image.fromarray(base.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    r = random.Random(seed)
    for _ in range(max(6, w * h // 90000)):
        x, y = r.uniform(0, w), r.uniform(0, h)
        a, ln = r.uniform(0, math.pi), r.uniform(8, 30)
        d.line([(x, y), (x + ln * math.cos(a), y + ln * math.sin(a))], fill=(232, 226, 210), width=1)
    return img


class Pen:
    """Black-marker strokes with a slight hand wobble. Draw at 2x and downscale for smooth edges."""

    def __init__(self, img: Image.Image, seed: int = 1, width: float = 7.0, color=INK, wobble: float = 1.6):
        self.img, self.d = img, ImageDraw.Draw(img)
        self.r = random.Random(seed)
        self.width, self.color, self.wobble = width, color, wobble

    def _jit(self, pts, wobble=None):
        wb = self.wobble if wobble is None else wobble
        return [(x + self.r.uniform(-wb, wb), y + self.r.uniform(-wb, wb)) for x, y in pts]

    def line(self, pts, width=None, color=None, wobble=None, closed=False):
        w = int(round(width or self.width))
        c = color or self.color
        dense = []
        pts = list(pts) + ([pts[0]] if closed else [])
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 42))
            dense += [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(n)]
        dense.append(pts[-1])
        dense = self._jit(dense, wobble)
        self.d.line(dense, fill=c, width=w, joint="curve")
        for x, y in (dense[0], dense[-1]):
            self.d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=c)

    def circle(self, cx, cy, r, width=None, color=None, fill=None, start=0.0, sweep=360.0):
        n = max(16, int(r / 3))
        a0 = math.radians(start)
        pts = [(cx + r * math.cos(a0 + math.radians(sweep) * k / n), cy + r * math.sin(a0 + math.radians(sweep) * k / n))
               for k in range(n + 1)]
        if fill is not None:
            self.d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
        self.line(pts, width, color, wobble=self.wobble * 0.6)

    def dot(self, x, y, r, color=None):
        self.d.ellipse((x - r, y - r, x + r, y + r), fill=color or self.color)

    def poly(self, pts, fill=None, width=None, color=None):
        if fill is not None:
            self.d.polygon(self._jit(pts, 0.8), fill=fill)
        self.line(pts, width, color, closed=True)

    def arrow(self, x0, y0, x1, y1, width=None, color=None, head=26):
        self.line([(x0, y0), ((x0 + x1) / 2 + self.r.uniform(-8, 8), (y0 + y1) / 2 + self.r.uniform(-8, 8)),
                   (x1, y1)], width, color)
        a = math.atan2(y1 - y0, x1 - x0)
        for s in (-1, 1):
            self.line([(x1, y1), (x1 - head * math.cos(a + s * 0.5), y1 - head * math.sin(a + s * 0.5))], width,
                      color)

    def hatch(self, box, color, gap=14, width=4):
        x0, y0, x1, y1 = box
        k = x0 - (y1 - y0)
        while k < x1:
            self.d.line([(max(x0, k), y1 - max(0, x0 - k)), (min(x1, k + (y1 - y0)), y0 + max(0, k + (y1 - y0) - x1))],
                        fill=color, width=width)
            k += gap

    def text(self, xy, s, size, color=None, anchor="mm", bold=0):
        self.d.text(xy, s, font=hand(size), fill=color or self.color, anchor=anchor,
                    stroke_width=bold, stroke_fill=color or self.color)


def finish(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return img.resize(size, Image.LANCZOS)


def brand_mark(img: Image.Image, corner: str = "br", scale: float = 1.0) -> None:
    """Small GLIVARAO mark: green handwritten word with a gold underline dot."""
    w, h = img.size
    s = int(30 * scale)
    p = Pen(img, seed=99, width=3 * scale, color=GREEN, wobble=0.6)
    txt_w = hand(s).getlength("GLIVARAO")
    x = w - txt_w / 2 - 34 * scale if corner.endswith("r") else txt_w / 2 + 34 * scale
    y = h - 34 * scale if corner.startswith("b") else 34 * scale
    p.text((x, y), "GLIVARAO", s, GREEN, bold=1)
    p.line([(x - txt_w / 2, y + s * 0.62), (x + txt_w / 2 - 12 * scale, y + s * 0.62)], 3 * scale, GREEN)
    p.dot(x + txt_w / 2, y + s * 0.62, 5 * scale, GOLD)


# ------------------------------------------------------------------------------------------- Max
def draw_max(img: Image.Image, cx: float, base_y: float, u: float = 60.0, emotion: str = "happy",
             seed: int = 5, point_to: tuple[float, float] | None = None) -> None:
    """Max, standing with his feet on base_y. u = head radius. Same proportions in every video."""
    p = Pen(img, seed=seed, width=max(4, u * 0.11), wobble=u * 0.02)
    lw = max(4, u * 0.11)
    head_y = base_y - u * 6.4
    hx = cx
    # legs + shoes
    hip = base_y - u * 2.3
    for s in (-1, 1):
        p.line([(cx + s * u * 0.35, hip), (cx + s * u * 0.55, base_y - u * 0.15)], lw)
        p.d.ellipse((cx + s * u * 0.55 - u * 0.35 + s * u * 0.12, base_y - u * 0.3, cx + s * u * 0.55 + u * 0.35 +
                     s * u * 0.12, base_y + u * 0.05), fill=INK)
    # sweater (green, with a gold coin pin)
    sh_y = head_y + u * 1.25
    # rounded shoulders, slightly narrower at the waist, ribbed hem, V-neck
    torso = [(cx - u * 0.45, sh_y), (cx - u * 0.85, sh_y + u * 0.12), (cx - u * 1.0, sh_y + u * 0.45),
             (cx - u * 0.82, hip + u * 0.1), (cx + u * 0.82, hip + u * 0.1), (cx + u * 1.0, sh_y + u * 0.45),
             (cx + u * 0.85, sh_y + u * 0.12), (cx + u * 0.45, sh_y)]
    p.poly(torso, fill=GREEN, width=lw)
    p.d.line([(cx - u * 0.78, hip - u * 0.08), (cx + u * 0.78, hip - u * 0.08)], fill=(22, 104, 57), width=int(lw))
    p.line([(cx - u * 0.3, sh_y + u * 0.02), (cx, sh_y + u * 0.4), (cx + u * 0.3, sh_y + u * 0.02)], lw * 0.7)
    p.circle(cx + u * 0.48, sh_y + u * 0.8, u * 0.17, width=lw * 0.6, fill=GOLD)
    # arms by emotion
    L, R = (cx - u * 0.9, sh_y + u * 0.35), (cx + u * 0.9, sh_y + u * 0.35)

    def arm(start, elbow, hand_):
        p.line([start, elbow, hand_], lw)
        p.dot(hand_[0], hand_[1], u * 0.16)

    if emotion == "cheering":
        arm(L, (cx - u * 1.6, sh_y - u * 0.4), (cx - u * 1.9, sh_y - u * 1.4))
        arm(R, (cx + u * 1.6, sh_y - u * 0.4), (cx + u * 1.9, sh_y - u * 1.4))
    elif emotion == "thinking":
        arm(L, (cx - u * 1.3, sh_y + u * 1.4), (cx - u * 0.9, hip - u * 0.3))
        arm(R, (cx + u * 1.35, sh_y + u * 1.0), (hx + u * 0.6, head_y + u * 0.92))       # hand to chin
    elif emotion == "worried":
        arm(L, (cx - u * 1.5, sh_y - u * 0.2), (hx - u * 0.95, head_y - u * 0.2))         # hand on head
        arm(R, (cx + u * 1.3, sh_y + u * 1.3), (cx + u * 1.1, hip - u * 0.2))
    elif emotion == "shocked":
        arm(L, (cx - u * 1.5, sh_y + u * 0.1), (cx - u * 1.8, sh_y - u * 0.8))
        arm(R, (cx + u * 1.5, sh_y + u * 0.1), (cx + u * 1.8, sh_y - u * 0.8))
    elif emotion in ("confident",) or point_to is not None:
        tx, ty = point_to or (cx + u * 4, sh_y - u * 0.5)
        S, O, sgn = (R, L, 1) if tx >= cx else (L, R, -1)      # point with the arm on the target's side
        a = math.atan2(ty - S[1], tx - S[0])
        arm(S, (S[0] + u * 0.9 * math.cos(a) + sgn * u * 0.1, S[1] + u * 0.9 * math.sin(a) + u * 0.25),
            (S[0] + u * 1.9 * math.cos(a), S[1] + u * 1.9 * math.sin(a)))
        arm(O, (cx - sgn * u * 1.3, sh_y + u * 1.3), (cx - sgn * u * 1.0, hip - u * 0.2))
    else:  # happy / sad: relaxed
        arm(L, (cx - u * 1.35, sh_y + u * 1.2), (cx - u * 1.2, hip - u * 0.1))
        arm(R, (cx + u * 1.35, sh_y + u * 1.2), (cx + u * 1.2, hip - u * 0.1))
    # neck + head
    p.line([(hx, head_y + u * 0.95), (hx, sh_y + u * 0.2)], lw)
    p.circle(hx, head_y, u, width=lw, fill=PAPER)
    # hair tuft: three strokes
    for k, (dx, h) in enumerate(((-0.25, 0.55), (0.0, 0.7), (0.25, 0.5))):
        p.line([(hx + dx * u, head_y - u * 0.95), (hx + dx * u + u * 0.12 * (k - 1), head_y - u * (0.95 + h))],
               lw * 0.9)
    # glasses
    gy = head_y - u * 0.05
    for s in (-1, 1):
        p.circle(hx + s * u * 0.38, gy, u * 0.27, width=lw * 0.6)
    p.line([(hx - u * 0.11, gy), (hx + u * 0.11, gy)], lw * 0.5)
    # eyes
    ey = gy + (u * -0.06 if emotion == "thinking" else 0)
    ex_off = u * 0.06 if emotion == "thinking" else 0
    for s in (-1, 1):
        if emotion == "shocked":
            p.circle(hx + s * u * 0.38, ey, u * 0.08, width=lw * 0.45)
        elif emotion == "happy" or emotion == "cheering":
            p.line([(hx + s * u * 0.38 - u * 0.09, ey + u * 0.03), (hx + s * u * 0.38, ey - u * 0.05),
                    (hx + s * u * 0.38 + u * 0.09, ey + u * 0.03)], lw * 0.45)
        else:
            p.dot(hx + s * u * 0.38 + ex_off, ey, u * 0.065)
    # eyebrows: (raise of the inner end, raise of the outer end) per side; positive = up
    by = gy - u * 0.42
    brows = {"happy": ((0.06, 0.02),) * 2, "cheering": ((0.1, 0.05),) * 2, "worried": ((0.16, -0.04),) * 2,
             "sad": ((0.14, -0.06),) * 2, "shocked": ((0.2, 0.17),) * 2, "confident": ((0.0, 0.07),) * 2,
             "thinking": ((0.0, 0.0), (0.16, 0.2))}.get(emotion, ((0.0, 0.0),) * 2)
    for side, (inner, outer) in zip((-1, 1), brows):
        p.line([(hx + side * u * 0.2, by - u * inner), (hx + side * u * 0.38, by - u * (inner + outer) / 2 - u * 0.04),
                (hx + side * u * 0.56, by - u * outer)], lw * 0.55)
    # mouth
    my = head_y + u * 0.52
    if emotion in ("happy", "cheering"):
        p.circle(hx, my - u * 0.18, u * 0.3, width=lw * 0.6, start=20, sweep=140)
    elif emotion == "confident":
        p.line([(hx - u * 0.25, my), (hx + u * 0.05, my + u * 0.05), (hx + u * 0.3, my - u * 0.1)], lw * 0.6)
    elif emotion in ("worried", "sad"):
        p.circle(hx, my + u * 0.25, u * 0.25, width=lw * 0.6, start=210, sweep=120)
    elif emotion == "shocked":
        p.circle(hx, my + u * 0.02, u * 0.14, width=lw * 0.6, fill=INK)
    else:  # thinking
        p.line([(hx - u * 0.2, my + u * 0.02), (hx + u * 0.2, my - u * 0.04)], lw * 0.6)
    # extras
    if emotion == "worried":
        p.d.polygon([(hx + u * 1.05, head_y - u * 0.4), (hx + u * 0.95, head_y - u * 0.1),
                     (hx + u * 1.15, head_y - u * 0.1)], fill=(120, 170, 220))
    if emotion == "shocked":
        for k in (-1, 0, 1):
            p.line([(hx + k * u * 0.5, head_y - u * 1.75), (hx + k * u * 0.65, head_y - u * 2.2)], lw * 0.6)
    if emotion == "thinking":
        p.text((hx + u * 1.5, head_y - u * 1.3), "?", int(u * 1.1), INK)


def max_figure(emotion: str = "happy", u: float = 60.0, seed: int = 5) -> Image.Image:
    """Max alone on a transparent canvas (for compositing)."""
    w, h = int(u * 5.5), int(u * 9.6)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_max(img, w / 2, h - u * 0.3, u, emotion, seed)
    return img


# ------------------------------------------------------------------------------------------- icons
def icon(img: Image.Image, kind: str, cx: float, cy: float, s: float = 120.0, seed: int = 3) -> None:
    """Doodle icons (s = half size). Unknown kinds draw a coin stack."""
    p = Pen(img, seed=seed, width=max(4, s * 0.06), wobble=s * 0.015)
    lw = max(4, s * 0.06)
    if kind == "credit_card":
        p.poly([(cx - s, cy - s * 0.62), (cx + s, cy - s * 0.62), (cx + s, cy + s * 0.62), (cx - s, cy + s * 0.62)],
               fill=(250, 250, 246))
        p.d.rectangle((cx - s + lw, cy - s * 0.35, cx + s - lw, cy - s * 0.12), fill=INK)
        p.poly([(cx - s * 0.75, cy + s * 0.05), (cx - s * 0.4, cy + s * 0.05), (cx - s * 0.4, cy + s * 0.3),
                (cx - s * 0.75, cy + s * 0.3)], fill=GOLD, width=lw * 0.6)
        p.line([(cx + s * 0.05, cy + s * 0.38), (cx + s * 0.7, cy + s * 0.38)], lw * 0.6)
    elif kind == "house":
        p.poly([(cx - s * 0.8, cy - s * 0.1), (cx + s * 0.8, cy - s * 0.1), (cx + s * 0.8, cy + s * 0.85),
                (cx - s * 0.8, cy + s * 0.85)], fill=(250, 250, 246))
        p.poly([(cx - s * 1.0, cy - s * 0.05), (cx, cy - s * 0.95), (cx + s * 1.0, cy - s * 0.05)], fill=GREEN)
        p.poly([(cx - s * 0.2, cy + s * 0.35), (cx + s * 0.2, cy + s * 0.35), (cx + s * 0.2, cy + s * 0.85),
                (cx - s * 0.2, cy + s * 0.85)], fill=GOLD, width=lw * 0.7)
    elif kind == "bank":
        p.poly([(cx - s, cy - s * 0.35), (cx, cy - s * 0.95), (cx + s, cy - s * 0.35)], fill=GREEN)
        p.line([(cx - s * 0.9, cy - s * 0.22), (cx + s * 0.9, cy - s * 0.22)], lw)
        for k in range(4):
            x = cx - s * 0.7 + k * s * 0.47
            p.line([(x, cy - s * 0.2), (x, cy + s * 0.6)], lw)
        p.line([(cx - s, cy + s * 0.75), (cx + s, cy + s * 0.75)], lw * 1.3)
        p.text((cx, cy - s * 0.52), "$", int(s * 0.45), GOLD, bold=1)
    elif kind in ("coin_stack", "dollar_bill", "paycheck", "piggy_bank"):
        for k in range(4):
            y = cy + s * 0.6 - k * s * 0.3
            p.d.ellipse((cx - s * 0.6, y - s * 0.17, cx + s * 0.6, y + s * 0.17), fill=GOLD)
            p.line([(cx - s * 0.6, y), (cx - s * 0.6, y + s * 0.1), (cx + s * 0.6, y + s * 0.1), (cx + s * 0.6, y)],
                   lw * 0.6)
            p.d.ellipse((cx - s * 0.6, y - s * 0.17, cx + s * 0.6, y + s * 0.17), outline=INK, width=int(lw * 0.7))
        p.text((cx, cy - s * 0.32), "$", int(s * 0.3), INK, bold=1)
    elif kind in ("shield",):
        p.poly([(cx - s * 0.75, cy - s * 0.75), (cx, cy - s), (cx + s * 0.75, cy - s * 0.75),
                (cx + s * 0.6, cy + s * 0.3), (cx, cy + s), (cx - s * 0.6, cy + s * 0.3)], fill=GREEN)
        p.line([(cx - s * 0.35, cy), (cx - s * 0.08, cy + s * 0.3), (cx + s * 0.4, cy - s * 0.3)], lw * 1.2,
               color=(250, 250, 246))
    elif kind in ("calendar", "hourglass"):
        p.poly([(cx - s * 0.85, cy - s * 0.7), (cx + s * 0.85, cy - s * 0.7), (cx + s * 0.85, cy + s * 0.8),
                (cx - s * 0.85, cy + s * 0.8)], fill=(250, 250, 246))
        p.d.rectangle((cx - s * 0.85, cy - s * 0.7, cx + s * 0.85, cy - s * 0.35), fill=GREEN)
        for r_ in range(3):
            for c_ in range(4):
                p.line([(cx - s * 0.6 + c_ * s * 0.4, cy - s * 0.1 + r_ * s * 0.3),
                        (cx - s * 0.5 + c_ * s * 0.4, cy - s * 0.1 + r_ * s * 0.3)], lw * 0.8)
        p.circle(cx + s * 0.5, cy + s * 0.5, s * 0.16, width=lw * 0.6, color=GOLD)
    elif kind in ("warning",):
        p.poly([(cx, cy - s * 0.9), (cx + s, cy + s * 0.8), (cx - s, cy + s * 0.8)], fill=GOLD)
        p.line([(cx, cy - s * 0.3), (cx, cy + s * 0.3)], lw * 1.4)
        p.dot(cx, cy + s * 0.55, lw)
    elif kind in ("lightbulb", "target", "scale"):
        p.circle(cx, cy - s * 0.2, s * 0.6, width=lw, fill=(255, 236, 170))
        p.line([(cx - s * 0.25, cy + s * 0.45), (cx + s * 0.25, cy + s * 0.45)], lw)
        p.line([(cx - s * 0.2, cy + s * 0.62), (cx + s * 0.2, cy + s * 0.62)], lw)
        for a in range(5):
            ang = math.radians(200 + a * 35)
            p.line([(cx + s * 0.8 * math.cos(ang), cy - s * 0.2 + s * 0.8 * math.sin(ang)),
                    (cx + s * 1.0 * math.cos(ang), cy - s * 0.2 + s * 1.0 * math.sin(ang))], lw * 0.7)
    elif kind in ("growth_arrow",):
        p.arrow(cx - s, cy + s * 0.7, cx + s, cy - s * 0.7, lw * 1.4, GREEN, head=s * 0.35)
    elif kind in ("shopping_cart", "car"):
        p.poly([(cx - s * 0.9, cy - s * 0.1), (cx + s * 0.9, cy - s * 0.1), (cx + s * 0.9, cy + s * 0.45),
                (cx - s * 0.9, cy + s * 0.45)], fill=GREEN)
        p.poly([(cx - s * 0.5, cy - s * 0.1), (cx - s * 0.3, cy - s * 0.55), (cx + s * 0.35, cy - s * 0.55),
                (cx + s * 0.55, cy - s * 0.1)], fill=(250, 250, 246))
        for s_ in (-1, 1):
            p.circle(cx + s_ * s * 0.5, cy + s * 0.5, s * 0.22, width=lw, fill=INK)
    elif kind == "hospital":
        p.poly([(cx - s * 0.8, cy - s * 0.6), (cx + s * 0.8, cy - s * 0.6), (cx + s * 0.8, cy + s * 0.8),
                (cx - s * 0.8, cy + s * 0.8)], fill=(250, 250, 246))
        p.d.rectangle((cx - s * 0.12, cy - s * 0.4, cx + s * 0.12, cy + s * 0.3), fill=GREEN)
        p.d.rectangle((cx - s * 0.47, cy - s * 0.17, cx + s * 0.47, cy + s * 0.07), fill=GREEN)
    else:
        icon(img, "coin_stack", cx, cy, s, seed)


# ------------------------------------------------------------------------------------------- charts
def spike_chart(img: Image.Image, box, history=None, spike=None, seed: int = 11, labels: bool = False,
                title: str = "", weight: float = 1.0) -> None:
    """Hand-drawn axes, a grey history line and a green line that jumps up at the end (gold dot)."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    lw = max(5, w * 0.008) * weight
    p = Pen(img, seed=seed, width=lw, wobble=w * 0.0015)
    p.arrow(x0, y1, x0, y0, lw, head=w * 0.03)
    p.arrow(x0, y1, x1, y1, lw, head=w * 0.03)
    hist = history or [0.20, 0.24, 0.21, 0.25, 0.23, 0.27, 0.25, 0.28, 0.27, 0.30]
    sp = spike or [0.30, 0.48, 0.70, 0.95]
    n = len(hist) + len(sp) - 1
    xs = [x0 + w * 0.06 + w * 0.84 * k / n for k in range(n + 1)]
    ys = [y1 - h * 0.08 - h * 0.84 * v for v in hist + sp[1:]]
    base_y = y1 - lw
    hist_pts = list(zip(xs[:len(hist)], ys[:len(hist)]))
    spike_pts = list(zip(xs[len(hist) - 1:], ys[len(hist) - 1:]))
    tint = (lambda c: c + (255,)) if img.mode == "RGBA" else (lambda c: c)
    p.d.polygon(hist_pts + [(hist_pts[-1][0], base_y), (hist_pts[0][0], base_y)], fill=tint((214, 214, 208)))
    p.d.polygon(spike_pts + [(spike_pts[-1][0], base_y), (spike_pts[0][0], base_y)], fill=tint((190, 226, 203)))
    p.line(hist_pts, lw * 1.1, GREY)
    pts = list(zip(xs[len(hist) - 1:], ys[len(hist) - 1:]))
    p.line(pts, lw * 1.5, GREEN)
    p.dot(pts[-1][0], pts[-1][1], lw * 1.9, GOLD)
    p.circle(pts[-1][0], pts[-1][1], lw * 1.9, width=lw * 0.5)
    if title:
        p.text((x0 + w * 0.5, y0 - h * 0.02), title, int(h * 0.09), INK, anchor="ms")


def bar_chart(img: Image.Image, box, values: list[float], labels: list[str], seed: int = 13) -> None:
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    lw = max(5, w * 0.008)
    p = Pen(img, seed=seed, width=lw, wobble=w * 0.0015)
    p.line([(x0, y1), (x1, y1)], lw)
    top = max(values) or 1
    n = len(values)
    bw = w / (n * 1.6)
    for k, (v, lab) in enumerate(zip(values, labels)):
        bx = x0 + w * 0.08 + k * (w * 0.84 / n) + (w * 0.84 / n - bw) / 2
        bh = h * 0.78 * v / top
        col = GREEN if k == n - 1 else GREY
        p.poly([(bx, y1), (bx, y1 - bh), (bx + bw, y1 - bh), (bx + bw, y1)], fill=None, width=lw)
        p.hatch((bx + lw, y1 - bh + lw, bx + bw - lw, y1 - lw), col, gap=int(max(10, bw * 0.12)), width=int(lw * 0.7))
        if k == n - 1:
            p.dot(bx + bw / 2, y1 - bh - lw * 3, lw * 1.6, GOLD)
        if lab:
            p.text((bx + bw / 2, y1 + h * 0.08), lab[:14], int(h * 0.07), INK)


# ------------------------------------------------------------------------------------------- text helpers
def wrap(s: str, size: int, width: float) -> list[str]:
    words, lines, cur = s.split(), [], ""
    for wd in words:
        t = f"{cur} {wd}".strip()
        if hand(size).getlength(t) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def sparkle(p: Pen, x: float, y: float, r: float, color=GOLD) -> None:
    """A little 'look here' burst of four marker strokes."""
    for a in (-60, -20, 20, 60):
        ang = math.radians(a - 90)
        p.line([(x + r * 0.45 * math.cos(ang), y + r * 0.45 * math.sin(ang)),
                (x + r * math.cos(ang), y + r * math.sin(ang))], max(4, r * 0.09), color)


def underline(p: Pen, x0: float, x1: float, y: float, color=GREEN, width: float = 7.0) -> None:
    p.line([(x0, y), ((x0 + x1) / 2, y + 6), (x1, y - 2)], width, color)


# ------------------------------------------------------------------------------------------- thumbnail
ACRONYMS = {"IRS", "FDIC", "BNPL", "ACA", "IRA", "APR", "FICO", "401K", "401(K)", "US", "USA", "HSA", "CD", "ETF"}


def statement(words: str) -> str:
    """2-3 word bold statement ending with a period: 'debt wins' -> 'Debt Wins.'"""
    ws = [w.strip(",!?;:") for w in words.replace(".", " ").split() if w.strip(",!?;:")][:3] or ["Money", "Matters"]
    return " ".join(w.upper() if w.upper().strip("()") in ACRONYMS else
                    (w if any(c.isdigit() for c in w) else w.capitalize()) for w in ws) + "."


def thumbnail(text: str, emotion: str = "shocked", out: Path | None = None, seed: int = 1,
              size: tuple[int, int] = (1280, 720), history=None, spike=None,
              max_img: Image.Image | None = None) -> Image.Image:
    """Off-white paper, a 2-3 word statement ending with a period (huge), ONE simple chart (grey history line +
    green spike with a gold dot) and Max with an emotion. Drawn at 2x, saved at 1280x720. No numbers on the chart."""
    W2, H2 = size[0] * 2, size[1] * 2
    img = paper(W2, H2, seed=3 + seed).copy()
    p = Pen(img, seed=seed, width=12)
    st = statement(text)
    words = st.split()
    lines = [" ".join(words[:2]), " ".join(words[2:])] if len(words) == 3 else (
        [st] if hand(300).getlength(st) <= W2 * 0.58 else [words[0], " ".join(words[1:])])
    lines = [ln for ln in lines if ln]
    size_ = 420
    while size_ > 160 and (max(hand(size_).getlength(ln) for ln in lines) > W2 * 0.6 or
                           size_ * 0.92 * len(lines) > H2 * 0.5):
        size_ -= 10
    y = H2 * 0.06 + size_ * 0.5
    for ln in lines:
        p.text((W2 * 0.045, y), ln, size_, INK, anchor="lm", bold=max(6, size_ // 28))
        y += size_ * 0.92
    last_w = hand(size_).getlength(lines[-1])
    underline(p, W2 * 0.05, W2 * 0.05 + last_w * 0.97, y - size_ * 0.27, GREEN, 26)
    spike_chart(img, (W2 * 0.06, max(y, H2 * 0.6), W2 * 0.6, H2 * 0.94), history=history, spike=spike, seed=seed + 5,
                weight=2.0)
    if max_img is not None:   # the Nano Banana Max cutout (same file in every video)
        h = int(H2 * 0.96)
        s = h / max_img.height
        cut = max_img.resize((max(1, int(max_img.width * s)), h), Image.LANCZOS)
        if cut.width > W2 * 0.42:
            s2 = W2 * 0.42 / cut.width
            cut = cut.resize((int(cut.width * s2), int(cut.height * s2)), Image.LANCZOS)
        img.paste(cut, (int(W2 * 0.79 - cut.width / 2), H2 - cut.height + int(H2 * 0.04)), cut)
    else:
        draw_max(img, W2 * 0.8, H2 * 1.22, u=H2 * 0.125, emotion=emotion, seed=seed + 9)
    brand_mark(img, "tr", scale=2.2)
    out_img = finish(img, size)
    if out is not None:
        out_img.save(out, "JPEG", quality=92, optimize=True)
    return out_img


# ------------------------------------------------------------------------------------------- reference sheet
def reference_sheet(path: Path | None = None) -> Image.Image:
    """Max style reference sheet: the 7 emotions, the turnaround rules and the brand colors (for Nano Banana and
    for review). Deterministic: the same sheet every time."""
    W2, H2 = 3072, 2048
    img = paper(W2, H2, seed=21).copy()
    p = Pen(img, seed=2, width=8)
    p.text((W2 / 2, 110), "MAX  -  GLIVARAO MASCOT  -  STYLE REFERENCE", 96, INK, bold=2)
    underline(p, W2 * 0.2, W2 * 0.8, 175, GREEN, 10)
    for k, emo in enumerate(EMOTIONS):
        cx = 230 + k * 430
        draw_max(img, cx, 1250, u=95, emotion=emo, seed=5)
        p.text((cx, 1340), emo, 64, INK)
    rules = ["Round head, round glasses, three-hair tuft", "Green sweater (#1f8a4c) with a gold coin pin (#e0a526)",
             "Stick arms and legs, black marker lines, white face", "Off-white paper background, no shading, no real faces",
             "Same proportions in every video and thumbnail"]
    for k, r in enumerate(rules):
        p.text((140, 1520 + k * 82), "- " + r, 58, INK, anchor="lm")
    for k, (c, name) in enumerate(((GREEN, "deep green #1f8a4c"), (GOLD, "gold #e0a526"), (INK, "marker black"),
                                   (PAPER, "paper #f7f3e8"))):
        x = 1900 + (k % 2) * 600
        y = 1560 + (k // 2) * 200
        p.poly([(x, y), (x + 130, y), (x + 130, y + 130), (x, y + 130)], fill=c, width=6)
        p.text((x + 160, y + 65), name, 46, INK, anchor="lm")
    brand_mark(img, "br", scale=2.0)
    out = finish(img, (1536, 1024))
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        out.save(path, "PNG")
    return out


__all__ = ["sparkle", "paper", "Pen", "draw_max", "max_figure", "icon", "spike_chart", "bar_chart", "thumbnail",
           "reference_sheet", "brand_mark", "statement", "wrap", "hand", "EMOTIONS", "GREEN", "GOLD", "INK", "PAPER",
           "GREY", "VERSION"]
