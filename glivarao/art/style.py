"""Hand-drawn rendering primitives: wobbly ink lines, paper texture, palette, fonts.

Every shape is jittered with smooth seeded noise. Rendering the same frame with a different
`boil` seed produces the subtle "line boil" of hand-drawn animation.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONT_HAND = ROOT / "assets/fonts/PatrickHand-Regular.ttf"
FALLBACK_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]

PALETTE = {
    "paper": (247, 241, 227),
    "paper_dark": (233, 224, 204),
    "ink": (38, 34, 46),
    "green": (46, 139, 87),
    "green_light": (152, 214, 168),
    "copper": (205, 127, 50),
    "copper_light": (236, 178, 112),
    "gold": (242, 190, 60),
    "blue": (58, 110, 186),
    "blue_light": (156, 192, 236),
    "red": (214, 76, 66),
    "red_light": (246, 160, 148),
    "skin": (241, 196, 160),
    "skin_shade": (222, 166, 128),
    "hair": (92, 60, 40),
    "white": (255, 253, 247),
    "sticky": (255, 226, 120),
    "grey": (150, 146, 140),
}
SERIES = ["green", "blue", "copper", "red", "gold"]


@lru_cache(maxsize=64)
def font(size: int) -> ImageFont.FreeTypeFont:
    for p in [FONT_HAND, *FALLBACK_FONTS]:
        try:
            return ImageFont.truetype(str(p), size)
        except OSError:
            continue
    return ImageFont.load_default(size)


class Ink:
    """Drawing context that jitters every stroke for a hand-drawn look."""

    def __init__(self, img: Image.Image, seed: int = 0, wobble: float = 2.2, width: int = 5):
        self.img = img
        self.d = ImageDraw.Draw(img)
        self.seed = seed
        self.wobble = wobble
        self.width = width
        self._n = 0

    # -- noise --------------------------------------------------------------
    def _rng(self) -> random.Random:
        self._n += 1
        return random.Random(self.seed * 7919 + self._n * 104729)

    def jitter(self, pts: list[tuple[float, float]], closed: bool = False, amount: float | None = None):
        amount = self.wobble if amount is None else amount
        if len(pts) < 2 or amount <= 0:
            return pts
        dense = densify(pts + ([pts[0]] if closed else []), step=14)
        rng = self._rng()
        f1, f2 = rng.uniform(0.03, 0.07), rng.uniform(0.1, 0.18)
        p1, p2, p3, p4 = (rng.uniform(0, 6.28) for _ in range(4))
        out = []
        for i, (x, y) in enumerate(dense):
            out.append((x + amount * (math.sin(i * f1 + p1) + 0.4 * math.sin(i * f2 + p2)),
                        y + amount * (math.sin(i * f1 + p3) + 0.4 * math.sin(i * f2 + p4))))
        return out

    # -- primitives -----------------------------------------------------------
    def line(self, pts, color="ink", width: int | None = None, wobble: float | None = None):
        pts = self.jitter(list(pts), amount=wobble)
        self.d.line(pts, fill=c(color), width=width or self.width, joint="curve")
        r = (width or self.width) / 2
        for x, y in (pts[0], pts[-1]):
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=c(color))

    def poly(self, pts, fill=None, outline="ink", width: int | None = None, offset: float = 3.0):
        pts = list(pts)
        if fill:
            # slight fill/outline mis-registration, like a quick hand-coloured cel
            rng = self._rng()
            ox, oy = rng.uniform(-offset, offset), rng.uniform(-offset, offset)
            self.d.polygon([(x + ox, y + oy) for x, y in self.jitter(pts, closed=True, amount=1.0)], fill=c(fill))
        if outline:
            jp = self.jitter(pts, closed=True)
            self.d.line(jp + [jp[0]], fill=c(outline), width=width or self.width, joint="curve")

    def ellipse(self, box, fill=None, outline="ink", width: int | None = None):
        self.poly(ellipse_pts(box), fill=fill, outline=outline, width=width)

    def rect(self, box, fill=None, outline="ink", width: int | None = None):
        x0, y0, x1, y1 = box
        self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], fill=fill, outline=outline, width=width)

    def text(self, xy, s: str, size: int, color="ink", anchor="la"):
        self.d.text(xy, s, font=font(size), fill=c(color), anchor=anchor)

    def hatch(self, box, color="ink", spacing: int = 18, width: int = 2):
        """Diagonal pencil hatching inside a box (used for shading)."""
        x0, y0, x1, y1 = box
        for k in range(int(x0 - (y1 - y0)), int(x1), spacing):
            self.line([(k, y1), (k + (y1 - y0), y0)], color=color, width=width, wobble=0.8)


def c(color):
    return PALETTE[color] if isinstance(color, str) else color


def densify(pts, step: float = 14):
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
        out.extend((x0 + (x1 - x0) * t / n, y0 + (y1 - y0) * t / n) for t in range(n))
    out.append(pts[-1])
    return out


def ellipse_pts(box, n: int = 48):
    x0, y0, x1, y1 = box
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


@lru_cache(maxsize=8)
def paper(w: int, h: int, seed: int = 0) -> Image.Image:
    """Warm paper background with fibre noise and a soft vignette."""
    rng = np.random.default_rng(seed)
    base = np.array(PALETTE["paper"], dtype=np.float32)
    noise = rng.normal(0, 1, (h // 4, w // 4)).astype(np.float32)
    noise = np.array(Image.fromarray(((noise * 20) + 128).clip(0, 255).astype(np.uint8))
                     .resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(1.5)), dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    vign = 1 - 0.10 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    img = (base[None, None, :] + (noise[..., None] - 128) * 0.12) * vign[..., None]
    return Image.fromarray(img.clip(0, 255).astype(np.uint8), "RGB")


def wrap(text: str, size: int, max_width: int) -> list[str]:
    f = font(size)
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if f.getlength(trial) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines
