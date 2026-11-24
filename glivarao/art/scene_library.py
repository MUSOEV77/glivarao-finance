"""Reusable full-frame scene backgrounds for the doodle style (made once with Nano Banana, reused forever).

Most shots in a video don't need their own AI picture: a rich, full-frame hand-drawn place (a city street, a bank
lobby, a kitchen table with bills, ...) with Max (a cutout) standing in it and our code-drawn card (number, chart,
title) on top works for most of them. The few key moments get their own AI scene with Max acting in it
(art/ai_visuals.py). The library images are generated lazily the first time a place is needed, then cached in
data/scene_library/ (landscape 16:9 at 2K for long videos, portrait 9:16 at 1K for Shorts).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

PLACES = {
    "kitchen_bills": "a cozy American kitchen table at night covered with bills, envelopes, a laptop, a calculator, "
                     "a coffee mug and a desk lamp, warm light, a window with the city behind",
    "city_street": "a quiet American street corner with two simple shop fronts and one parked car",
    "suburb": "a sunny American suburban street with rows of houses, lawns, mailboxes, a for-sale sign with no words, "
              "kids biking",
    "bank_lobby": "a big bank lobby with marble columns, teller windows, a vault door, people waiting in line",
    "living_room": "a comfortable living room with a sofa, a TV, plants, shelves and a family budget board on the wall",
    "office": "a bright open office with desks, computers, plants, coworkers chatting, big windows",
    "grocery": "a grocery store aisle with shelves full of products, shopping carts and shoppers",
    "hospital": "a hospital reception area with a front desk, chairs, a nurse, patients waiting, clipboards",
    "car_lot": "a car dealership lot with rows of shiny cars, balloons, a salesperson and a small office building",
    "skyline": "a downtown city skyline with tall office towers and a busy plaza with people at sunset",
    "capitol": "a big neoclassical government building with columns and wide steps (generic, not a real building), "
               "a plaza with small people, flags without symbols",
    "home_office": "a home office desk with papers, a calculator, a piggy bank, a laptop, a plant and a window",
}
KEYWORDS = [(r"medical|hospital|doctor|health|insur|aca\b", "hospital"),
            (r"car\b|auto|vehicle|dealer", "car_lot"), (r"bank|fdic|deposit|vault|teller", "bank_lobby"),
            (r"house|home price|mortgage|rent|neighborhood|housing", "suburb"),
            (r"national debt|government|treasury|congress|fed\b|federal reserve|policy", "capitol"),
            (r"stock|market|401\(k\)|invest|recession|economy|jobs", "skyline"),
            (r"grocer|prices|inflation|shopping|buy now|bnpl|checkout", "grocery"),
            (r"bill|card|debt|payment|interest|apr|statement|minimum", "kitchen_bills"),
            (r"budget|save|savings|emergency|family|household", "living_room"),
            (r"tax|irs|return|refund|paperwork|form", "home_office"),
            (r"job|work|paycheck|salary|employer", "office")]
STYLE = ("SIMPLE, uncluttered hand-drawn cartoon illustration with few large shapes and no small details or crowds filling the WHOLE frame edge to edge (no empty paper, no "
         "border): bold slightly wobbly black ink outlines, flat warm colors with deep green (#1f8a4c) and gold "
         "(#e0a526) accents, simple cel shading, friendly cartoon people with simple faces (no real or famous "
         "people). Keep the lower-right third a little calmer because a character will stand there. No text, no "
         "letters, no numbers, no words on signs, no logos, no watermark.")


def place_for(text: str, avoid: str | None = None, avoid_set=frozenset()) -> str:
    """The place that fits the narration; never `avoid` (the previous scene's place) and, where another place
    fits or any unused place is left, none of `avoid_set` (places the previous video used)."""
    low = text.lower()
    banned = set(avoid_set) | ({avoid} if avoid else set())
    for rx, key in KEYWORDS:
        if re.search(rx, low) and key not in banned:
            return key
    for key in ["city_street", "living_room"] + list(PLACES):
        if key not in banned:
            return key
    return "city_street" if avoid != "city_street" else "living_room"


def library_dir(settings) -> Path:
    return Path(getattr(settings, "doodle_library_dir", "data/scene_library"))


def path_for(settings, key: str, portrait: bool) -> Path:
    return library_dir(settings) / f"{key}_{'portrait' if portrait else 'landscape'}_v2.png"   # v2: simple style


def background(settings, key: str, portrait: bool, gi=None) -> Path | None:
    """The library picture for a place (generated the first time if an image client is given)."""
    p = path_for(settings, key, portrait)
    if p.exists():
        return p
    if gi is None:
        return None
    from .gemini_image import ImageUnavailable

    try:
        img = gi.generate(f"{PLACES[key].capitalize()}. {STYLE}", "1K" if portrait else "2K",
                          "9:16" if portrait else "16:9", [])
    except ImageUnavailable as exc:
        log.warning("scene library %s: %s", key, exc)
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p, "PNG")
    return p


def any_cached(settings, portrait: bool) -> list[Path]:
    d = library_dir(settings)
    return sorted(d.glob(f"*_{'portrait' if portrait else 'landscape'}.png")) if d.exists() else []


__all__ = ["PLACES", "place_for", "background", "path_for", "any_cached", "library_dir", "STYLE"]
