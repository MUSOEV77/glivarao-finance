"""Give every scene of a doodle-style video a FULL picture before rendering.

* Key scenes (DOODLE_KEY_SCENES_LONG=6 per long video at 2K 16:9, DOODLE_KEY_SCENES_SHORT=1 per Short at 1K 9:16):
  Nano Banana draws the moment with Max acting in it (his 8-pose style sheet is sent as the reference).
* Every other scene: a reusable place from the scene library (made once, cached) with the Max cutout whose pose
  matches the mood of the narration.
* Charts, numbers, titles: drawn by code on top (render/doodle.py).
If Max hasn't been designed yet or no picture can be had at all, DoodleUnavailable is raised and the caller makes
this video in the editorial style instead (never a half-empty doodle video).
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import max_assets, scene_library
from .gemini_image import GeminiImage, ImageUnavailable

log = logging.getLogger(__name__)


class DoodleUnavailable(RuntimeError):
    pass


def key_scene_prompt(scene, portrait: bool) -> str:
    gist = " ".join(scene.narration.replace("*", "").split())[:420]
    place = scene_library.PLACES[scene_library.place_for(f"{scene.heading} {scene.narration}")]
    return (f"{'Tall 9:16' if portrait else 'Wide 16:9'} full-frame scene for a personal-finance explainer video: "
            f"\"{scene.heading}\". What the narrator says: {gist} Show the moment as a lively scene set in {place}, "
            f"with {max_assets.CHARACTER} acting in it with clear body language and a readable facial expression "
            "(exactly as in the reference sheet: same face, glasses, hair, sweater, coin pin). Max is on the "
            f"{'lower half' if portrait else 'right half'} of the picture; keep the "
            f"{'top third' if portrait else 'upper-left area'} a little calmer for a text card. "
            f"{scene_library.STYLE}")


def key_indices(script, n: int) -> list[int]:
    if n <= 0 or not script.scenes:
        return []
    m = len(script.scenes) - 1 if len(script.scenes) > 1 else 1      # the last scene is the sign-off
    pref = [i for i, s in enumerate(script.scenes[:m]) if s.beat in ("creator", "case", "question", "myth")]
    spread = [int(k * m / n) for k in range(n)]
    out = []
    for i in [0] + pref + spread:
        if i not in out and i < len(script.scenes):
            out.append(i)
        if len(out) >= n:
            break
    return sorted(out)


def prepare(script, out: Path, settings, store=None, gi=None) -> tuple:
    """Returns (script with bg_path / max_pose_path on every scene, stats)."""
    from ..render.doodle import mood

    if not max_assets.ready(settings):
        raise DoodleUnavailable("Max has not been designed yet (python -m glivarao style-samples)")
    portrait = script.format == "short"
    if gi is None:
        try:
            gi = GeminiImage(settings)
        except ImageUnavailable as exc:
            log.warning("doodle: no image API (%s): library pictures only", exc)
    sheet = max_assets.sheet_path(settings).read_bytes()
    n_key = settings.doodle_key_scenes_short if portrait else settings.doodle_key_scenes_long
    keys = key_indices(script, n_key)
    scenes, stats, prev_place = list(script.scenes), {"key_ai": 0, "library": 0, "note": ""}, None
    start = gi.spent_usd if gi is not None else 0.0
    for i, sc in enumerate(scenes):
        upd = None
        if i in keys and gi is not None:
            try:
                img = gi.generate(key_scene_prompt(sc, portrait), "1K" if portrait else "2K",
                                  "9:16" if portrait else "16:9", [sheet])
                dst = out / "scene_art" / f"key_{i:02d}.png"
                dst.parent.mkdir(parents=True, exist_ok=True)
                img.save(dst, "PNG")
                upd = {"bg_path": str(dst), "max_pose_path": None, "art_path": None}
                stats["key_ai"] += 1
            except ImageUnavailable as exc:
                stats["note"] = str(exc)
        if upd is None:
            place = scene_library.place_for(f"{sc.heading} {sc.narration}", avoid=prev_place)
            bg = scene_library.background(settings, place, portrait, gi)
            if bg is None:
                cached = scene_library.any_cached(settings, portrait)
                bg = cached[i % len(cached)] if cached else None
            if bg is None:
                raise DoodleUnavailable(f"no scene pictures available ({stats['note'] or 'image API off'})")
            prev_place = place
            pose = max_assets.MOOD_POSE.get(mood(sc.narration), "explaining")
            upd = {"bg_path": str(bg), "max_pose_path": str(max_assets.pose_path(settings, pose)), "art_path": None}
            stats["library"] += 1
        scenes[i] = sc.model_copy(update=upd)
    stats["usd"] = round((gi.spent_usd - start) if gi is not None else 0.0, 3)
    return script.model_copy(update={"scenes": scenes}), stats


def estimate(settings) -> dict:
    """Nano Banana cost per long video, per Short, per month (16 long + 90 Shorts) and one-time items."""
    p1, p2 = settings.image_price_1k, settings.image_price_2k
    long_v = settings.doodle_key_scenes_long * p2
    short_v = settings.doodle_key_scenes_short * p1
    month = settings.long_videos_per_month * long_v + settings.shorts_per_month * short_v
    library = len(scene_library.PLACES) * (p2 + p1)
    design = p2 + len(max_assets.POSES) * p1 * 2           # worst case: every pose generated twice
    return {"per_long": round(long_v, 3), "per_short": round(short_v, 3), "per_month": round(month, 2),
            "library_once": round(library, 2), "max_design_once_max": round(design, 2),
            "budget": settings.image_monthly_budget_usd,
            "fits": month + library <= settings.image_monthly_budget_usd}


__all__ = ["prepare", "estimate", "key_indices", "key_scene_prompt", "DoodleUnavailable"]
