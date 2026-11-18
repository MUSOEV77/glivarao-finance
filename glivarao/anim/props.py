"""Animated props and effects: icon pop-ins, coin showers, flying bills, sticky notes, number counters."""
from __future__ import annotations

import math
import random
from functools import lru_cache

from PIL import Image

from ..art.illustrations import draw_illustration
from ..art.style import Ink, font, wrap
from .easing import clamp, ease_out, ease_out_back, progress


@lru_cache(maxsize=64)
def icon_sprite(name: str, size: int, boil: int) -> Image.Image:
    return draw_illustration(name, boil=boil, size=size)


@lru_cache(maxsize=512)
def _scaled(name: str, size: int, boil: int, scale_q: int, angle_q: int) -> Image.Image:
    im = icon_sprite(name, size, boil)
    sc = scale_q / 100
    if sc != 1:
        im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BICUBIC)
    return im.rotate(angle_q / 2, resample=Image.BICUBIC, expand=True) if angle_q else im


def paste_center(dst: Image.Image, im: Image.Image, cx: float, cy: float, alpha: float = 1.0):
    if alpha < 1:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda a: int(a * alpha)))
    dst.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)


def icon(dst, name, cx, cy, size, t, start, boil, float_amp=10.0):
    """Pop in with overshoot, then float gently."""
    p = progress(t, start, 0.55)
    if p <= 0:
        return
    sc = max(0.01, ease_out_back(p))
    bob = math.sin((t - start) * 1.6) * float_amp * clamp((t - start) / 1.0)
    ang = math.sin((t - start) * 1.1) * 3
    im = _scaled(name, size, boil, max(1, int(sc * 100)), int(ang * 2))
    paste_center(dst, im, cx, cy + bob)


@lru_cache(maxsize=8)
def coin_sprite(r: int, boil: int) -> Image.Image:
    img = Image.new("RGBA", (r * 2 + 8, r * 2 + 8), (0, 0, 0, 0))
    ink = Ink(img, seed=boil + 3, wobble=1.0, width=4)
    c = r + 4
    ink.ellipse((c - r, c - r, c + r, c + r), fill="gold")
    ink.text((c, c), "$", int(r * 1.2), anchor="mm")
    return img


def coin_shower(dst, x0, x1, ground_y, t, start, boil, n=14, seed=1):
    """Coins drop with gravity, bounce once and settle into a small pile."""
    if t < start:
        return
    rng = random.Random(seed)
    for i in range(n):
        delay = start + i * 0.09 + rng.uniform(0, 0.05)
        if t < delay:
            continue
        x = rng.uniform(x0, x1)
        rest_y = ground_y - (i % 4) * 18 - rng.uniform(0, 6)
        y0 = -80 - rng.uniform(0, 200)
        g = 2600.0
        tt = t - delay
        fall_t = math.sqrt(2 * (rest_y - y0) / g)
        if tt < fall_t:
            y = y0 + 0.5 * g * tt * tt
            squash = 1.0
        else:
            bt = tt - fall_t  # one damped bounce
            v = g * fall_t * 0.28
            y = rest_y - max(0.0, v * bt - 0.5 * g * bt * bt)
            squash = 1.0
        spin = abs(math.cos((tt + i) * 7)) if tt < fall_t + 0.3 else 1.0
        im = coin_sprite(26, boil)
        w = max(4, int(im.width * max(0.15, spin) * squash))
        paste_center(dst, im.resize((w, im.height), Image.BICUBIC), x, y)


@lru_cache(maxsize=4)
def bill_sprite(boil: int) -> Image.Image:
    img = Image.new("RGBA", (150, 74), (0, 0, 0, 0))
    ink = Ink(img, seed=boil + 9, wobble=1.0, width=4)
    ink.rect((4, 4, 146, 70), fill="green_light")
    ink.ellipse((52, 12, 98, 62), fill="white", width=3)
    ink.text((75, 38), "$", 40, color="green", anchor="mm")
    return img


def flying_bills(dst, x0, y0, x1, y1, t, start, boil, n=6, seed=2, dur=1.6):
    """Bills flutter along an arc from (x0,y0) to (x1,y1)."""
    rng = random.Random(seed)
    for i in range(n):
        d = start + i * 0.18
        p = progress(t, d, dur)
        if p <= 0 or p >= 1:
            continue
        e = ease_out(p)
        x = x0 + (x1 - x0) * e + math.sin(p * 9 + i) * 30
        y = y0 + (y1 - y0) * e - math.sin(p * math.pi) * (160 + rng.uniform(0, 80))
        ang = math.sin(p * 10 + i) * 35
        im = bill_sprite(boil).rotate(ang, resample=Image.BICUBIC, expand=True)
        paste_center(dst, im, x, y, alpha=min(1.0, (1 - p) * 4))


def sticky_note(dst, text, x, y, t, start, idx, boil, w=520):
    """Slides in from the right with a slight rotation, then settles."""
    p = progress(t, start, 0.6)
    if p <= 0:
        return
    e = ease_out_back(p, 1.2)
    tilt = (-1) ** idx * 3.5 * (1 - 0.3 * e)
    lines = wrap(text, 50, w - 60)[:3]
    h = 70 + 56 * len(lines)
    img = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    ink = Ink(img, seed=boil * 7 + idx, wobble=1.2, width=4)
    ink.d.rectangle((16, 16, w + 14, h + 14), fill=(0, 0, 0, 40))  # soft shadow
    ink.rect((6, 6, w, h), fill="sticky")
    ink.line([(w / 2 - 50, 8), (w / 2 + 50, 8)], color=(220, 200, 150), width=16, wobble=0.5)  # tape
    for j, line in enumerate(lines):
        ink.text((34, 40 + j * 56), line, 50)
    img = img.rotate(tilt, resample=Image.BICUBIC, expand=True)
    xx = x + (1 - e) * 900
    dst.paste(img, (int(xx), int(y)), img)


def counter(dst, value: float, x, y, t, start, dur, size=96, prefix="$", color=(46, 139, 87)):
    """Number that counts up from 0 to `value`."""
    p = progress(t, start, dur)
    if p <= 0:
        return
    v = value * ease_out(p)
    text = f"{prefix}{v:,.0f}"
    ink = Ink(dst, seed=3)
    for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
        ink.d.text((x + dx, y + dy), text, font=font(size), fill=(255, 253, 247), anchor="mm")
    ink.d.text((x, y), text, font=font(size), fill=color, anchor="mm")
