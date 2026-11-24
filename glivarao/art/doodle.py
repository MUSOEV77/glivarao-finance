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
                title: str = "", weight: float = 1.0) -> dict:
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
    return {"end": pts[-1], "start_x": xs[0], "base_y": y1, "dot_r": lw * 1.9}


def series_chart(img: Image.Image, box, values: list[float], seed: int = 11, weight: float = 1.0) -> dict:
    """Real data only: one point per value, evenly spaced across the full width, y axis from ZERO (no exaggerated
    trend), grey line for the earlier points, green for the last step, gold dot on the latest value."""
    x0, y0, x1, y1 = box
    w = x1 - x0
    lw = max(5, w * 0.008) * weight
    p = Pen(img, seed=seed, width=lw, wobble=w * 0.0015)
    p.arrow(x0, y1, x0, y0, lw, head=w * 0.03)
    p.arrow(x0, y1, x1, y1, lw, head=w * 0.03)
    pts = series_points_xy(box, values)
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
    tint = (lambda c: c + (255,)) if img.mode == "RGBA" else (lambda c: c)
    p.d.polygon(pts + [(xs[-1], y1 - lw), (xs[0], y1 - lw)], fill=tint((214, 214, 208)))
    p.line(pts[:-1], lw * 1.2, GREY)
    p.line(pts[-2:], lw * 1.5, GREEN)
    for x, y in pts[:-1]:
        p.dot(x, y, lw * 1.1, GREY)
    p.dot(pts[-1][0], pts[-1][1], lw * 1.9, GOLD)
    p.circle(pts[-1][0], pts[-1][1], lw * 1.9, width=lw * 0.5)
    return {"end": pts[-1], "start_x": xs[0], "base_y": y1, "dot_r": lw * 1.9, "line_top": min(ys),
            "line_bottom": max(ys), "points": pts}


def series_points_xy(box, values: list[float]) -> list[tuple[float, float]]:
    """Where series_chart puts each value (evenly spaced, axis from zero)."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    top = max(values) or 1.0
    n = max(1, len(values) - 1)
    return [(x0 + w * 0.08 + w * 0.8 * k / n, y1 - h * 0.85 * v / top) for k, v in enumerate(values)]


def _hits_line(box, pts, margin: float) -> bool:
    x0, y0, x1, y1 = box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        for k in range(41):
            x, y = ax + (bx - ax) * k / 40, ay + (by - ay) * k / 40
            if x0 <= x <= x1 and y0 <= y <= y1:
                return True
    return False


def free_spot(cbox, pts, text: str, start: int, smallest: int, margin: float):
    """Largest pill size and position inside the chart box that doesn't touch the line: (vs, x0, y0, w, h)."""
    x0, y0, x1, y1 = cbox
    for vs in range(start, smallest - 1, -4):
        w = hand(vs).getlength(text) + vs * 0.7
        h = vs * 1.41
        ins = margin
        for cx, cy in ((x0 + ins, y0 + ins), ((x0 + x1 - w) / 2, y0 + ins), (x1 - w - ins, y1 - h - ins),
                       ((x0 + x1 - w) / 2, y1 - h - ins), (x0 + ins + w * 0.1, (y0 + y1 - h) / 2),
                       (x1 - w - ins, y0 + ins), (x0 + ins, y1 - h - ins)):
            b = (cx, cy, cx + w, cy + h)
            if b[0] >= x0 and b[2] <= x1 and b[1] >= y0 and b[3] <= y1 and not _hits_line(b, pts, margin):
                return vs, cx, cy, w, h
    return None


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
    """2-4 word bold statement ending with a period: 'debt wins' -> 'Debt Wins.' Never cut: the caller passes a
    complete headline (ai_visuals.bold_words checks it)."""
    ws = [w.strip(",!?;:") for w in words.replace(".", " ").split() if w.strip(",!?;:")] or ["Money", "Matters"]
    return " ".join(w.upper() if w.upper().strip("()") in ACRONYMS else
                    (w if any(c.isdigit() for c in w) else w.capitalize()) for w in ws) + "."


