"""Illustrated environments ("sets") drawn on a stage larger than the frame so the camera can move.

Each set returns a static RGB background plus layout anchors:
  floor_y   : where characters stand
  board     : (x0, y0, x1, y1) area where charts / icons / notes are presented
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image

from ..art.style import Ink, paper

STAGE_W, STAGE_H = 2208, 1242  # 1.15 x 1920x1080: room for pans and push-ins


@dataclass(frozen=True)
class SetLayout:
    name: str
    floor_y: int
    board: tuple[int, int, int, int]


LAYOUTS = {
    "studio": SetLayout("studio", 1130, (930, 200, 2060, 880)),
    "home": SetLayout("home", 1140, (960, 190, 2040, 860)),
    "city": SetLayout("city", 1150, (950, 170, 2070, 860)),
    "bank": SetLayout("bank", 1140, (960, 200, 2050, 880)),
    "board": SetLayout("board", 1150, (880, 170, 2080, 900)),
}
SETS = list(LAYOUTS)


def _wall(ink: Ink, color, floor_y, floor_color):
    w, h = ink.img.size
    ink.d.rectangle((0, 0, w, floor_y - 40), fill=color)
    ink.d.rectangle((0, floor_y - 40, w, h), fill=floor_color)
    ink.line([(-20, floor_y - 40), (w + 20, floor_y - 44)], width=6)


def _studio(ink: Ink, L: SetLayout):
    _wall(ink, (238, 229, 210), L.floor_y, (205, 170, 128))
    for x in range(0, STAGE_W, 120):  # soft wallpaper stripes
        ink.d.rectangle((x, 0, x + 60, L.floor_y - 42), fill=(242, 234, 216))
    for x in range(-40, STAGE_W, 210):  # floorboards
        ink.line([(x, L.floor_y - 38), (x - 90, STAGE_H)], color=(178, 140, 100), width=3, wobble=1)
    ink.rect((120, 170, 470, 430), fill=(156, 192, 236))  # window
    ink.line([(295, 170), (295, 430)], width=6)
    ink.line([(120, 300), (470, 300)], width=6)
    ink.ellipse((150, 200, 230, 240), fill="white", outline=None)
    ink.rect((180, L.floor_y - 230, 270, L.floor_y - 120), fill=(205, 127, 50))  # plant pot
    for dx, dy in ((-60, -330), (0, -380), (60, -320), (-20, -300), (40, -280)):
        ink.ellipse((225 + dx - 34, L.floor_y + dy - 18, 225 + dx + 34, L.floor_y + dy + 18), fill="green")
        ink.line([(225, L.floor_y - 230), (225 + dx, L.floor_y + dy)], color="green", width=5)


def _home(ink: Ink, L: SetLayout):
    _wall(ink, (226, 214, 236), L.floor_y, (172, 132, 98))
    ink.rect((80, 160, 420, 440), fill=(156, 192, 236))
    ink.line([(250, 160), (250, 440)], width=6)
    ink.ellipse((40, L.floor_y - 30, 900, L.floor_y + 60), fill=(214, 76, 66), width=4)  # rug
    ink.rect((60, L.floor_y - 330, 640, L.floor_y - 150), fill=(58, 110, 186))  # couch
    ink.rect((40, L.floor_y - 260, 110, L.floor_y - 110), fill=(58, 110, 186))
    ink.rect((590, L.floor_y - 260, 660, L.floor_y - 110), fill=(58, 110, 186))
    ink.rect((60, L.floor_y - 200, 640, L.floor_y - 110), fill=(80, 128, 200))
    ink.line([(700, L.floor_y - 420), (700, L.floor_y - 60)], width=6)  # lamp
    ink.poly([(640, L.floor_y - 420), (760, L.floor_y - 420), (730, L.floor_y - 500), (670, L.floor_y - 500)],
             fill=(242, 190, 60))


def _city(ink: Ink, L: SetLayout):
    ink.d.rectangle((0, 0, STAGE_W, L.floor_y), fill=(200, 222, 238))
    rng = random.Random(7)
    x = -40
    while x < STAGE_W:
        bw, bh = rng.randint(140, 260), rng.randint(320, 760)
        col = rng.choice([(150, 162, 186), (170, 180, 200), (134, 148, 176)])
        ink.rect((x, L.floor_y - 60 - bh, x + bw, L.floor_y - 50), fill=col, width=4)
        for wy in range(L.floor_y - 30 - bh, L.floor_y - 110, 70):
            for wx in range(x + 22, x + bw - 30, 52):
                ink.d.rectangle((wx, wy, wx + 24, wy + 34), fill=(242, 226, 150) if rng.random() < .35
                                else (226, 234, 244))
        x += bw + rng.randint(6, 30)
    ink.d.rectangle((0, L.floor_y - 50, STAGE_W, STAGE_H), fill=(150, 146, 140))
    ink.line([(-20, L.floor_y - 50), (STAGE_W + 20, L.floor_y - 50)], width=6)
    for x in range(40, STAGE_W, 260):
        ink.line([(x, L.floor_y + 40), (x + 120, L.floor_y + 40)], color="white", width=8)
    ink.line([(110, L.floor_y - 50), (110, L.floor_y - 520)], width=10)  # street lamp
    ink.ellipse((75, L.floor_y - 570, 145, L.floor_y - 510), fill=(242, 226, 150))


def _bank(ink: Ink, L: SetLayout):
    _wall(ink, (236, 230, 216), L.floor_y, (190, 184, 172))
    for x in (90, 330, 570):
        ink.rect((x, 150, x + 90, L.floor_y - 60), fill="white")
        ink.rect((x - 20, 120, x + 110, 160), fill="paper_dark")
    ink.rect((40, 60, 800, 125), fill="paper_dark")
    ink.text((420, 92), "SAVINGS & LOAN", 54, anchor="mm")
    for x in range(-60, STAGE_W, 160):
        ink.line([(x, L.floor_y - 30), (x + 160, STAGE_H)], color=(170, 164, 152), width=3, wobble=1)


def _board(ink: Ink, L: SetLayout):
    _wall(ink, (232, 226, 212), L.floor_y, (196, 160, 118))
    x0, y0, x1, y1 = L.board
    ink.rect((x0 - 40, y0 - 40, x1 + 40, y1 + 40), fill=(150, 104, 64), width=7)  # frame
    ink.d.rectangle((x0 - 18, y0 - 18, x1 + 18, y1 + 18), fill=(52, 82, 66))      # chalkboard
    ink.rect((x0 + 200, y1 + 40, x1 - 200, y1 + 64), fill=(150, 104, 64))           # chalk ledge
    ink.rect((180, 200, 520, 520), fill="white")                                    # poster
    ink.line([(220, 470), (300, 400), (360, 430), (480, 260)], color="green", width=10)
    ink.text((350, 245), "GOALS", 44, anchor="mm")


DRAWERS = {"studio": _studio, "home": _home, "city": _city, "bank": _bank, "board": _board}


@lru_cache(maxsize=8)
def background(name: str) -> Image.Image:
    L = LAYOUTS[name]
    img = paper(STAGE_W, STAGE_H, seed=5).copy()
    ink = Ink(img, seed=hash(name) % 997, wobble=2.0, width=6)
    DRAWERS[name](ink, L)
    # unify with a light paper-grain overlay so every set feels hand-painted on the same stock
    grain = paper(STAGE_W, STAGE_H, seed=9)
    return Image.blend(img, grain, 0.12)
