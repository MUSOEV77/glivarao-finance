"""Frame-by-frame scene compositor.

Layout is computed once per scene; static layers are cached per "boil" variant so a 17-minute
video renders in minutes. Per frame we only paste the talking character and (while animating) the chart.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from PIL import Image

from ..art.characters import draw_character
from ..art.charts import draw_chart
from ..art.illustrations import draw_illustration
from ..art.style import Ink, font, paper, wrap
from ..models import Scene

BOILS = 3
MOUTH_LEVELS = (0.0, 0.35, 0.65, 1.0)


@dataclass(frozen=True)
class Layout:
    w: int
    h: int
    portrait: bool

    @classmethod
    def for_format(cls, fmt: str) -> "Layout":
        return cls(1080, 1920, True) if fmt == "short" else cls(1920, 1080, False)


@lru_cache(maxsize=256)
def _character(name: str, pose: str, mouth: float, blink: bool, boil: int, scale: float) -> Image.Image:
    return draw_character(name, pose=pose, mouth=mouth, blink=blink, boil=boil, scale=scale)


def _quantize_mouth(v: float) -> float:
    return min(MOUTH_LEVELS, key=lambda m: abs(m - v))


class SceneRenderer:
    def __init__(self, scene: Scene, layout: Layout, index: int, total: int):
        self.scene, self.L, self.index, self.total = scene, layout, index, total
        self.has_chart = scene.chart.kind != "none"
        self._static: dict[int, Image.Image] = {}
        self._chart_done: dict[int, Image.Image] = {}
        L = layout
        if L.portrait:
            self.char_scale = 0.95
            self.char_pos = (L.w // 2 - int(260 * 0.95), 1200)
            self.chart_box = (30, 360, 1020, 760)  # x, y, w, h
            self.illo_box = (260, 430, 560)
        else:
            self.char_scale = 1.0
            self.char_pos = (30, 330)
            self.chart_box = (600, 150, 1270, 740)
            self.illo_box = (760 if scene.key_points else 960, 210, 520)

    # -- static layer -----------------------------------------------------------------
    def _static_layer(self, boil: int) -> Image.Image:
        if boil in self._static:
            return self._static[boil]
        L, s = self.L, self.scene
        img = paper(L.w, L.h).copy()
        ink = Ink(img, seed=boil * 101 + self.index, wobble=2.0, width=6)
        if L.portrait:
            lines = wrap(s.heading, 96, L.w - 140)[:2]
            for i, line in enumerate(lines):
                ink.text((L.w // 2, 200 + i * 100), line, 96, anchor="mm")
            ink.line([(L.w // 2 - 260, 200 + len(lines) * 100 - 30), (L.w // 2 + 260, 200 + len(lines) * 100 - 30)],
                     color="green", width=8)
        else:
            ink.text((70, 40), s.heading, 84)
            tw = ink.d.textlength(s.heading, font=font(84))
            ink.line([(70, 140), (70 + tw, 136)], color="green", width=8)
            ink.text((L.w - 40, 40), f"{self.index + 1}/{self.total}", 34, color="grey", anchor="ra")
        ink.text((L.w - 30, L.h - 24) if not L.portrait else (L.w // 2, 60), "GLIVARAO Finance", 30,
                 color="grey", anchor="rb" if not L.portrait else "mm")
        if not self.has_chart:
            x, y, size = self.illo_box
            illo = draw_illustration(s.illustration, boil=boil, size=size)
            img.paste(illo, (x, y), illo)
            if s.key_points and not L.portrait:
                for i, point in enumerate(s.key_points[:3]):
                    self._sticky(ink, 1340, 230 + i * 190, point, boil + i)
        self._static[boil] = img
        return img

    def _sticky(self, ink: Ink, x: int, y: int, text: str, seed: int):
        tilt = (-1) ** seed * 6
        ink.poly([(x, y + tilt), (x + 500, y), (x + 500, y + 160), (x, y + 160 - tilt)], fill="sticky", width=4)
        for j, line in enumerate(wrap(text, 46, 450)[:2]):
            ink.text((x + 25, y + 30 + j * 54), line, 46)

    def _draw_chart(self, w: int, h: int, progress: float, boil: int) -> Image.Image:
        # Shorts are watched on phones: draw smaller and upscale so chart text is ~1.4x larger.
        if not self.L.portrait:
            return draw_chart(self.scene.chart, w, h, progress, boil)
        k = 1.4
        small = draw_chart(self.scene.chart, int(w / k), int(h / k), progress, boil)
        return small.resize((w, h), Image.LANCZOS)

    # -- per-frame ----------------------------------------------------------------------
    def frame(self, f: int, n_frames: int, fps: int, loudness: float) -> Image.Image:
        boil = (f // 2) % BOILS
        img = self._static_layer(boil).copy()
        t = f / fps
        if self.has_chart:
            x, y, w, h = self.chart_box
            progress = min(1.0, max(0.0, (t - 0.3) / max(1.5, 0.6 * n_frames / fps)))
            if progress >= 1.0:
                if boil not in self._chart_done:
                    self._chart_done[boil] = self._draw_chart(w, h, 1.0, boil)
                chart = self._chart_done[boil]
            else:
                chart = self._draw_chart(w, h, progress, boil)
            img.paste(chart, (x, y), chart)

        mouth = _quantize_mouth(loudness)
        blink = (f % int(fps * 3.7)) == 0
        bob = int(6 * math.sin(t * 2.4))
        cx, cy = self.char_pos
        s = self.scene
        if s.character == "duo":
            sc = self.char_scale * 0.78
            a = _character("max", s.pose, mouth, blink, boil, sc)
            b = _character("penny", "cheer" if s.pose == "cheer" else "talk", 0.0, False, boil, sc * 0.9)
            if self.L.portrait:
                img.paste(a, (cx - 170, cy + 140 + bob), a)
                img.paste(b, (cx + 250, cy + 210 - bob), b)
            else:
                img.paste(a, (cx - 20, cy + 160 + bob), a)
                if not self.has_chart:  # the chart occupies Penny's spot in landscape
                    img.paste(b, (cx + 290, cy + 240 - bob), b)
        else:
            ch = _character(s.character, s.pose, mouth, blink, boil, self.char_scale)
            img.paste(ch, (cx, cy + bob), ch)

        # quick pop-in fade for the first frames of a scene
        if f < 3:
            prev = paper(self.L.w, self.L.h)
            img = Image.blend(prev, img, (f + 1) / 3)
        return img


def frame_bytes(img: Image.Image) -> bytes:
    return np.asarray(img.convert("RGB"), dtype=np.uint8).tobytes()
