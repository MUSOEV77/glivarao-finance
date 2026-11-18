"""Thumbnails in the channel's hand-drawn style.

Landscape 1280x720 JPEG (< 2 MB) is uploaded for long videos. Shorts get a 720x1280 cover for the
Telegram review card (the YouTube API does not set custom thumbnails on Shorts).
"""
from __future__ import annotations

from pathlib import Path

from PIL import ImageEnhance

from ..art.characters import draw_character
from ..art.illustrations import draw_illustration
from ..art.style import Ink, font, paper, wrap
from ..models import Script


def _fit_text(text: str, max_w: int, max_lines: int, start: int) -> tuple[list[str], int]:
    size = start
    lines = wrap(text, size, max_w)
    while (len(lines) > max_lines or any(font(size).getlength(l) > max_w for l in lines)) and size > 50:
        size -= 6
        lines = wrap(text, size, max_w)
    return lines[:max_lines], size


def make_thumbnail(script: Script, dst: Path, portrait: bool = False) -> Path:
    w, h = (720, 1280) if portrait else (1280, 720)
    img = paper(w, h, seed=3).copy()
    ink = Ink(img, seed=11, wobble=3, width=8)
    text = script.thumbnail_text.upper()
    text_w = w - 120 if portrait else int(w * 0.56)
    lines, size = _fit_text(text, text_w, 3, 120 if portrait else 130)
    block_h = int(len(lines) * size * 1.02) + 70
    x0, y0 = 40, 50
    ink.poly([(x0 - 10, y0), (x0 + text_w + 50, y0 - 10), (x0 + text_w + 40, y0 + block_h),
              (x0, y0 + block_h + 12)], fill="green", width=9)
    y = y0 + 30
    for line in lines:
        for dx, dy in ((-4, 0), (4, 0), (0, -4), (0, 4), (6, 6)):  # chunky ink outline
            ink.d.text((x0 + 25 + dx, y + dy), line, font=font(size), fill=(38, 34, 46))
        ink.d.text((x0 + 25, y), line, font=font(size), fill=(255, 226, 120))
        y += int(size * 1.02)

    illo_name = next((s.illustration for s in script.scenes if s.chart.kind == "none"), "coin_stack")
    if portrait:
        illo = draw_illustration(illo_name, boil=1, size=300)
        img.paste(illo, (w - 330, y0 + block_h + 60), illo)
        char = draw_character("max", pose="point", mouth=0.65, boil=2, scale=0.95)
        img.paste(char, (10, h - char.height + 20), char)
    else:
        illo = draw_illustration(illo_name, boil=1, size=280)
        img.paste(illo, (x0 + 60, h - 300), illo)
        char = draw_character("max", pose="point", mouth=0.65, boil=2, scale=0.95)
        img.paste(char, (w - char.width + 10, h - char.height + 40), char)
    if portrait:
        ink.text((x0 + 10, y0 + block_h + 40), "GLIVARAO FINANCE", 34)
    else:
        ink.text((w - 30, 30), "GLIVARAO FINANCE", 34, anchor="ra")
    img = ImageEnhance.Contrast(img).enhance(1.08)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(dst, "JPEG", quality=90, optimize=True)
    return dst