THUMB_PAPER = (236, 222, 192)        # warmer, slightly darker paper than the video frames
THUMB_PANEL = (205, 231, 212)        # soft green panel behind the chart
THUMB_BG = {"cream": (THUMB_PAPER, INK), "mint": ((222, 239, 227), INK),             # simple LIGHT backgrounds
            "gold": ((250, 236, 198), INK), "white": ((250, 248, 243), INK)}         # (background, text)
THUMB_LAYOUTS = ("max_right", "panel_top_left", "max_left", "panel_top")
TOPIC_PROP = {"credit_card": "credit_card", "debt_payoff": "credit_card", "bnpl": "credit_card",
              "aca_marketplace": "hospital", "insurance": "hospital", "medical_debt": "hospital",
              "us_housing": "house", "mortgage": "house", "rent_vs_buy": "house", "emergency_fund": "piggy_bank",
              "hysa": "piggy_bank", "ira_roth": "coin_stack", "retirement_401k": "coin_stack",
              "fed_rates": "bank", "us_banks": "bank", "credit_score": "shield", "student_loan": "calendar"}


def thumb_style(n: int) -> tuple[str, str]:
    """(background color, layout) for long video n: never the same color or layout twice in a row."""
    return list(THUMB_BG)[n % 4], THUMB_LAYOUTS[(n + n // 4) % 4]


def _contrast(c1, c2) -> float:
    """WCAG contrast ratio between two RGB colours."""
    def lum(c):
        v = [x / 255 for x in c[:3]]
        v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
    a, b = sorted((lum(c1), lum(c2)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def thumbnail(text: str, emotion: str = "shocked", out: Path | None = None, seed: int = 1,
              size: tuple[int, int] = (1280, 720), history=None, spike=None,
              max_img: Image.Image | None = None, value: str = "", start_year: str = "", end_year: str = "",
              info: dict | None = None, points: list | None = None, layout: str = "max_right",
              palette: str = "cream", scene_bg: Image.Image | None = None, prop: str = "",
              visual: str = "", pair: tuple | None = None) -> Image.Image:
    """Warm paper, a complete 2-4 word statement ending with a period (huge), a soft green panel and Max with an
    emotion. Drawn at 2x, saved at 1280x720. `info` receives the text boxes (in output pixels) for the readability
    test.

    The panel never implies a trend we don't have:
    * `points` = 3 or more real (year, value) data points from the fact sheet -> a line chart of exactly those
      values (axis from zero), first and last year under it, the latest value in gold at the end;
    * otherwise -> ONE big number badge (e.g. '22.36% APR'), no line, no years. (`start_year`/`end_year` are
      ignored: two years around one number would suggest a trend.)
    * no number at all -> no panel.
    Layouts (rotated so consecutive videos differ): 'max_right' (statement top-left, panel below, Max right),
    'max_left' (the mirror: Max left), 'panel_top' (panel on top, statement under it, Max right), 'panel_top_left'
    (panel_top mirrored: Max left). palette: cream / green / gold / dark background; scene_bg: the topic's scene,
    faded behind; prop: a topic object Max holds (credit_card, hospital, house, coin_stack, ...)."""
    W2, H2 = size[0] * 2, size[1] * 2
    bg_col, ink = THUMB_BG.get(palette, THUMB_BG["cream"])
    img = Image.blend(paper(W2, H2, seed=3 + seed).copy(), Image.new("RGB", (W2, H2), bg_col),
                      0.6 if palette == "cream" else 0.92)
    if scene_bg is not None:              # the topic's scene, faded so text and Max stay readable
        sc = scene_bg.convert("RGB").resize((W2, H2), Image.LANCZOS)
        img = Image.blend(img, sc, 0.22)
    p = Pen(img, seed=seed, width=12)
    boxes = {"statement": [], "value": None, "years": []}
    st = statement(text)
    words = st.split()
    lines = [" ".join(words[:2]), " ".join(words[2:])] if len(words) in (3, 4) else (
        [st] if hand(300).getlength(st) <= W2 * 0.58 else [words[0], " ".join(words[1:])])
    lines = [ln for ln in lines if ln]
    size_ = 420
    while size_ > 160 and (max(hand(size_).getlength(ln) for ln in lines) > W2 * 0.58 or
                           size_ * 0.92 * len(lines) > H2 * 0.38):
        size_ -= 10
    pts = [(str(yr), float(v)) for yr, v in (points or [])]
    chart_ok = len(pts) >= 3
    if visual in ("bars", "before_after") and not pair:
        visual = ""
    has_panel = chart_ok or bool(value) or visual in ("bars", "before_after")
    ox = W2 * 0.355 if layout in ("max_left", "panel_top_left") else 0.0     # text + panel column offset
    stmt_h = size_ * 0.92 * len(lines)
    if layout in ("panel_top", "panel_top_left") and has_panel:
        y = H2 * 0.925 - stmt_h + size_ * 0.42                # statement at the bottom, panel above it
    else:
        y = H2 * 0.05 + size_ * 0.5
    y_first = y
    for ln in lines:
        p.text((ox + W2 * 0.045, y), ln, size_, ink, anchor="lm", bold=max(6, size_ // 28))
        boxes["statement"].append(p.d.textbbox((ox + W2 * 0.045, y), ln, font=hand(size_), anchor="lm",
                                               stroke_width=max(6, size_ // 28)))
        y += size_ * 0.92
    last_w = hand(size_).getlength(lines[-1])
    underline(p, ox + W2 * 0.05, ox + W2 * 0.05 + last_w * 0.97, y - size_ * 0.27,
              GOLD if palette in ("green", "dark") else GREEN, 26)
    if has_panel:
        # soft coloured panel (with a shadow), so the chart / number stands out on YouTube
        if layout in ("panel_top", "panel_top_left"):
            px0, py0, px1, py1 = ox + W2 * 0.035, H2 * 0.04, ox + W2 * 0.6, y_first - size_ * 0.62
        else:
            px0, py0, px1, py1 = (ox + W2 * 0.035, max(y - size_ * 0.27 + H2 * 0.03, H2 * 0.44), ox + W2 * 0.6,
                                  H2 * 0.965)
        sh = Image.new("L", (W2, H2), 0)
        ImageDraw.Draw(sh).rounded_rectangle((px0 + 16, py0 + 20, px1 + 16, py1 + 20), 40, fill=90)
        from PIL import ImageFilter

        img.paste((60, 40, 20), (0, 0), sh.filter(ImageFilter.GaussianBlur(18)))
        p.d.rounded_rectangle((px0, py0, px1, py1), 40, fill=PAPER if palette == "green" else THUMB_PANEL,
                              outline=INK, width=10)
    if visual in ("bars", "before_after"):        # a real before/after pair from ONE fact on the sheet
        b_val, b_lab, a_val, a_lab = pair
        pw, ph = px1 - px0, py1 - py0
        if visual == "bars":                       # two bars, real heights (axis from zero), values on top
            bv, av = _amount(b_val), _amount(a_val)
            top = max(bv, av) or 1.0
            base = py1 - ph * 0.17
            bw = pw * 0.3
            for k, (v, lab, txt) in enumerate(((bv, b_lab, b_val), (av, a_lab, a_val))):
                bx = px0 + pw * (0.1 if k == 0 else 0.6)
                bh = (ph * 0.34) * v / top
                p.d.rectangle((bx, base - bh, bx + bw, base), fill=GREY if k == 0 else GREEN, outline=INK, width=8)
                vs = int(ph * 0.31)
                while vs > ph * 0.12 and hand(vs).getlength(txt) > pw * 0.48:
                    vs -= 4
                p.d.text((bx + bw / 2, base - bh - vs * 0.15), txt, font=hand(vs), fill=INK, anchor="mb",
                         stroke_width=2, stroke_fill=INK)
                p.d.text((bx + bw / 2, base + ph * 0.04), lab[:16], font=hand(int(ph * 0.09)), fill=INK, anchor="mt")
                if k == 1:
                    boxes["value"] = p.d.textbbox((bx + bw / 2, base - bh - vs * 0.15), txt, font=hand(vs),
                                                  anchor="mb", stroke_width=2)
        else:                                       # big before -> after numbers, a drawn arrow between them
            vs = int(ph * 0.3)
            gap = pw * 0.16
            while vs > ph * 0.12 and hand(vs).getlength(b_val) + hand(vs).getlength(a_val) + gap > pw * 0.92:
                vs -= 4
            bw_, aw_ = hand(vs).getlength(b_val), hand(vs).getlength(a_val)
            x = (px0 + px1 - (bw_ + aw_ + gap)) / 2
            cy = py0 + ph * 0.45
            p.d.text((x, cy), b_val, font=hand(vs), fill=GREY, anchor="lm", stroke_width=2, stroke_fill=GREY)
            p.arrow(x + bw_ + gap * 0.15, cy, x + bw_ + gap * 0.85, cy, max(8, vs * 0.06), head=gap * 0.25)
            p.d.text((x + bw_ + gap, cy), a_val, font=hand(vs), fill=INK, anchor="lm", stroke_width=3,
                     stroke_fill=INK)
            boxes["value"] = p.d.textbbox((x + bw_ + gap, cy), a_val, font=hand(vs), anchor="lm", stroke_width=3)
            ls = int(ph * 0.11)
            p.d.text((x + bw_ / 2, cy + vs * 0.7), b_lab[:16], font=hand(ls), fill=GREEN, anchor="mt")
            p.d.text((x + bw_ + gap + aw_ / 2, cy + vs * 0.7), a_lab[:16], font=hand(ls), fill=GREEN, anchor="mt")
        chart_ok = False
        value = ""
    if chart_ok:          # a line chart ONLY with >= 3 real data points (axis from zero: no exaggeration)
        ys = int(H2 * 0.092)                    # year labels
        cbox = (px0 + W2 * 0.035, py0 + H2 * 0.045, px1 - W2 * 0.03, py1 - ys * 1.3)
        vals = [v for _, v in pts]
        readable = int(H2 * 0.145)            # the number stays readable at phone size (160x90)
        g = lw_gap(W2)

        def spot_for(cb):
            return free_spot((cb[0] + g * 2, cb[1], cb[2], cb[3] - g), series_points_xy(cb, vals), value,
                             int(H2 * 0.17), readable, g) if value else None

        spot = spot_for(cbox)
        side = None
        if value and spot is None:            # no free space on the plot: the number gets its own row on top
            vs = int(H2 * 0.15)
            while vs > H2 * 0.09 and hand(vs).getlength(value) + vs * 0.7 > (px1 - px0) * 0.9:
                vs -= 4
            sw, sh_ = hand(vs).getlength(value) + vs * 0.7, vs * 1.41
            side = (vs, px0 + W2 * 0.03, py0 + H2 * 0.025, sw, sh_)
            cbox = (cbox[0], py0 + H2 * 0.025 + sh_ + H2 * 0.03, cbox[2], cbox[3])
        chart = series_chart(img, cbox, vals, seed=seed + 5, weight=2.0)
        ex, ey = chart["end"]
        for yr, x in ((pts[0][0], chart["start_x"]), (pts[-1][0], ex)):
            yy = chart["base_y"] + ys * 0.15
            p.d.text((x, yy), yr, font=hand(ys), fill=INK, anchor="mt", stroke_width=2, stroke_fill=INK)
            boxes["years"].append(p.d.textbbox((x, yy), yr, font=hand(ys), anchor="mt", stroke_width=2))
        if value and (spot or side):          # the latest real value in gold, never on the line
            vs, bx0, by0, bw_, bh_ = spot or side
            f = hand(vs)
            p.d.rounded_rectangle((bx0, by0, bx0 + bw_, by0 + bh_), int(bh_ * 0.3), fill=INK)
            p.d.text((bx0 + bw_ / 2, by0 + bh_ / 2), value, font=f, fill=GOLD, anchor="mm", stroke_width=3,
                     stroke_fill=GOLD)
            boxes["value"] = p.d.textbbox((bx0 + bw_ / 2, by0 + bh_ / 2), value, font=f, anchor="mm",
                                          stroke_width=3)
    elif value:           # ONE number: a big badge only (no line, no years: one number is not a trend)
        vs = int(H2 * 0.2)
        while vs > H2 * 0.08 and hand(vs).getlength(value) + vs * 0.9 > (px1 - px0) * 0.9:
            vs -= 4
        f = hand(vs)
        tw = f.getlength(value)
        padx, pady = vs * 0.45, vs * 0.22
        bw_, bh_ = tw + 2 * padx, vs * 1.05 + 2 * pady
        cx, cy = (px0 + px1) / 2, (py0 + py1) / 2
        p.d.rounded_rectangle((cx - bw_ / 2, cy - bh_ / 2, cx + bw_ / 2, cy + bh_ / 2), int(bh_ * 0.3), fill=INK)
        p.d.text((cx, cy), value, font=f, fill=GOLD, anchor="mm", stroke_width=3, stroke_fill=GOLD)
        boxes["value"] = p.d.textbbox((cx, cy), value, font=f, anchor="mm", stroke_width=3)
    if max_img is not None:   # the Nano Banana Max cutout (same file in every video)
        h = int(H2 * 0.96)
        s = h / max_img.height
        cut = max_img.resize((max(1, int(max_img.width * s)), h), Image.LANCZOS)
        if cut.width > W2 * 0.4:
            s2 = W2 * 0.4 / cut.width
            cut = cut.resize((int(cut.width * s2), int(cut.height * s2)), Image.LANCZOS)
        mx = 0.2 if layout in ("max_left", "panel_top_left") else 0.8
        img.paste(cut, (int(W2 * mx - cut.width / 2), H2 - cut.height + int(H2 * 0.04)), cut)
    else:
        draw_max(img, W2 * (0.2 if layout in ("max_left", "panel_top_left") else 0.8), H2 * 1.22, u=H2 * 0.125,
                 emotion=emotion, seed=seed + 9)
    left = layout in ("max_left", "panel_top_left")
    if prop:                              # the topic object Max holds (in front of his hand / chest)
        mxc = W2 * (0.2 if left else 0.8)
        icon(img, prop, mxc + (W2 * 0.11 if left else -W2 * 0.11), H2 * 0.62, s=H2 * 0.11, seed=seed + 3)
    brand_mark(img, "tl" if left else "tr", scale=2.2)
    out_img = finish(img, size)
    if info is not None:
        k = size[0] / W2
        sc = lambda b: tuple(round(v * k) for v in b)  # noqa: E731
        info.update({"statement": [sc(b) for b in boxes["statement"]],
                     "value": sc(boxes["value"]) if boxes["value"] else None,
                     "years": [sc(b) for b in boxes["years"]],
                     "contrast_statement": _contrast(ink, bg_col), "contrast_value": _contrast(GOLD, INK) if visual not in ("bars", "before_after") else
                     _contrast(INK, THUMB_PANEL),
                     "contrast_years": _contrast(INK, THUMB_PANEL)})
    if out is not None:
        out_img.save(out, "JPEG", quality=92, optimize=True)
    return out_img


def compact_number(s: str) -> str:
    """'$1,368.5 billion' -> '$1.4T', '$19.1 trillion' -> '$19.1T', '$208 billion' -> '$208B', '$400,400' -> '$400K',
    '22.36%' -> '22.36%'."""
    import re as _re

    t = s.strip()
    if "%" in t or "percent" in t.lower():
        return _re.sub(r"\s*percent", "%", t, flags=_re.I).replace(" %", "%")
    m = _re.search(r"([\d,]+(?:\.\d+)?)\s*(trillion|billion|million|thousand)?", t, _re.I)
    if not m:
        return t
    v = float(m.group(1).replace(",", "")) * {"trillion": 1e12, "billion": 1e9, "million": 1e6,
                                               "thousand": 1e3}.get((m.group(2) or "").lower(), 1)
    cur = "$" if "$" in t else ""
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= div:
            x = v / div
            return f"{cur}{x:.1f}{suf}".replace(".0" + suf, suf) if x < 100 else f"{cur}{x:.0f}{suf}"
    return f"{cur}{v:g}"


def key_number(texts: list[str], today_year: int) -> tuple[str, str, str]:
    """(value, start year, end year) for the thumbnail chart from the video's verified facts: the first fact with
    a dollar amount or percentage; end year = the latest year it names (else this year); start year = the earliest
    other year it names, or the year before for 'a year earlier'."""
    import re as _re

    from ..render.doodle import NUM

    for t in texts:
        m = NUM.search(t)
        if not m:
            continue
        years = sorted({int(y) for y in _re.findall(r"\b(?:19|20)\d{2}\b", t)})
        end = years[-1] if years else today_year
        start = years[0] if years and years[0] < end else (end - 1 if _re.search(r"a year (?:earlier|ago)", t)
                                                           else None)
        return compact_number(m.group(0)), str(start) if start else "", str(end)
    return "", "", ""


def lw_gap(width: float) -> float:
    return width * 0.012


def badge_text(fact: str, value: str) -> str:
    """'22.36%' from a credit card interest fact -> '22.36% APR' (only when the fact says it is a card rate)."""
    import re as _re

    if value.endswith("%") and _re.search(r"credit card", fact, _re.I) and \
            _re.search(r"\b(?:interest|APR|annual percentage rate|rate)\b", fact, _re.I):
        return f"{value} APR"
    return value


_PAIR = [r"(?P<v>{num})\s+(?:in|for|during|at the end of)\s+(?P<y>(?:19|20)\d{{2}})",
         r"(?P<y>(?:19|20)\d{{2}})\s*[:=(]\s*(?P<v>{num})",
         r"\bin\s+(?P<y>(?:19|20)\d{{2}}),?\s+(?:\w+\s+){{0,6}}?(?P<v>{num})"]


def _amount(s: str) -> float:
    import re as _re

    m = _re.search(r"([\d,]+(?:\.\d+)?)\s*(trillion|billion|million|thousand)?", s, _re.I)
    return float(m.group(1).replace(",", "")) * {"trillion": 1e12, "billion": 1e9, "million": 1e6,
                                                 "thousand": 1e3}.get((m.group(2) or "").lower(), 1)


def series_points(facts: list, unit_out: list | None = None) -> list[tuple[str, float]]:
    """Real (year, value) data points stated in the fact sheet for ONE measure (same source, same unit).
    `facts`: (text, url) pairs. Returns the longest such series, sorted by year (may be shorter than 3)."""
    import re as _re

    from ..render.doodle import NUM

    groups: dict = {}
    for text, url in facts:
        for pat in _PAIR:
            for m in _re.finditer(pat.format(num=NUM.pattern), text, _re.I):
                v = m.group("v")
                unit = "%" if ("%" in v or "percent" in v.lower()) else "$"
                groups.setdefault((url, unit), {}).setdefault(m.group("y"), _amount(v))
    if not groups:
        return []
    key = max(groups, key=lambda k: len(groups[k]))
    if unit_out is not None:
        unit_out.append(key[1])
    return sorted(groups[key].items())


def surprising_number(facts: list) -> tuple[str, str]:
    """(number, its fact) to put in the badge: the most surprising figure on the fact sheet, never a range bound
    ('between 100% and 400%') or a plain 100%. Big dollar totals and exact rates beat round numbers."""
    import re as _re

    from ..render.doodle import NUM

    best, best_score = ("", ""), -1
    for k, (text, _url) in enumerate(facts):
        for m in NUM.finditer(text):
            v, before = m.group(0), text[max(0, m.start() - 9):m.start()].lower()
            amt = _amount(v)
            pct = "%" in v or "percent" in v.lower()
            if pct and amt in (100.0, 400.0) or "between" in before or _re.match(r"\s*(?:and|to)\s+\$?\d", text[m.end():]):
                continue
            if _re.search(r"trillion|billion|million", v, _re.I):
                score = 5
            elif pct and "." in v:
                score = 4
            elif "$" in v and amt >= 1000:
                score = 3
            elif pct:
                score = 2
            else:
                score = 1
            score -= k * 0.01                     # ties: the earlier (lead) fact
            if score > best_score:
                best, best_score = (v, text), score
    return best


def value_pair(facts: list) -> tuple | None:
    """(before, before label, after, after label) when ONE fact states a change: 'X, up from Y a year earlier',
    'to X, up from Y for 2026'. Only numbers written in that fact."""
    import re as _re

    from ..render.doodle import NUM

    for text, _url in facts:
        m = _re.search(r"(?P<a>" + NUM.pattern + r")[^.;]{0,30}?\b(?:up|down) from (?P<b>" + NUM.pattern +
                       r")(?P<lab>(?: [a-z0-9]+){0,3})", text, _re.I)
        if m:
            lab = m.group("lab").strip() or "before"
            lab = _re.sub(r"^(?:for|in) ", "", lab)
            yr = _re.search(r"\b(20\d\d)\b", lab)
            after = str(int(yr.group(1)) + 1) if yr else "now"
            return m.group("b"), lab, m.group("a"), after
    return None


def thumb_data(facts: list, today_year: int) -> dict:
    """What the thumbnail panel may show, from the verified facts ((text, url) pairs): 'value' (the key number,
    as a badge) and 'points' (a line chart only with >= 3 real data points)."""
    value, _, _ = key_number([t for t, _ in facts], today_year)
    unit: list = []
    pts = series_points(facts, unit)
    if len(pts) >= 3:     # the chart's own latest value goes in the gold pill
        v = pts[-1][1]
        return {"value": f"{v:g}%" if unit[0] == "%" else compact_number(f"${v:,.2f}"), "points": pts}
    num, src = surprising_number(facts)
    if num:
        pct = "%" in num or "percent" in num.lower()
        value = compact_number(num) if pct or _amount(num) >= 100000 else num
    return {"value": badge_text(src, value) if value else "", "points": pts if len(pts) >= 3 else [],
            "pair": value_pair(facts)}


def visual_options(data: dict) -> list[str]:
    """The real visuals this fact sheet supports (never invented): line (3+ points), bars / before_after (a
    stated change), badge (one number)."""
    out = (["line"] if data.get("points") else []) + (["bars", "before_after"] if data.get("pair") else [])
    return out + (["badge"] if data.get("value") else [])


def phone_readability(info: dict, size: tuple[int, int] = (1280, 720), phone=(160, 90)) -> list[str]:
    """Problems reading the thumbnail on a phone (YouTube shows it about 160x90). Text heights are scaled to the
    phone size: statement >= 12 px, number >= 8 px, years >= 5 px; contrast >= 7:1 (statement), 4.5:1 (others)."""
    k = phone[1] / size[1]
    probs = []
    if info["statement"] and min(b[3] - b[1] for b in info["statement"]) * k < 12:
        probs.append("statement too small on a phone")
    if info.get("value") and (info["value"][3] - info["value"][1]) * k < 8:
        probs.append("number too small on a phone")
    if info.get("years") and min(b[3] - b[1] for b in info["years"]) * k < 5:
        probs.append("years too small on a phone")
    if info["contrast_statement"] < 7:
        probs.append(f"statement contrast {info['contrast_statement']:.1f}:1")
    if info["contrast_value"] < 4.5:
        probs.append(f"number contrast {info['contrast_value']:.1f}:1")
    if info["contrast_years"] < 4.5:
        probs.append(f"years contrast {info['contrast_years']:.1f}:1")
    return probs


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


__all__ = ["compact_number", "key_number", "phone_readability", "THUMB_PAPER", "THUMB_PANEL", "sparkle", "paper", "Pen", "draw_max", "max_figure", "icon", "spike_chart", "bar_chart", "thumbnail",
           "reference_sheet", "brand_mark", "statement", "wrap", "hand", "EMOTIONS", "GREEN", "GOLD", "INK", "PAPER",
           "GREY", "VERSION"]


HOOK_EMOTION = {"number": "shocked", "mistake": "worried", "warning": "worried", "myth": "shocked",
                "story": "worried", "comparison": "shocked", "question": "thinking"}


def cover(text: str, palette: str = "green", layout: str = "text_top", max_img: Image.Image | None = None,
          size: tuple[int, int] = (1080, 1920), emotion: str = "shocked", number: str = "") -> Image.Image:
    """Shorts frame 1: flat high-contrast background, a BIG complete 2-4 word hook, the key number BIG in a pill
    (when the script has one), and Max LARGE head-to-knees filling a contrasting disc. Never happy/cheering."""
    from ..studio.variety import COVER_PALETTES

    if emotion in ("happy", "cheering", "explaining"):
        emotion = "shocked"
    bg, ink, accent = COVER_PALETTES.get(palette, COVER_PALETTES["green"])
    W2, H2 = size[0] * 2, size[1] * 2
    img = Image.new("RGB", (W2, H2), bg)
    p = Pen(img, seed=7, width=12)
    words = statement(text).split()
    splits = [[" ".join(words[:k]), " ".join(words[k:])] for k in range(1, len(words))] or [[" ".join(words)]]
    lines = min(splits, key=lambda ls: max(hand(100).getlength(x) for x in ls)) if len(words) > 2 else [" ".join(words)]
    lines = [ln for ln in lines if ln]
    sz = 560
    while sz > 140 and (max(hand(sz).getlength(ln) for ln in lines) > W2 * 0.88 or sz * 1.02 * len(lines) > H2 * 0.27):
        sz -= 10
    align = {"text_left": "l", "text_right": "r"}.get(layout, "c")
    y = H2 * 0.05
    for ln in lines:
        w = hand(sz).getlength(ln)
        x = {"l": W2 * 0.06, "r": W2 * 0.94 - w}.get(align, (W2 - w) / 2)
        p.text((x, y + sz * 0.5), ln, sz, ink, anchor="lm", bold=max(8, sz // 22))
        y += sz * 1.02
    if number:                                            # the key number, big, in a dark/gold pill
        ns = int(H2 * 0.1)
        while ns > H2 * 0.05 and hand(ns).getlength(number) + ns > W2 * 0.8:
            ns -= 6
        nw, nh = hand(ns).getlength(number) + ns * 0.9, ns * 1.35
        nx = {"l": W2 * 0.06, "r": W2 * 0.94 - nw}.get(align, (W2 - nw) / 2)
        ny = y + H2 * 0.01
        pill, txt = ((26, 26, 26), GOLD) if palette != "dark" else (GOLD, (26, 26, 26))
        p.d.rounded_rectangle((nx, ny, nx + nw, ny + nh), int(nh * 0.3), fill=pill)
        p.d.text((nx + nw / 2, ny + nh / 2), number, font=hand(ns), fill=txt, anchor="mm", stroke_width=3,
                 stroke_fill=txt)
        y = ny + nh
    else:
        ux = {"l": W2 * 0.06, "r": W2 * 0.54}.get(align, W2 * 0.3)
        p.d.rounded_rectangle((ux, y + 10, ux + W2 * 0.4, y + 34), 12, fill=accent)
        y += 40
    r = min(H2 - y - H2 * 0.04, W2 * 0.92) / 2            # the disc fills the space left: no empty band
    cx = {"l": 0.58, "r": 0.42}.get(align, 0.5) * W2
    cy = H2 - r - H2 * 0.02
    dc = (247, 238, 214) if palette != "cream" else (31, 138, 76)
    p.d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=dc)
    if max_img is not None:                               # head to knees (top 75% of the cutout), filling the disc
        crop = max_img.crop((0, 0, max_img.width, int(max_img.height * 0.75)))
        h = int(r * 2.05)
        s_ = h / crop.height
        cut = crop.resize((max(1, int(crop.width * s_)), h), Image.LANCZOS)
        if cut.width > W2 * 0.95:
            k = W2 * 0.95 / cut.width
            cut = cut.resize((int(cut.width * k), int(cut.height * k)), Image.LANCZOS)
        img.paste(cut, (int(cx - cut.width / 2), int(cy + r - cut.height + r * 0.06)), cut)
    else:
        draw_max(img, cx, cy + r * 1.45, u=r * 0.38, emotion=emotion, seed=11)
    return finish(img, size)
