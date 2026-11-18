"""GLIVARAO v3 thumbnails: ledger-paper background, large black serif headline with an amber highlighter
swipe, one clear visual (a chart from the video's exact calculation, or an icon) and Max reacting.
Three elements at most, so it reads at phone size. Landscape 1280x720 (upload) and 1080x1920 (Shorts cover).
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..anim.director import GESTURES
from ..anim.rig import draw_max
from ..art.charts import draw_chart
from ..art.illustrations import draw_illustration
from ..models import Script

ROOT = Path(__file__).resolve().parents[2]
SERIF = ROOT / "assets/fonts/DejaVuSerif-Bold.ttf"
PAPER = (251, 248, 241)
RULE = (214, 226, 236)
AMBER = (242, 183, 5)
INK = (28, 26, 32)


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(SERIF), size)


def _ledger(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(img)
    for y in range(60, h, 46):
        d.line([(0, y), (w, y)], fill=RULE, width=2)
    d.line([(70, 0), (70, h)], fill=(236, 190, 190), width=3)  # ledger margin line
    return img


def _wrap(text: str, size: int, max_w: int) -> list[str]:
    f, lines, cur = _font(size), [], ""
    for w in text.split():
        trial = f"{cur} {w}".strip()
        if f.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def _headline(img: Image.Image, text: str, x: int, y: int, max_w: int, start: int, max_lines: int = 2) -> int:
    size = start
    lines = _wrap(text, size, max_w)
    while (len(lines) > max_lines or any(_font(size).getlength(l) > max_w for l in lines)) and size > 48:
        size -= 6
        lines = _wrap(text, size, max_w)
    d = ImageDraw.Draw(img)
    f = _font(size)
    rng = random.Random(text)
    for i, line in enumerate(lines[:max_lines]):
        ly = y + i * int(size * 1.12)
        words = line.split()
        key = next((w for w in words if any(ch.isdigit() for ch in w)), words[0])  # highlight the number
        kx = x + int(f.getlength(line[: line.index(key)]))
        kw = int(f.getlength(key))
        tilt = rng.uniform(-6, 6)
        d.polygon([(kx - 12, ly + size * 0.45 + tilt), (kx + kw + 14, ly + size * 0.40 - tilt),
                   (kx + kw + 10, ly + size * 1.05 - tilt), (kx - 8, ly + size * 1.08 + tilt)], fill=AMBER)
        d.text((x, ly), line, font=f, fill=INK)
    return y + len(lines[:max_lines]) * int(size * 1.12)


def _visual(script: Script, w: int, h: int) -> Image.Image:
    chart = next((s.chart for s in script.scenes if s.chart.kind != "none"), None)
    if chart is not None:  # draw at a comfortable size, then scale down so labels never collide
        k = max(1.0, 900 / w, 520 / h)
        big = draw_chart(chart, int(w * k), int(h * k), 1.0, boil=1)
        return big.resize((w, h), Image.LANCZOS)
    illo = next((s.illustration for s in script.scenes if s.illustration not in ("target", "lightbulb")), "coin_stack")
    return draw_illustration(illo, boil=1, size=min(w, h))


def make_thumbnail_v3(script: Script, dst: Path, portrait: bool = False) -> Path:
    w, h = (1080, 1920) if portrait else (1280, 720)
    img = _ledger(w, h)
    text = script.thumbnail_text or script.title
    worried = any(k in script.title.lower() for k in ("mistake", "scam", "minimum", "fee", "debt", "red flags"))
    pose = GESTURES["worry"] if worried else GESTURES["present"]
    pose = pose.blend(pose, 1.0)
    pose.mouth, pose.brow = (0.5, 1.0) if worried else (0.7, 0.6)
    if portrait:
        bottom = _headline(img, text, 110, 120, w - 180, 150)
        vis = _visual(script, w - 120, 620)
        img.paste(vis, (60, bottom + 60), vis)
        ch = draw_max(pose, 0.9, boil=2)
        img.paste(ch, (w // 2 - ch.width // 2 + 120, h - ch.height + 90), ch)
    else:
        ch = draw_max(pose, 0.78, boil=2)
        img.paste(ch, (w - ch.width + 40, h - ch.height + 150), ch)
        bottom = _headline(img, text, 100, 40, 760, 112)
        top = bottom + 24
        vh = h - 50 - top  # the visual always sits below the headline, never under it
        vw = min(720, int(vh * 1.75))
        vis = _visual(script, vw, vh)
        img.paste(vis, (90, top), vis)
    ImageDraw.Draw(img).text((92, h - 14), "GLIVARAO FINANCE", font=_font(24), fill=(120, 116, 110), anchor="lb")
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "JPEG", quality=90, optimize=True)
    if dst.stat().st_size > 2_000_000:  # YouTube thumbnail limit
        img.save(dst, "JPEG", quality=78, optimize=True)
    return dst
