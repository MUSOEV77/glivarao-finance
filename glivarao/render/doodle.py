"""Doodle theme frames (GLIVARAO hand-drawn explainer style, v2).

Every shot is a FULL hand-drawn picture: either a key scene made for this video (Max acting in it) or a reusable
place from the scene library with a Max cutout standing in it. The background moves (slow pan/zoom); our
code-drawn cards (title, big number, chart, key points) and Max stay fixed on screen, and every text is fitted
inside the SAFE AREA (never cut off at the frame edge, never under the captions). Shots are 6-10 s and change
with a hard cut.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from ..art import doodle as D

FPS = 24
MIN_SHOT, MAX_SHOT = 6.0, 10.0
# (x0, y0, x1, y1) as fractions of the frame: text and cards stay inside; captions live below y1
SAFE = {False: (0.05, 0.06, 0.95, 0.80), True: (0.07, 0.06, 0.93, 0.56)}
NUM = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:trillion|billion|million|thousand))?|\d[\d,]*(?:\.\d+)?\s?(?:%|percent)"
                 r"|\d[\d,]*(?:\.\d+)?\s(?:trillion|billion|million)", re.I)
MOODS = [(r"\$\d|\d%|trillion|billion|record|jump|spike|doubled|soar|climb|faster than", "shocked"),
         (r"trap|debt|late|owe|worse|lose|risk|fail|crisis|problem|expensive|cost", "worried"),
         (r"why|how|what|\?", "thinking"), (r"save|win|pay off|free|plan|step|fix|protect", "happy"),
         (r"done|great|finally|debt-free", "cheering")]


@dataclass
class Shot:
    start: float
    end: float
    kind: str
    text: str = ""
    data: dict = field(default_factory=dict)


def plan_shots(sentences: list[tuple[float, float, str]], duration: float) -> list[tuple[float, float, str]]:
    """Group sentences into 6-10 s shots (long sentences are split evenly). Returns (start, end, text)."""
    out, cur = [], None
    for s, e, txt in sentences or [(0.0, duration, "")]:
        if cur is None:
            cur = [s if not out else out[-1][1], e, txt]
        elif e - cur[0] <= MAX_SHOT or cur[1] - cur[0] < MIN_SHOT:
            cur[1], cur[2] = e, f"{cur[2]} {txt}".strip()
        else:
            out.append(tuple(cur))
            cur = [cur[1], e, txt]
    if cur is not None:
        out.append(tuple(cur))
    if not out:
        out = [(0.0, duration, "")]
    out[0] = (0.0, out[0][1], out[0][2])
    out[-1] = (out[-1][0], max(out[-1][1], duration), out[-1][2])
    if len(out) > 1 and out[-1][1] - out[-1][0] < 4.0:
        a, b = out[-2], out[-1]
        out[-2:] = [(a[0], b[1], f"{a[2]} {b[2]}")]
    split = []
    for s, e, txt in out:
        n = max(1, math.ceil((e - s) / MAX_SHOT))
        split += [(s + (e - s) * k / n, s + (e - s) * (k + 1) / n, txt) for k in range(n)]
    return split


def mood(text: str, fallback: str = "explaining") -> str:
    low = text.lower()
    for rx, m in MOODS:
        if re.search(rx, low):
            return m
    return fallback


def shots_for(scene, sentences, duration: float, first_scene: bool = False) -> list[Shot]:
    shots, used_chart, used_points = [], False, False
    has_chart = scene.chart.kind != "none"
    for k, (s, e, txt) in enumerate(plan_shots(sentences, duration)):
        num = NUM.search(txt)
        if k == 0:
            kind = "title"
        elif has_chart and not used_chart:
            kind, used_chart = "chart", True
        elif num:
            kind = "number"
        elif scene.key_points and not used_points:
            kind, used_points = "points", True
        else:
            kind = "scene"          # the picture alone (Max acting / in the place)
        shots.append(Shot(s, e, kind, txt, {"num": num.group(0) if num else ""}))
    return shots


# ------------------------------------------------------------------------------------------- safe text
def safe_box(size: tuple[int, int], portrait: bool) -> tuple[int, int, int, int]:
    w, h = size
    x0, y0, x1, y1 = SAFE[portrait]
    return int(w * x0), int(h * y0), int(w * x1), int(h * y1)


def fit_text(text: str, box_w: float, box_h: float, max_size: int, min_size: int = 18,
             max_lines: int = 3) -> tuple[int, list[str]]:
    """Largest font size (<= max_size) at which the wrapped text fits box_w x box_h in <= max_lines lines. At the
    minimum size the text is shortened with an ellipsis rather than ever leaving the box."""
    size = max_size
    while size >= min_size:
        lines = D.wrap(text, size, box_w)
        if (len(lines) <= max_lines and all(D.hand(size).getlength(ln) <= box_w for ln in lines)
                and len(lines) * size * 1.08 <= box_h):
            return size, lines
        size -= 2
    size = min_size
    lines = D.wrap(text, size, box_w)[:max_lines]
    last = lines[-1]
    while last and D.hand(size).getlength(last + "...") > box_w:
        last = last[:-1]
    lines[-1] = last.rstrip() + "..."
    lines = [ln if D.hand(size).getlength(ln) <= box_w else ln[: max(1, int(len(ln) * box_w /
                                                                          D.hand(size).getlength(ln)) - 1)]
             for ln in lines]
    return size, lines


class Overlay:
    """Screen-space RGBA layer (cards + text) that records the exact box of every text it draws."""

    def __init__(self, size: tuple[int, int], portrait: bool, seed: int = 0):
        self.size, self.portrait = size, portrait
        self.img = Image.new("RGBA", size, (0, 0, 0, 0))
        self.pen = D.Pen(self.img, seed=seed, width=5, wobble=1.0)
        self.text_boxes: list[tuple[int, int, int, int]] = []
        self.safe = safe_box(size, portrait)

    def card(self, box, tilt_seed: int = 0) -> None:
        x0, y0, x1, y1 = box
        sh = Image.new("RGBA", self.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((x0 + 8, y0 + 10, x1 + 8, y1 + 10), 18, fill=(0, 0, 0, 70))
        self.img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
        paper = D.paper(int(x1 - x0), int(y1 - y0), seed=5 + tilt_seed % 3).convert("RGBA")
        mask = Image.new("L", paper.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, paper.width - 1, paper.height - 1), 18, fill=255)
        gd = ImageDraw.Draw(paper)            # notebook grid paper, like a page from the explainer's notebook
        step = max(18, int(min(self.size) * 0.028))
        for gx in range(step, paper.width, step):
            gd.line([(gx, 0), (gx, paper.height)], fill=(196, 214, 226, 255), width=1)
        for gy in range(step, paper.height, step):
            gd.line([(0, gy), (paper.width, gy)], fill=(196, 214, 226, 255), width=1)
        gd.line([(step * 2, 0), (step * 2, paper.height)], fill=(226, 150, 150, 255), width=2)   # margin line
        self.img.paste(paper, (int(x0), int(y0)), mask)
        self.pen.d.rounded_rectangle(box, 18, outline=D.INK + (255,), width=5)
        self.pen.d.rectangle((x0 + 30, y0 - 12, x0 + 130, y0 + 12), fill=D.GOLD + (230,))     # tape

    def text(self, text: str, box, max_size: int, color=D.INK, align: str = "left", max_lines: int = 3,
             bold: bool = True) -> float:
        """Fit text into box (clipped to the safe area). Returns the y below the last line."""
        sx0, sy0, sx1, sy1 = self.safe
        x0, y0, x1, y1 = max(box[0], sx0), max(box[1], sy0), min(box[2], sx1), min(box[3], sy1)
        size, lines = fit_text(text, x1 - x0, y1 - y0, max_size, max_lines=max_lines)
        font = D.hand(size)
        y = y0
        stroke = max(1, size // 34) if bold else 0
        for ln in lines:
            w = font.getlength(ln)
            x = x0 if align == "left" else x0 + (x1 - x0 - w) / 2
            self.pen.d.text((x, y), ln, font=font, fill=color + (255,) if len(color) == 3 else color,
                            stroke_width=stroke, stroke_fill=color + (255,) if len(color) == 3 else color)
            bb = self.pen.d.textbbox((x, y), ln, font=font, stroke_width=stroke)
            self.text_boxes.append(tuple(int(v) for v in bb))
            y += size * 1.08
        return y


def build_overlay(scene, shot: Shot, size: tuple[int, int], portrait: bool, seed: int = 0) -> Overlay:
    ov = Overlay(size, portrait, seed)
    sx0, sy0, sx1, sy1 = ov.safe
    sw, sh = sx1 - sx0, sy1 - sy0
    pad = int(min(size) * 0.025)
    if shot.kind == "title":
        box = (sx0, sy0, sx0 + sw * (1.0 if portrait else 0.56), sy0 + sh * (0.34 if portrait else 0.36))
        ov.card(box, seed)
        y = ov.text(scene.heading, (box[0] + pad, box[1] + pad, box[2] - pad, box[3] - pad * 1.6),
                    int(size[1] * (0.05 if portrait else 0.085)))
        D.underline(ov.pen, box[0] + pad, min(box[2] - pad, box[0] + pad + sw * 0.4), min(y, box[3] - pad),
                    D.GREEN + (255,), 8)
    elif shot.kind == "number":
        num = shot.data.get("num", "")
        box = (sx0, sy0, sx0 + sw * (1.0 if portrait else 0.5), sy0 + sh * (0.5 if portrait else 0.62))
        ov.card(box, seed)
        y = ov.text(num, (box[0] + pad * 2.2, box[1] + pad * 1.6, box[2] - pad * 2.2,
                          box[1] + (box[3] - box[1]) * 0.6), int(size[1] * (0.1 if portrait else 0.17)),
                    align="center", max_lines=1)
        bb = ov.text_boxes[-1]
        ov.pen.d.ellipse((max(box[0] + 6, bb[0] - pad), max(box[1] + 6, bb[1] - pad * 0.8),
                          min(box[2] - 6, bb[2] + pad), bb[3] + pad * 0.8), outline=D.GOLD + (255,),
                         width=max(5, int(size[1] * 0.007)))
        ov.text(scene.heading, (box[0] + pad, max(y, bb[3] + pad), box[2] - pad, box[3] - pad),
                int(size[1] * (0.035 if portrait else 0.05)), color=D.GREEN, align="center", max_lines=2)
        D.sparkle(ov.pen, min(bb[2] + pad * 0.5, box[2] - pad * 2), max(bb[1], box[1] + pad * 2), pad * 1.4,
                  D.GOLD + (255,))
    elif shot.kind == "chart":
        c = scene.chart
        box = (sx0, sy0, sx0 + sw * (1.0 if portrait else 0.52), sy0 + sh * (0.62 if portrait else 0.78))
        ov.card(box, seed)
        y = ov.text(c.title or scene.heading, (box[0] + pad, box[1] + pad, box[2] - pad,
                                              box[1] + (box[3] - box[1]) * 0.22),
                    int(size[1] * (0.032 if portrait else 0.045)), max_lines=2)
        cb = (box[0] + pad * 2, y + pad, box[2] - pad * 2, box[3] - pad * 2)
        vals = [float(v) for v in (c.values or [])]
        if c.kind == "bar_compare" and vals:
            D.bar_chart(ov.img, cb, vals[:6], [lab[:10] for lab in (c.labels or [""] * len(vals))[:6]], seed=seed)
        elif len(vals) >= 3:
            lo, hi = min(vals), max(vals)
            norm = [(v - lo) / ((hi - lo) or 1) * 0.75 + 0.15 for v in vals]
            cut = max(2, int(len(norm) * 0.7))
            D.spike_chart(ov.img, cb, history=norm[:cut], spike=norm[cut - 1:], seed=seed)
        else:
            D.spike_chart(ov.img, cb, seed=seed)
    elif shot.kind == "points":
        pts = [x for x in (scene.key_points or []) if x][:3]
        box = (sx0, sy0, sx0 + sw * (1.0 if portrait else 0.55), sy0 + sh * (0.7 if portrait else 0.8))
        ov.card(box, seed)
        y = ov.text(scene.heading, (box[0] + pad, box[1] + pad, box[2] - pad, box[1] + (box[3] - box[1]) * 0.25),
                    int(size[1] * (0.035 if portrait else 0.05)), max_lines=2)
        row_h = (box[3] - pad - y) / max(1, len(pts))
        for n, t in enumerate(pts):
            ry = y + n * row_h + pad * 0.5
            ck = pad * 1.4
            ov.pen.line([(box[0] + pad, ry + ck * 0.5), (box[0] + pad + ck * 0.35, ry + ck),
                         (box[0] + pad + ck, ry)], max(5, pad * 0.25), D.GREEN + (255,))
            ov.text(t, (box[0] + pad + ck * 1.5, ry, box[2] - pad, ry + row_h - pad * 0.3),
                    int(size[1] * (0.03 if portrait else 0.042)), max_lines=2, bold=False)
    return ov


# ------------------------------------------------------------------------------------------- camera
MOVES = ("zoom_in", "pan_right", "zoom_out", "pan_left", "pan_up")


def camera(bg: Image.Image, frame_size: tuple[int, int], t: float, move: str) -> Image.Image:
    """Slow move across a full picture (cover-fit, never shows past its edge); t in 0..1 (eased)."""
    e = t * t * (3 - 2 * t)
    fw, fh = frame_size
    bw, bh = bg.size
    base = min(bw / fw, bh / fh)                     # view size (in picture pixels) at zoom 1 = cover fit
    z0, z1 = {"zoom_in": (1.0, 1.12), "zoom_out": (1.12, 1.0)}.get(move, (1.08, 1.08))
    z = z0 + (z1 - z0) * e
    vw, vh = fw * base / z, fh * base / z
    fx, fy = {"pan_right": (0.15 + 0.7 * e, 0.5), "pan_left": (0.85 - 0.7 * e, 0.5),
              "pan_up": (0.5, 0.8 - 0.6 * e)}.get(move, (0.5, 0.5))
    x0, y0 = (bw - vw) * fx, (bh - vh) * fy
    return bg.transform(frame_size, Image.EXTENT, (x0, y0, x0 + vw, y0 + vh), Image.BICUBIC)


@lru_cache(maxsize=24)
def _load_bg(path: str) -> Image.Image:
    return Image.open(path).convert("RGB")


@lru_cache(maxsize=32)
def _max_cut(path: str, height: int) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    s = height / im.height
    return im.resize((max(1, int(im.width * s)), height), Image.LANCZOS)


def empty_ratio(img: Image.Image, block: int = 8, std_max: float = 4.0) -> float:
    """Share of the frame that is BLANK: flat, featureless, near-white/cream paper (8x8 blocks of a 192x108
    thumbnail). Coloured fills (sky, walls, chart areas) are content, not blank. Full illustrations score near 0;
    the rejected v1 doodle frames scored 60-70%."""
    import numpy as np

    sz = (192, 108) if img.width >= img.height else (108, 192)
    rgb = np.asarray(img.convert("RGB").resize(sz, Image.BILINEAR), dtype=np.float32)
    lum = rgb.mean(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    h, w = lum.shape
    blank = total = 0
    for y in range(0, h - block + 1, block):
        for x in range(0, w - block + 1, block):
            total += 1
            b = lum[y:y + block, x:x + block]
            blank += b.std() < std_max and b.mean() > 215 and sat[y:y + block, x:x + block].mean() < 30
    return blank / max(1, total)


class DoodleFrames:
    """frame(f, portrait) for one scene. bg_path: the scene's picture; max_pose_path: Max cutout to place (None
    when the picture already shows Max acting in it)."""

    def __init__(self, script, i: int, sentences, n_frames: int):
        self.scene = script.scenes[i]
        self.i = i
        self.shots = shots_for(self.scene, sentences, n_frames / FPS, i == 0)
        self._ov: dict = {}

    def _shot_at(self, t: float) -> int:
        for k, s in enumerate(self.shots):
            if t < s.end:
                return k
        return len(self.shots) - 1

    def overlay(self, k: int, portrait: bool) -> Overlay:
        key = (k, portrait)
        if key not in self._ov:
            size = (1080, 1920) if portrait else (1920, 1080)
            self._ov = {key: build_overlay(self.scene, self.shots[k], size, portrait, seed=self.i * 7 + k)}
        return self._ov[key]

    def frame(self, f: int, portrait: bool) -> Image.Image:
        t = f / FPS
        k = self._shot_at(t)
        s = self.shots[k]
        size = (1080, 1920) if portrait else (1920, 1080)
        prog = min(1.0, max(0.0, (t - s.start) / max(0.1, s.end - s.start)))
        bgp = getattr(self.scene, "bg_path", None) or getattr(self.scene, "art_path", None)
        if bgp:
            out = camera(_load_bg(bgp), size, prog, MOVES[(self.i * 3 + k) % len(MOVES)])
        else:   # no picture at all: plain paper (the caller avoids this by falling back to the editorial theme)
            out = D.paper(*size).copy()
        pose = getattr(self.scene, "max_pose_path", None)
        if pose:
            h = int(size[1] * (0.30 if portrait else 0.78))      # Shorts: below the captions band
            cut = _max_cut(pose, h)
            x = int(size[0] * (0.70 if portrait else 0.80) - cut.width / 2)
            y = size[1] - h - (int(size[1] * 0.02) if not portrait else int(size[1] * 0.0))
            sh = Image.new("L", (cut.width, max(8, h // 14)), 0)
            ImageDraw.Draw(sh).ellipse((cut.width * 0.15, 0, cut.width * 0.85, sh.height - 1), fill=90)
            out.paste((30, 28, 24), (x, y + h - sh.height // 2), sh.filter(ImageFilter.GaussianBlur(6)))
            out.paste(cut, (x, y), cut)
        ov = self.overlay(k, portrait)
        out.paste(ov.img, (0, 0), ov.img)
        D.brand_mark(out, "tr", scale=1.0)
        return out


__all__ = ["DoodleFrames", "plan_shots", "shots_for", "build_overlay", "camera", "Shot", "fit_text", "safe_box",
           "empty_ratio", "SAFE", "MIN_SHOT", "MAX_SHOT", "Overlay"]
