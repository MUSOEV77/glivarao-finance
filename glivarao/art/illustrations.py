"""Original hand-drawn economic illustrations (icons), drawn procedurally on a 400x400 RGBA canvas."""
from __future__ import annotations

import math

from PIL import Image

from .style import Ink

SIZE = 400


def _new(boil: int):
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return img, Ink(img, seed=boil * 13 + 5, wobble=2.2, width=7)


def piggy_bank(ink: Ink):
    ink.ellipse((70, 120, 330, 320), fill="red_light")
    ink.ellipse((290, 180, 360, 250), fill="red_light")
    ink.d.ellipse((315, 200, 325, 212), fill=(38, 34, 46))
    ink.d.ellipse((335, 200, 345, 212), fill=(38, 34, 46))
    ink.poly([(130, 140), (150, 80), (185, 130)], fill="red_light")
    for x in (110, 250):
        ink.rect((x, 300, x + 35, 350), fill="red_light")
    ink.line([(170, 125), (240, 125)], width=10)
    ink.ellipse((230, 160, 260, 190), fill="white", width=4)
    ink.line([(70, 210), (40, 190), (50, 230)], width=6)


def house(ink: Ink):
    ink.rect((90, 190, 310, 350), fill="blue_light")
    ink.poly([(60, 200), (200, 70), (340, 200)], fill="red")
    ink.rect((175, 260, 225, 350), fill="copper")
    ink.rect((110, 220, 160, 265), fill="white")
    ink.rect((240, 220, 290, 265), fill="white")
    ink.rect((260, 90, 295, 160), fill="grey")


def coin_stack(ink: Ink):
    for i in range(5):
        y = 300 - i * 38
        ink.ellipse((110, y - 30, 290, y + 30), fill="gold")
    ink.text((200, 120), "$", 70, anchor="mm")
    ink.ellipse((250, 80, 350, 180), fill="gold")
    ink.text((300, 130), "¢", 56, anchor="mm")


def credit_card(ink: Ink):
    ink.rect((50, 110, 350, 300), fill="blue")
    ink.rect((50, 145, 350, 185), fill="ink", outline=None)
    ink.rect((80, 210, 150, 255), fill="gold")
    for x in (180, 230, 280):
        ink.line([(x, 265), (x + 35, 265)], color="white", width=6)


def dollar_bill(ink: Ink):
    ink.rect((40, 120, 360, 290), fill="green_light")
    ink.rect((60, 140, 340, 270), outline="green", width=4)
    ink.ellipse((150, 150, 250, 260), fill="white", width=5)
    ink.text((200, 205), "$", 80, color="green", anchor="mm")
    for x in (85, 315):
        ink.text((x, 170), "1", 40, color="green", anchor="mm")


def growth_arrow(ink: Ink):
    ink.line([(60, 340), (60, 60)], width=6)
    ink.line([(60, 340), (350, 340)], width=6)
    ink.line([(80, 300), (150, 250), (200, 270), (260, 170), (330, 90)], color="green", width=14)
    ink.poly([(330, 60), (350, 120), (290, 100)], fill="green")


def shield(ink: Ink):
    ink.poly([(200, 50), (330, 100), (310, 260), (200, 350), (90, 260), (70, 100)], fill="blue_light")
    ink.line([(140, 200), (190, 250), (270, 150)], color="green", width=16)


def calendar(ink: Ink):
    ink.rect((70, 90, 330, 340), fill="white")
    ink.rect((70, 90, 330, 150), fill="red")
    for r in range(3):
        for col in range(4):
            x, y = 100 + col * 58, 175 + r * 52
            ink.rect((x, y, x + 36, y + 32), fill="paper_dark", width=3)
    for x in (130, 270):
        ink.line([(x, 65), (x, 115)], width=10)


def shopping_cart(ink: Ink):
    ink.line([(40, 90), (100, 90), (140, 270), (320, 270)], width=8)
    ink.poly([(110, 130), (340, 130), (310, 240), (135, 240)], fill="blue_light")
    for x in (160, 290):
        ink.ellipse((x - 25, 280, x + 25, 330), fill="grey")


def paycheck(ink: Ink):
    ink.rect((50, 110, 350, 300), fill="white")
    ink.text((80, 135), "PAY TO", 32)
    ink.line([(190, 160), (320, 160)], width=4)
    ink.text((80, 200), "$", 50, color="green")
    ink.rect((120, 200, 320, 245), fill="paper_dark", width=4)
    ink.line([(220, 275), (320, 270)], width=4)


def bank(ink: Ink):
    ink.poly([(50, 140), (200, 60), (350, 140)], fill="paper_dark")
    ink.rect((60, 140, 340, 170), fill="paper_dark")
    for x in (90, 160, 230, 300):
        ink.rect((x - 15, 175, x + 15, 310), fill="white", width=5)
    ink.rect((50, 310, 350, 345), fill="paper_dark")
    ink.text((200, 115), "$", 46, anchor="mm")


def scale(ink: Ink):
    ink.line([(200, 70), (200, 330)], width=10)
    ink.line([(110, 340), (290, 340)], width=10)
    ink.line([(70, 120), (330, 100)], width=8)
    for x, y in ((70, 120), (330, 100)):
        ink.line([(x, y), (x - 40, y + 110)], width=4)
        ink.line([(x, y), (x + 40, y + 110)], width=4)
        ink.poly([(x - 55, y + 110), (x + 55, y + 110), (x + 35, y + 140), (x - 35, y + 140)], fill="gold")


def hourglass(ink: Ink):
    ink.rect((100, 50, 300, 80), fill="copper")
    ink.rect((100, 320, 300, 350), fill="copper")
    ink.poly([(120, 80), (280, 80), (210, 200), (280, 320), (120, 320), (190, 200)], fill="blue_light")
    ink.poly([(150, 320), (250, 320), (200, 260)], fill="gold", outline=None)
    ink.poly([(150, 110), (250, 110), (200, 180)], fill="gold", outline=None)


def warning(ink: Ink):
    ink.poly([(200, 50), (350, 330), (50, 330)], fill="gold")
    ink.line([(200, 140), (200, 240)], width=22)
    ink.ellipse((186, 265, 214, 293), fill="ink", outline=None)


def lightbulb(ink: Ink):
    ink.ellipse((110, 50, 290, 240), fill="gold")
    ink.rect((155, 235, 245, 300), fill="grey")
    for y in (255, 280):
        ink.line([(155, y), (245, y)], width=4)
    for a in range(0, 360, 45):
        if 60 < a < 120:
            continue
        r = math.radians(a)
        ink.line([(200 + 115 * math.cos(r), 145 - 115 * math.sin(r)),
                  (200 + 165 * math.cos(r), 145 - 165 * math.sin(r))], width=6)


def target(ink: Ink):
    for i, col in enumerate(["red", "white", "red", "white", "red"]):
        m = i * 32
        ink.ellipse((60 + m, 60 + m, 340 - m, 340 - m), fill=col)
    ink.line([(200, 200), (350, 70)], width=8)
    ink.poly([(340, 50), (370, 90), (330, 80)], fill="green")


DRAWERS = {f.__name__: f for f in [piggy_bank, house, coin_stack, credit_card, dollar_bill, growth_arrow, shield,
                                    calendar, shopping_cart, paycheck, bank, scale, hourglass, warning, lightbulb,
                                    target]}


def draw_illustration(name: str, boil: int = 0, size: int = SIZE) -> Image.Image:
    img, ink = _new(boil)
    DRAWERS.get(name, coin_stack)(ink)
    return img if size == SIZE else img.resize((size, size), Image.LANCZOS)
