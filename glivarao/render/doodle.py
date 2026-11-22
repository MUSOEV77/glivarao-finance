"""Doodle theme frames (GLIVARAO hand-drawn explainer style; see art/doodle.py).

Each scene is cut into SHOTS of 6-10 seconds at sentence boundaries. Every shot is one drawing on off-white paper
(title + Max, a big circled number, a hand-drawn chart, a list of key points, a doodle icon, or an AI scene
illustration in the same style), and the camera slowly pans or zooms across it. Shots change with a hard cut.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from PIL import Image

from ..art import doodle as D

FPS = 24
MIN_SHOT, MAX_SHOT = 6.0, 10.0
CANVAS = 1.16          # drawings are made larger than the frame so the camera can move across them
NUM = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:trillion|billion|million|thousand|k))?|\d[\d,]*(?:\.\d+)?\s?(?:%|percent)"
                 r"|\d[\d,]*(?:\.\d+)?\s(?:trillion|billion|million)", re.I)
ICON_WORDS = [(r"house|home|mortgage|rent", "house"), (r"credit card|card|apr", "credit_card"),
              (r"bank|fdic|deposit", "bank"), (r"hospital|medical|doctor|health", "hospital"),
              (r"\bcar\b|auto|vehicle", "car"), (r"save|savings|emergency fund|interest earned", "coin_stack"),
              (r"recession|warning|risk|late|delinquen|default", "warning"), (r"deadline|calendar|date|month", "calendar"),
              (r"rate|fed|grow|rise|rising|higher", "growth_arrow"), (r"protect|insur|safe", "shield"),
              (r"idea|tip|trick|plan", "lightbulb")]
MOODS = [(r"\$\d|\d%|trillion|billion|record|jump|spike|doubled|soar|climb|faster than", "shocked"),
         (r"trap|debt|late|owe|worse|lose|risk|fail|crisis|problem|expensive|cost", "worried"), (r"why|how|what|\?", "thinking"),
         (r"save|win|pay off|free|plan|step|fix|protect", "confident"), (r"done|great|finally|debt-free", "cheering")]


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
    if len(out) > 1 and out[-1][1] - out[-1][0] < 4.0:      # no tiny last shot: merge it
        a, b = out[-2], out[-1]
        out[-2:] = [(a[0], b[1], f"{a[2]} {b[2]}")]
    split = []
    for s, e, txt in out:                                     # one long sentence -> several shots
        n = max(1, math.ceil((e - s) / MAX_SHOT))
        split += [(s + (e - s) * k / n, s + (e - s) * (k + 1) / n, txt) for k in range(n)]
    return split


def mood(text: str, fallback: str = "happy") -> str:
    low = text.lower()
    for rx, m in MOODS:
        if re.search(rx, low):
            return m
    return fallback


def icon_for(scene, text: str = "") -> str:
    low = f"{text} {scene.heading} {scene.narration[:200]}".lower()
    for rx, k in ICON_WORDS:
        if re.search(rx, low):
            return k
    return scene.illustration or "coin_stack"


def shots_for(scene, sentences, duration: float) -> list[Shot]:
    groups = plan_shots(sentences, duration)
    shots, used_chart, points = [], False, list(scene.key_points or [])
    has_chart = scene.chart.kind != "none"
    art = getattr(scene, "art_path", None)
    for k, (s, e, txt) in enumerate(groups):
        num = NUM.search(txt)
        if k == 0:
            kind = "title"
        elif has_chart and not used_chart and (k == 1 or "chart" in txt.lower() or num):
            kind, used_chart = "chart", True
        elif num:
            kind = "number"
        elif art and k == 2:
            kind = "art"
        elif points and k % 2 == 0:
            kind = "points"
        else:
            kind = "icon"
        shots.append(Shot(s, e, kind, txt, {"num": num.group(0) if num else ""}))
    return shots


# ------------------------------------------------------------------------------------------- drawings
def _scale(portrait: bool) -> tuple[int, int]:
    w, h = (1080, 1920) if portrait else (1920, 1080)
    return int(w * CANVAS), int(h * CANVAS)


def draw_shot(scene, shot: Shot, portrait: bool, k: int, seed: int = 0) -> Image.Image:
    """One drawing at canvas size (frame x CANVAS). Drawn at 2x and downscaled for smooth marker lines."""
    cw, ch = _scale(portrait)
    W2, H2 = cw * 2, ch * 2
    img = D.paper(W2, H2, seed=11 + seed % 5).copy()
    p = D.Pen(img, seed=seed * 31 + k, width=10)
    emo = mood(shot.text, "happy")
    # safe area: the camera never shows the outer CANVAS margin; captions sit in the lower part
    mx, my = W2 * (1 - 1 / CANVAS) / 2 + W2 * 0.04, H2 * (1 - 1 / CANVAS) / 2 + H2 * 0.04
    left, top, right, bottom = mx, my, W2 - mx, H2 - my - H2 * (0.2 if portrait else 0.16)
    bw, bh = right - left, bottom - top

    def heading(text, y, size, width):
        lines = D.wrap(text, size, width)[:3]
        for n, ln in enumerate(lines):
            p.text((left + (bw / 2 if portrait else 0), y + n * size * 1.0), ln, size, D.INK,
                   anchor="mm" if portrait else "lm", bold=max(2, size // 40))
        return y + len(lines) * size

    if shot.kind == "title":
        if portrait:
            y = heading(scene.heading, top + bh * 0.08, int(H2 * 0.05), bw * 0.9)
            D.icon(img, icon_for(scene, shot.text), left + bw * 0.5, y + bh * 0.2, bh * 0.12, seed + k)
            D.draw_max(img, left + bw * 0.5, bottom, u=bh * 0.055, emotion=emo, seed=5)
        else:
            hs = int(H2 * 0.095)
            y_end = heading(scene.heading, top + bh * 0.12, hs, bw * 0.6)
            last = D.wrap(scene.heading, hs, bw * 0.6)[:3][-1]
            D.underline(p, left, left + D.hand(hs).getlength(last), y_end - hs * 0.42, D.GREEN, 14)
            ic = icon_for(scene, shot.text)
            D.icon(img, ic, left + bw * 0.3, y_end + (bottom - y_end) * 0.5, min(bh * 0.24, (bottom - y_end) * 0.42),
                   seed + k)
            D.sparkle(p, left + bw * 0.3 + bh * 0.3, y_end + (bottom - y_end) * 0.22, bh * 0.09)
            D.draw_max(img, left + bw * 0.8, bottom, u=bh * 0.11, emotion=emo, seed=5)
    elif shot.kind == "number":
        num = shot.data.get("num", "")
        size = int(H2 * (0.09 if portrait else 0.16))
        cx, cy = (left + bw * 0.5, top + bh * 0.3) if portrait else (left + bw * 0.38, top + bh * 0.4)
        p.text((cx, cy), num, size, D.INK, bold=max(3, size // 30))
        tw = D.hand(size).getlength(num)
        p.d.ellipse((cx - tw * 0.62, cy - size * 0.75, cx + tw * 0.62, cy + size * 0.75), outline=D.GOLD,
                    width=int(size * 0.06))
        label = D.wrap(scene.heading, int(size * 0.38), bw * (0.85 if portrait else 0.6))[:2]
        for n, ln in enumerate(label):
            p.text((cx, cy + size * (0.98 + 0.45 * n)), ln, int(size * 0.38), D.GREEN, bold=1)
        D.sparkle(p, cx + tw * 0.66, cy - size * 0.72, size * 0.32)
        D.icon(img, icon_for(scene, shot.text), cx - tw * 0.55, cy + size * 2.1 if not portrait else cy + size * 2.6,
               size * 0.62, seed + k)
        if portrait:
            D.draw_max(img, left + bw * 0.5, bottom, u=bh * 0.05, emotion=emo, seed=5)
        else:
            D.draw_max(img, left + bw * 0.83, bottom, u=bh * 0.11, emotion=emo, seed=5)
    elif shot.kind == "chart":
        c = scene.chart
        vals = [float(v) for v in (c.values or [])]
        box = ((left + bw * 0.05, top + bh * 0.2, right - bw * 0.05, top + bh * 0.62) if portrait else
               (left + bw * 0.04, top + bh * 0.18, left + bw * 0.64, bottom - bh * 0.08))
        if c.kind == "bar_compare" and vals:
            D.bar_chart(img, box, vals[:6], (c.labels or [""] * len(vals))[:6], seed=seed + k)
        else:
            if vals and len(vals) >= 3:
                lo, hi = min(vals), max(vals)
                norm = [(v - lo) / ((hi - lo) or 1) * 0.75 + 0.15 for v in vals]
                cut = max(2, int(len(norm) * 0.7))
                D.spike_chart(img, box, history=norm[:cut], spike=norm[cut - 1:], seed=seed + k)
            else:
                D.spike_chart(img, box, seed=seed + k)
        title = (c.title or scene.heading)[:60]
        tsize, tmax = int(H2 * (0.035 if portrait else 0.055)), bw * (0.95 if portrait else 0.66)
        while tsize > 20 and D.hand(tsize).getlength(title) > tmax:
            tsize -= 2
        p.text(((left + right) / 2 if portrait else left + bw * 0.34, top + bh * 0.08), title, tsize, D.INK, bold=2)
        if portrait:
            D.draw_max(img, left + bw * 0.5, bottom, u=bh * 0.045, emotion=emo, seed=5)
        else:
            D.draw_max(img, left + bw * 0.84, bottom, u=bh * 0.11, emotion=emo, seed=5)
    elif shot.kind == "points":
        pts = [x for x in (scene.key_points or []) if x][:4]
        y = heading(scene.heading, top + bh * 0.08, int(H2 * (0.045 if portrait else 0.07)), bw * 0.9)
        size = int(H2 * (0.034 if portrait else 0.052))
        y += size * 0.6
        for n, t in enumerate(pts):
            p.line([(left + size * 0.2, y + size * 0.05), (left + size * 0.45, y + size * 0.35),
                    (left + size * 0.95, y - size * 0.35)], size * 0.12, D.GREEN)
            for m, ln in enumerate(D.wrap(t, size, bw * (0.85 if portrait else 0.55))[:2]):
                p.text((left + size * 1.3, y + m * size), ln, size, D.INK, anchor="lm")
            y += size * 2.3
        if not portrait:
            D.draw_max(img, left + bw * 0.83, bottom, u=bh * 0.11, emotion="confident", seed=5)
    elif shot.kind == "art":
        try:
            from ..art.ai_visuals import load_art

            art = load_art(scene.art_path, int(min(bw, bh) * (0.75 if portrait else 0.9)))
        except Exception:  # noqa: BLE001
            art = None
        if art is not None:
            ax = int(left + (bw - art.width) / 2) if portrait else int(left + bw * 0.04)
            ay = int(top + bh * 0.08)
            # multiply the AI drawing onto the paper so it reads as drawn on the same sheet
            region = img.crop((ax, ay, ax + art.width, ay + art.height))
            from PIL import ImageChops

            img.paste(ImageChops.multiply(region, art.convert("RGB")), (ax, ay))
            if not portrait:
                D.draw_max(img, left + bw * 0.84, bottom, u=bh * 0.11, emotion=emo, seed=5)
        else:
            shot = Shot(shot.start, shot.end, "icon", shot.text)
    if shot.kind == "icon":
        kind = icon_for(scene, shot.text)
        if portrait:
            D.icon(img, kind, left + bw * 0.5, top + bh * 0.3, bh * 0.14, seed + k)
            label = D.wrap(scene.heading, int(H2 * 0.04), bw * 0.9)[:2]
            for n, ln in enumerate(label):
                p.text((left + bw * 0.5, top + bh * 0.55 + n * H2 * 0.045), ln, int(H2 * 0.04), D.INK, bold=2)
            D.draw_max(img, left + bw * 0.5, bottom, u=bh * 0.045, emotion=emo, seed=5)
        else:
            D.icon(img, kind, left + bw * 0.3, top + bh * 0.45, bh * 0.25, seed + k)
            p.arrow(left + bw * 0.5, top + bh * 0.3, left + bw * 0.42, top + bh * 0.38, 9, D.GREEN, head=30)
            label = D.wrap(scene.heading, int(H2 * 0.06), bw * 0.4)[:2]
            for n, ln in enumerate(label):
                p.text((left + bw * 0.3, top + bh * 0.82 + n * H2 * 0.06), ln, int(H2 * 0.06), D.INK, bold=2)
            D.draw_max(img, left + bw * 0.8, bottom, u=bh * 0.11, emotion=emo, seed=5,
                       point_to=(left + bw * 0.45, top + bh * 0.45))
    return D.finish(img, (cw, ch))


# ------------------------------------------------------------------------------------------- camera
MOVES = ("zoom_in", "pan_right", "zoom_out", "pan_left", "pan_up")


def camera(canvas: Image.Image, frame_size: tuple[int, int], t: float, move: str) -> Image.Image:
    """Slow move across the drawing; t in 0..1 (eased). Never shows past the canvas edge."""
    e = t * t * (3 - 2 * t)
    cw, ch = canvas.size
    fw, fh = frame_size
    z0, z1 = {"zoom_in": (1.0, 1.09), "zoom_out": (1.09, 1.0)}.get(move, (1.04, 1.04))
    z = z0 + (z1 - z0) * e
    vw, vh = cw / z / CANVAS * 1.0, ch / z / CANVAS * 1.0      # view size in canvas pixels
    vw, vh = min(vw, cw), min(vh, ch)
    mx, my = (cw - vw), (ch - vh)
    fx, fy = {"pan_right": (0.25 + 0.5 * e, 0.5), "pan_left": (0.75 - 0.5 * e, 0.5),
              "pan_up": (0.5, 0.7 - 0.4 * e)}.get(move, (0.5, 0.5))
    x0, y0 = mx * fx, my * fy
    return canvas.transform(frame_size, Image.EXTENT, (x0, y0, x0 + vw, y0 + vh), Image.BICUBIC)


class DoodleFrames:
    def __init__(self, script, i: int, sentences, n_frames: int):
        self.scene = script.scenes[i]
        self.i = i
        self.shots = shots_for(self.scene, sentences, n_frames / FPS)
        self._cache: dict = {}

    def _shot_at(self, t: float) -> int:
        for k, s in enumerate(self.shots):
            if t < s.end:
                return k
        return len(self.shots) - 1

    def frame(self, f: int, portrait: bool) -> Image.Image:
        t = f / FPS
        k = self._shot_at(t)
        key = (k, portrait)
        if key not in self._cache:
            self._cache = {key: draw_shot(self.scene, self.shots[k], portrait, k, seed=self.i)}  # one at a time
        s = self.shots[k]
        prog = min(1.0, max(0.0, (t - s.start) / max(0.1, s.end - s.start)))
        size = (1080, 1920) if portrait else (1920, 1080)
        out = camera(self._cache[key], size, prog, MOVES[(self.i * 3 + k) % len(MOVES)])
        D.brand_mark(out, "tr", scale=1.0)   # fixed on screen (not moved by the camera)
        return out


__all__ = ["DoodleFrames", "plan_shots", "shots_for", "draw_shot", "camera", "Shot", "MIN_SHOT", "MAX_SHOT"]
