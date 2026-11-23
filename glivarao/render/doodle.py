"""Doodle theme frames (GLIVARAO hand-drawn explainer style, v2).

Every shot is a FULL hand-drawn picture: either a key scene made for this video (Max acting in it) or a reusable
place from the scene library with a Max cutout standing in it. The background moves (slow pan/zoom); our
code-drawn cards (title, big number, chart, key points) and Max stay fixed on screen, and every text is fitted
inside the SAFE AREA (never cut off at the frame edge, never under the captions). Shots are 6-10 s and change
with a hard cut.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from ..art import doodle as D

FPS = 24
MIN_SHOT, MAX_SHOT = 4.0, 6.0          # after the first 30 s: a visual change every 4-6 s
FAST_MIN, FAST_MAX = 2.0, 3.0          # first 30 s: a new image, zoom, pan or big text every 2-3 s
FAST_UNTIL = 30.0
NO_LOGO_UNTIL = 5.0                    # no logo/intro: the brand mark appears only after the hook
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


def plan_shots(sentences: list[tuple[float, float, str]], duration: float,
               offset: float = 0.0) -> list[tuple[float, float, str]]:
    """Cut the scene into shots: 2-3 s while the VIDEO is in its first 30 s (`offset` = this scene's start in the
    video), 4-6 s after that. Cuts snap to sentence ends when one is close. Returns (start, end, text)."""
    sents = sentences or [(0.0, duration, "")]
    ends = sorted({round(e, 3) for _, e, _ in sents if 0 < e < duration})
    cuts, t = [0.0], 0.0
    while duration - t > 1e-6:
        fast = offset + t < FAST_UNTIL
        lo, hi = (FAST_MIN, FAST_MAX) if fast else (MIN_SHOT, MAX_SHOT)
        tgt = (lo + hi) / 2
        rem = duration - t
        if rem <= hi:
            cuts.append(duration)
            break
        near = [b for b in ends if t + lo <= b <= t + hi]
        nxt = min(near, key=lambda b: abs(b - (t + tgt))) if near else t + tgt
        if duration - nxt < lo:                       # don't leave a sliver: split what is left evenly
            nxt = t + rem / 2
        cuts.append(nxt)
        t = nxt
    out = []
    for s0, s1 in zip(cuts, cuts[1:]):
        mid = (s0 + s1) / 2
        txt = " ".join(x for a, b, x in sents if a < s1 and b > s0 and (a + b) / 2 >= s0 - 0.01 and (a + b) / 2 < s1)
        if not txt:
            txt = next((x for a, b, x in sents if a <= mid < b), sents[-1][2])
        out.append((s0, s1, txt.strip()))
    return out or [(0.0, duration, "")]


def key_phrase(text: str, n: int = 5) -> str:
    """Big on-screen words for a shot: the number and what follows it, else the first words."""
    m = NUM.search(text)
    words = text.replace("*", "").split()
    if m:
        after = text[m.end():].split()[:3]
        return " ".join([m.group(0)] + [w.strip(",.;:!?") for w in after]).strip()
    return " ".join(w.strip(",.;:!?") for w in words[:n])


def count_text(num: str, frac: float) -> str:
    """'$1,368.5 billion' at frac 0.5 -> '$684.3 billion' (same format), for numbers that count up on screen."""
    m = re.match(r"^(\$?\s?)([\d,]*\.?\d+)(.*)$", num.strip())
    if not m or frac >= 1:
        return num
    pre, digits, post = m.groups()
    v = float(digits.replace(",", "")) * max(0.0, frac)
    dec = len(digits.split(".")[1]) if "." in digits else 0
    body = f"{v:,.{dec}f}" if "," in digits or v >= 1000 else f"{v:.{dec}f}"
    return f"{pre}{body}{post}"


def mood(text: str, fallback: str = "explaining") -> str:
    low = text.lower()
    for rx, m in MOODS:
        if re.search(rx, low):
            return m
    return fallback


def shots_for(scene, sentences, duration: float, first_scene: bool = False, offset: float = 0.0) -> list[Shot]:
    """Shot kinds: the video's first shot is the HOOK (big text from frame 1); then the chart once, numbers
    (counting up), key points once, and big words / the picture alone alternating, so every cut also changes
    what is on screen."""
    shots, used_chart, used_points, last = [], False, False, ""
    has_chart = scene.chart.kind != "none"
    for k, (s, e, txt) in enumerate(plan_shots(sentences, duration, offset)):
        num = NUM.search(txt)
        if k == 0 and first_scene:
            kind = "hook"
        elif k == 0:
            kind = "title"
        elif has_chart and not used_chart:
            kind, used_chart = "chart", True
        elif num and last != "number":
            kind = "number"
        elif scene.key_points and not used_points:
            kind, used_points = "points", True
        else:
            kind = "words" if last != "words" and offset + s < FAST_UNTIL else (
                "scene" if last != "scene" else "words")
        shots.append(Shot(s, e, kind, txt, {"num": num.group(0) if num else "", "phrase": key_phrase(txt)}))
        last = kind
    return shots


def change_times(shots_per_scene: list[list[Shot]], scene_starts: list[float]) -> list[float]:
    """Absolute times (s) of every visual change: each cut (new shot: new camera move and new card)."""
    out = []
    for shots, t0 in zip(shots_per_scene, scene_starts):
        out += [round(t0 + sh.start, 3) for sh in shots]
    return sorted(set(out))


def pacing_issues(times: list[float], total: float) -> list[str]:
    """Never static: a change at least every 3 s in the first 30 s, every 6 s after."""
    out = []
    pts = sorted(set(times + [total]))
    for a, b in zip(pts, pts[1:]):
        limit = FAST_MAX if a < FAST_UNTIL else MAX_SHOT
        if b - a > limit + 0.05:
            out.append(f"{b - a:.1f} s without a visual change at {a:.1f} s (max {limit:g} s)")
    return out


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
    if shot.kind == "hook":                      # frame 1: the hook in BIG text (number first if there is one)
        big = shot.data.get("num") or shot.data.get("phrase") or scene.heading
        box = (sx0, sy0, sx1 if portrait else sx0 + sw * 0.62, sy0 + sh * (0.5 if portrait else 0.6))
        ov.card(box, seed)
        y = ov.text(big, (box[0] + pad * 1.6, box[1] + pad * 1.4, box[2] - pad * 1.6,
                          box[1] + (box[3] - box[1]) * 0.62), int(size[1] * (0.11 if portrait else 0.16)),
                    align="center", max_lines=2)
        rest = shot.data.get("phrase", "") if shot.data.get("num") else scene.heading
        if rest and rest != big:
            ov.text(rest, (box[0] + pad, y, box[2] - pad, box[3] - pad), int(size[1] * (0.045 if portrait else 0.06)),
                    color=D.GREEN, align="center", max_lines=2)
    elif shot.kind == "words":                   # big on-screen words (pattern change between pictures)
        box = (sx0, sy0, sx1 if portrait else sx0 + sw * 0.55, sy0 + sh * (0.34 if portrait else 0.42))
        ov.card(box, seed)
        ov.text(shot.data.get("phrase") or scene.heading, (box[0] + pad * 1.4, box[1] + pad * 1.2,
                                                          box[2] - pad * 1.4, box[3] - pad * 1.2),
                int(size[1] * (0.075 if portrait else 0.11)), align="center", max_lines=2)
    elif shot.kind == "title":
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
    if move == "punch_in":                           # linear: visible motion from the very first frame
        e = t
    z0, z1 = {"zoom_in": (1.0, 1.12), "zoom_out": (1.12, 1.0), "punch_in": (1.0, 1.16)}.get(move, (1.08, 1.08))
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
    when the picture already shows Max acting in it). `offset`: the scene's start in the video (s)."""

    COUNT_UP = 0.6          # numbers count up on screen over the first 0.6 s of their shot

    def __init__(self, script, i: int, sentences, n_frames: int, offset: float = 0.0):
        self.scene = script.scenes[i]
        self.i = i
        self.offset = offset
        self.shots = shots_for(self.scene, sentences, n_frames / FPS, i == 0, offset)
        self._ov: dict = {}

    def _shot_at(self, t: float) -> int:
        for k, s in enumerate(self.shots):
            if t < s.end:
                return k
        return len(self.shots) - 1

    def overlay(self, k: int, portrait: bool, step: int = 6) -> Overlay:
        key = (k, portrait, step)
        if key not in self._ov:
            size = (1080, 1920) if portrait else (1920, 1080)
            shot = self.shots[k]
            if shot.kind == "number" and step < 6:
                shot = Shot(shot.start, shot.end, shot.kind, shot.text,
                            {**shot.data, "num": count_text(shot.data.get("num", ""), step / 6)})
            self._ov = {key: build_overlay(self.scene, shot, size, portrait, seed=self.i * 7 + k)}
        return self._ov[key]

    def move(self, k: int) -> str:
        if self.i == 0 and k == 0:
            return "punch_in"           # motion from frame 1 (no ease-in)
        return MOVES[(self.i * 3 + k) % len(MOVES)]

    def frame(self, f: int, portrait: bool) -> Image.Image:
        t = f / FPS
        k = self._shot_at(t)
        s = self.shots[k]
        size = (1080, 1920) if portrait else (1920, 1080)
        prog = min(1.0, max(0.0, (t - s.start) / max(0.1, s.end - s.start)))
        bgp = getattr(self.scene, "bg_path", None) or getattr(self.scene, "art_path", None)
        if bgp:
            out = camera(_load_bg(bgp), size, prog, self.move(k))
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
        step = min(6, int((t - s.start) / self.COUNT_UP * 6)) if s.kind == "number" else 6
        ov = self.overlay(k, portrait, step)
        out.paste(ov.img, (0, 0), ov.img)
        if self.offset + t >= NO_LOGO_UNTIL:      # no logo during the hook
            D.brand_mark(out, "tr", scale=1.0)
        return out


__all__ = ["DoodleFrames", "plan_shots", "shots_for", "change_times", "pacing_issues", "count_text", "key_phrase", "build_overlay", "camera", "Shot", "fit_text", "safe_box",
           "empty_ratio", "SAFE", "MIN_SHOT", "MAX_SHOT", "Overlay"]
