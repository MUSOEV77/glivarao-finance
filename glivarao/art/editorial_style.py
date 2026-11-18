"""Editorial documentary style: palette, type, paper and anti-aliased drawing helpers.

Look: warm archival paper, near-black ink, one accent per meaning (crimson = cost/risk, green = growth,
navy = neutral data), serif headlines (Caladea, OFL) and clean data type (Inter, OFL).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "assets/fonts"
FACES = {
    "serif": "Caladea-Bold.ttf", "serif_reg": "Caladea-Regular.ttf", "serif_it": "Caladea-Italic.ttf",
    "sans": "Inter-Regular.otf", "sans_med": "Inter-Medium.otf", "sans_semi": "Inter-SemiBold.otf",
    "sans_bold": "Inter-Bold.otf", "sans_xbold": "Inter-ExtraBold.otf",
}
PAL = {
    "paper": (245, 241, 232), "paper2": (235, 228, 214), "ink": (22, 24, 29), "sub": (98, 100, 108),
    "faint": (160, 156, 148), "rule": (208, 199, 182), "crimson": (158, 35, 48), "crimson_l": (226, 178, 176),
    "green": (28, 104, 70), "green_l": (170, 208, 184), "navy": (30, 54, 94), "navy_l": (168, 184, 208),
    "amber": (238, 182, 40), "white": (252, 250, 245),
}
COST_WORDS = r"\b(interest|fee|fees|cost|costs|debt|lose|loss|losing|penalt\w*|late|scam|owe|owed|charge\w*|apr)\b"
GAIN_WORDS = r"\b(grow|grows|growth|gain|gains|earn|earns|save|saves|saved|savings|wealth|worth|return|returns|match)\b"


@lru_cache(maxsize=128)
def face(kind: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / FACES[kind]), max(6, int(size)))


def tone(text: str) -> str:
    """crimson for costs/risks, green for growth, navy otherwise."""
    low = text.lower()
    if re.search(COST_WORDS, low):
        return "crimson"
    if re.search(GAIN_WORDS, low):
        return "green"
    return "navy"


@lru_cache(maxsize=8)
def paper_bg(w: int, h: int, ruled: bool = True) -> Image.Image:
    """Warm paper with fibre noise, very faint ledger rules and a soft vignette (static, cached)."""
    rng = np.random.default_rng(7)
    base = np.array(PAL["paper"], np.float32)[None, None, :]
    noise = rng.normal(0, 1, (h // 4 + 1, w // 4 + 1)).astype(np.float32)
    noise = np.array(Image.fromarray(noise).resize((w, h), Image.BICUBIC))
    fine = rng.normal(0, 1, (h, w)).astype(np.float32)
    img = base + (noise * 2.6 + fine * 1.4)[..., None]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    img *= (1 - 0.10 * np.clip(r - 0.55, 0, 1) ** 1.4)[..., None]
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")
    if ruled:
        d = ImageDraw.Draw(out, "RGBA")
        step = 54 if w > h else 60
        for y in range(step * 2, h - step, step):
            d.line([(0, y), (w, y)], fill=(*PAL["rule"], 46), width=1)
    return out


@lru_cache(maxsize=4)
def grain(w: int, h: int, k: int) -> Image.Image:
    """Four precomputed film-grain tiles (cycled per frame): alive without per-frame noise cost."""
    rng = np.random.default_rng(100 + k)
    g = rng.normal(128, 9, (h // 2, w // 2)).clip(0, 255).astype(np.uint8)
    return Image.fromarray(g, "L").resize((w, h), Image.NEAREST)


def apply_grain(img: Image.Image, f: int) -> Image.Image:
    """Soft-light film grain (mid-grey noise leaves colours unchanged on average)."""
    from PIL import ImageChops

    return ImageChops.soft_light(img, grain(img.width, img.height, f % 4).convert("RGB"))


def text_w(kind: str, size: int, text: str, tracking: float = 0) -> float:
    f = face(kind, size)
    return f.getlength(text) + tracking * max(0, len(text) - 1)


def draw_text(d: ImageDraw.ImageDraw, xy, text: str, kind: str, size: int, fill, anchor: str = "la",
              tracking: float = 0, alpha: int = 255):
    """Text with optional letter-spacing (tracking, px) and alpha."""
    col = (*PAL[fill], alpha) if isinstance(fill, str) else (*fill[:3], alpha)
    f = face(kind, size)
    if not tracking:
        d.text(xy, text, font=f, fill=col, anchor=anchor)
        return
    x, y = xy
    total = text_w(kind, size, text, tracking)
    if anchor[0] == "m":
        x -= total / 2
    elif anchor[0] == "r":
        x -= total
    a = "l" + anchor[1]
    for ch in text:
        d.text((x, y), ch, font=f, fill=col, anchor=a)
        x += f.getlength(ch) + tracking


def wrap(text: str, kind: str, size: int, max_w: float) -> list[str]:
    f, lines, cur = face(kind, size), [], ""
    for w in text.split():
        trial = f"{cur} {w}".strip()
        if f.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def fit_lines(text: str, kind: str, start: int, max_w: float, max_lines: int, min_size: int = 28):
    size = start
    lines = wrap(text, kind, size, max_w)
    while (len(lines) > max_lines or any(face(kind, size).getlength(l) > max_w for l in lines)) and size > min_size:
        size -= 2
        lines = wrap(text, kind, size, max_w)
    return lines[:max_lines], size


def highlighter(d: ImageDraw.ImageDraw, x0: float, y0: float, x1: float, y1: float, pr: float, alpha: int = 150):
    """Amber highlighter swipe drawn left to right (pr 0..1), slightly slanted like a real marker."""
    if pr <= 0:
        return
    xe = x0 + (x1 - x0) * min(1.0, pr)
    d.polygon([(x0, y0 + 4), (xe, y0), (xe + 6, y1 - 2), (x0 - 4, y1)], fill=(*PAL["amber"], alpha))


@lru_cache(maxsize=64)
def duotone_plate(name: str, size: int) -> Image.Image:
    """Archival duotone (ink to paper) of a GLIVARAO illustration, with its alpha kept."""
    from .illustrations import draw_illustration

    src = draw_illustration(name, 0, size)
    gray = ImageOps.autocontrast(src.convert("L"), cutoff=1)
    tinted = ImageOps.colorize(gray, black=PAL["ink"], white=PAL["paper"], mid=PAL["navy"]).convert("RGBA")
    tinted.putalpha(src.getchannel("A"))
    return tinted


def soft_shadow(size: tuple[int, int], radius: int = 18, alpha: int = 60) -> Image.Image:
    w, h = size
    pad = radius * 2
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((pad, pad, pad + w, pad + h), fill=(40, 30, 20, alpha))
    return img.filter(ImageFilter.GaussianBlur(radius))


NUM_RE = re.compile(r"(\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:K|M|B|k)\b|\s(?:thousand|million|billion)\b)?|"
                    r"\b\d[\d,]*(?:\.\d+)?\s?(?:%|percent\b)|"
                    r"\b\d[\d,]*(?:\.\d+)?\s(?:years?|months?|days?|points?|times)\b)")


def find_figure(text: str) -> str | None:
    """The most prominent figure in a sentence ($ amounts first, then %, then counts with units)."""
    found = [m.group(0).strip() for m in NUM_RE.finditer(text)]
    if not found:
        return None
    for pref in ("$", "%", "percent"):
        for f in found:
            if pref in f:
                return f
    return found[0]


def split_figure(fig: str) -> tuple[str, float, int, str]:
    """'$8,887' -> ('$', 8887.0, 0 decimals, ''); '24 percent' -> ('', 24, 0, '%'); '18 years' -> ('', 18, 0, ' years')."""
    m = re.match(r"(\$?)\s?(\d[\d,]*)(\.\d+)?\s?(.*)", fig)
    if not m:
        return "", 0.0, 0, fig
    pre, whole, dec, suf = m.groups()
    value = float(whole.replace(",", "") + (dec or ""))
    suf = suf.strip()
    suf = {"percent": "%", "thousand": "K", "million": "M", "billion": "B", "k": "K"}.get(suf.lower(), suf)
    if suf and suf not in ("%", "K", "M", "B"):
        suf = " " + suf
    return pre, value, len(dec) - 1 if dec else 0, suf


def format_figure(pre: str, value: float, decimals: int, suf: str) -> str:
    body = f"{value:,.{decimals}f}"
    return f"{pre}{body}{suf}"
