"""Editorial thumbnails matching the documentary theme: archival paper, a huge serif headline with the key
number on an amber highlighter, and one visual (the video's own chart, drawn from its exact numbers, or an
archival duotone plate). Landscape 1280x720 (upload) and 1080x1920 (Shorts cover)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from ..art.charts_editorial import draw_editorial_chart
from ..art.editorial_style import PAL, draw_text, duotone_plate, face, fit_lines, highlighter, paper_bg, soft_shadow
from ..models import Script


def _headline(img: Image.Image, text: str, x: int, y: int, max_w: int, start: int, max_lines: int,
              center: bool = False) -> int:
    d = ImageDraw.Draw(img, "RGBA")
    lines, size = fit_lines(text, "serif", start, max_w, max_lines, 56)
    f = face("serif", size)
    lh = int(size * 1.06)
    for i, ln in enumerate(lines):
        ly = y + i * lh
        lx = x + (max_w - f.getlength(ln)) / 2 if center else x
        words = ln.split()
        key = next((w for w in words if any(ch.isdigit() for ch in w) or "$" in w), None)
        if key:
            kx = lx + f.getlength(ln[: ln.index(key)])
            highlighter(d, kx - 10, ly + size * 0.42, kx + f.getlength(key) + 10, ly + size * 0.98, 1.0, alpha=255)
        draw_text(d, (lx, ly), ln, "serif", size, "ink")
    return y + len(lines) * lh


def _card(visual: Image.Image, pad: int = 26) -> Image.Image:
    w, h = visual.width + 2 * pad, visual.height + 2 * pad
    card = Image.new("RGBA", (w, h), (*PAL["white"], 255))
    ImageDraw.Draw(card).rectangle((0, 0, w - 1, h - 1), outline=PAL["ink"], width=3)
    card.alpha_composite(visual, (pad, pad))
    return card


def _visual(script: Script, w: int, h: int) -> Image.Image:
    chart = next((s.chart for s in script.scenes if s.chart.kind != "none"), None)
    if chart is not None:  # drawn large then scaled down so it stays crisp and uncluttered
        k = max(1.0, 1100 / w)
        big = draw_editorial_chart(chart, int(w * k), int(h * k), 1.0, compact=True)
        return big.resize((w, h), Image.LANCZOS)
    illo = next((s.illustration for s in script.scenes if s.illustration not in ("target", "lightbulb")), "coin_stack")
    size = min(w, h)
    out = Image.new("RGBA", (w, h), (*PAL["paper2"], 255))
    art = duotone_plate(illo, int(size * 0.86))
    out.alpha_composite(art, ((w - art.width) // 2, (h - art.height) // 2))
    return out


def make_thumbnail_editorial(script: Script, dst: Path, portrait: bool = False) -> Path:
    w, h = (1080, 1920) if portrait else (1280, 720)
    img = paper_bg(w, h).copy().convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    text = script.thumbnail_text or script.title
    if portrait:
        draw_text(d, (w / 2, 120), "GLIVARAO FINANCE", "sans_bold", 30, "crimson", anchor="mm", tracking=8)
        bottom = _headline(img, text, 70, 200, w - 140, 190, 3, center=True)
        vis = _card(_visual(script, w - 200, 640))
        sh = soft_shadow(vis.size, 20, 70)
        top = max(bottom + 70, 820)
        img.alpha_composite(sh, ((w - vis.width) // 2 - 40 + 12, top - 40 + 16))
        img.alpha_composite(vis, ((w - vis.width) // 2, top))
    else:
        draw_text(d, (70, 66), "GLIVARAO FINANCE", "sans_bold", 22, "crimson", anchor="lm", tracking=6)
        d.line([(70, 92), (250, 92)], fill=PAL["crimson"], width=3)
        bottom = _headline(img, text, 64, 128, 640, 132, 3)
        dek = script.title.split(" (")[0].replace("#Shorts", "").strip()
        if dek.lower().rstrip(".") != text.lower().rstrip("."):
            lines, size = fit_lines(dek, "serif_it", 40, 600, 3, 28)
            dd = ImageDraw.Draw(img, "RGBA")
            for k, ln in enumerate(lines):
                draw_text(dd, (68, bottom + 34 + k * size * 1.2), ln, "serif_it", size, "sub")
        vis = _card(_visual(script, 440, 470))
        sh = soft_shadow(vis.size, 18, 70)
        x, y = w - vis.width - 56, (h - vis.height) // 2 + 10
        img.alpha_composite(sh, (x - 36 + 12, y - 36 + 16))
        img.alpha_composite(vis, (x, y))
    d = ImageDraw.Draw(img)
    d.line([(0, h - 8), (w, h - 8)], fill=PAL["navy"], width=8)
    out = img.convert("RGB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    out.save(dst, "JPEG", quality=90, optimize=True)
    if dst.stat().st_size > 2_000_000:  # YouTube thumbnail limit
        out.save(dst, "JPEG", quality=78, optimize=True)
    return dst


def make_thumbnail(script: Script, dst: Path, portrait: bool = False, theme: str = "editorial") -> Path:
    """Theme-aware entry point used by the daily pipeline."""
    if theme == "editorial":
        return make_thumbnail_editorial(script, dst, portrait)
    from .thumbnail_v3 import make_thumbnail_v3

    return make_thumbnail_v3(script, dst, portrait)
