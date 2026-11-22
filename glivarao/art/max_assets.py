"""Max, designed ONCE with Nano Banana and reused forever (identical in every video, no cost after).

    python -m glivarao style-samples --send      # designs Max first if he doesn't exist yet (hard cap $2)

1. A master design (2K): a charming, expressive hand-drawn cartoon man with round glasses, a deep green
   (#1f8a4c) sweater and a small gold (#e0a526) coin pin, on a flat magenta background.
2. 8 poses (1K each), every one generated with the master as the reference image, with real body language and
   facial expressions: explaining, pointing, worried, shocked, thinking, happy, sad, cheering.
3. The magenta (or plain) background is keyed out -> transparent PNG cutouts in data/character/max/.
   Every cutout passes automatic checks (background removed, figure big enough, no leftover magenta); a pose that
   fails is generated once more.
4. A style sheet (all 8 cutouts on paper) is composed by code: it is the reference sent with every scene request.

The files are fingerprinted; they are never regenerated unless you ask (--redesign-max).
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

log = logging.getLogger(__name__)

POSES = {
    "explaining": "talking to the viewer with one open hand raised, friendly smile, mid-sentence",
    "pointing": "pointing enthusiastically to his left (the viewer's right) at something off to the side, eyebrows "
                "raised, excited",
    "worried": "worried: one hand on his forehead, teeth clenched in an awkward grimace, a drop of sweat, knees "
               "slightly bent",
    "shocked": "shocked: jaw dropped, eyes wide behind his glasses, both hands on his cheeks, leaning back",
    "thinking": "thinking: one hand on his chin, looking up to the side, one eyebrow raised, the other arm folded",
    "happy": "happy: big warm grin, giving a thumbs up with one hand, relaxed confident stance",
    "sad": "sad and broke: shoulders slumped, frowning, pulling out both empty trouser pockets",
    "cheering": "celebrating: both arms up in the air, eyes closed with a huge open-mouth smile, one knee lifted",
}
MOOD_POSE = {"happy": "happy", "worried": "worried", "shocked": "shocked", "thinking": "thinking",
             "confident": "pointing", "cheering": "cheering", "sad": "sad", "explaining": "explaining"}
CHARACTER = ("Max, the original mascot of a personal-finance YouTube channel: a friendly American man in his early "
             "thirties, slim, with short messy brown hair and a small tuft on top, round black glasses, a warm "
             "expressive face, a deep green crew-neck sweater (#1f8a4c) with a small round gold coin pin (#e0a526) "
             "on the chest, beige chinos and brown sneakers")
LOOK = ("Charming, expressive hand-drawn cartoon style like a premium animated explainer: bold slightly wobbly black "
        "ink outlines, flat warm colors, simple cel shading, big readable expressions and clear body language. "
        "Original character, not based on any existing cartoon. No text, no letters, no logos, no watermark.")
KEY_BG = ("Full body, whole figure visible with a margin on every side, centered. Background: one flat solid pure "
          "magenta color (#FF00FF) everywhere, no floor, no shadow, no gradient, no other objects.")


def max_dir(settings) -> Path:
    return Path(getattr(settings, "doodle_ref_path", "data/character/doodle_reference.png")).parent / "max"


def pose_path(settings, pose: str) -> Path:
    return max_dir(settings) / f"{pose}.png"


def sheet_path(settings) -> Path:
    return max_dir(settings) / "max_style_sheet.png"


def ready(settings) -> bool:
    return all(pose_path(settings, p).exists() for p in POSES) and sheet_path(settings).exists()


def load_pose(settings, pose: str) -> Image.Image | None:
    p = pose_path(settings, MOOD_POSE.get(pose, pose))
    if not p.exists():
        return None
    return Image.open(p).convert("RGBA")


# ------------------------------------------------------------------------------------------- keying
def key_out(img: Image.Image, tolerance: float = 70.0) -> Image.Image:
    """Remove the flat background (the colour of the border), keeping enclosed areas inside the figure.
    Soft 1-2 px edge, magenta spill removed, cropped to the figure with a small margin."""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w, _ = rgb.shape
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    dist = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
    cand = dist < tolerance
    # background = candidate pixels connected to the border (flood fill from the border; enclosed areas such as
    # eye whites or the gap under an arm stay part of the figure unless they touch the edge)
    from PIL import ImageDraw

    mask = Image.fromarray((cand * 255).astype(np.uint8)).copy()  # own buffer: floodfill must be able to write
    step = 8
    for x in list(range(0, w, step)) + [w - 1]:
        for y in (0, h - 1):
            if mask.getpixel((x, y)) == 255:
                ImageDraw.floodfill(mask, (x, y), 128)
    for y in list(range(0, h, step)) + [h - 1]:
        for x in (0, w - 1):
            if mask.getpixel((x, y)) == 255:
                ImageDraw.floodfill(mask, (x, y), 128)
    cur = mask.point(lambda v: 255 if v == 128 else 0)
    bgmask = np.asarray(cur) > 0
    alpha = np.where(bgmask, 0.0, 1.0)
    # soft edge: pixels near the background get partial alpha by colour distance
    edge = np.asarray(Image.fromarray((bgmask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
    band = edge & ~bgmask
    alpha[band] = np.clip((dist[band] - tolerance * 0.6) / (tolerance * 1.2), 0, 1)
    out = rgb.copy()
    if bg[0] > 150 and bg[2] > 150 and bg[1] < 110:         # magenta key: remove pink spill on the edges
        spill = band | (alpha < 1)
        g = out[..., 1]
        out[..., 0] = np.where(spill, np.minimum(out[..., 0], g + 40), out[..., 0])
        out[..., 2] = np.where(spill, np.minimum(out[..., 2], g + 40), out[..., 2])
    rgba = np.dstack([out, alpha * 255]).clip(0, 255).astype(np.uint8)
    res = Image.fromarray(rgba, "RGBA")
    bbox = res.getchannel("A").point(lambda a: 255 if a > 24 else 0).getbbox()
    if bbox:
        m = 12
        res = res.crop((max(0, bbox[0] - m), max(0, bbox[1] - m), min(w, bbox[2] + m), min(h, bbox[3] + m)))
    return res


def check_cutout(cut: Image.Image, source_size: tuple[int, int]) -> list[str]:
    """Problems with a cutout (empty = good)."""
    a = np.asarray(cut.getchannel("A"), dtype=np.float32) / 255
    rgb = np.asarray(cut.convert("RGB"), dtype=np.int16)
    probs = []
    cover = a.mean()
    if cover < 0.18 or cover > 0.92:
        probs.append(f"figure covers {cover:.0%} of its box (background not removed cleanly)")
    if cut.height < source_size[1] * 0.55:
        probs.append(f"figure too small ({cut.height}px of {source_size[1]}px)")
    magenta = (rgb[..., 0] > 200) & (rgb[..., 2] > 200) & (rgb[..., 1] < 90) & (a > 0.5)
    if magenta.mean() > 0.004:
        probs.append(f"{magenta.mean():.1%} magenta left on the figure")
    return probs


# ------------------------------------------------------------------------------------------- sheet
def compose_sheet(cutouts: dict[str, Image.Image], dst: Path | None = None) -> Image.Image:
    """All poses on paper with their names (code-drawn): the reference for every scene request."""
    from .doodle import Pen, paper, INK, GREEN, brand_mark, underline

    W, H = 3072, 1728
    img = paper(W, H, seed=21).copy().convert("RGBA")
    p = Pen(img, seed=2, width=8)
    p.text((W / 2, 95), "MAX  -  GLIVARAO MASCOT  -  8 POSES (STYLE REFERENCE)", 84, INK, bold=2)
    underline(p, W * 0.18, W * 0.82, 155, GREEN, 10)
    names = list(POSES)
    cols, cell_w, cell_h = 4, W / 4, (H - 230) / 2
    for k, name in enumerate(names):
        cut = cutouts.get(name)
        cx, top = cell_w * (k % cols) + cell_w / 2, 210 + cell_h * (k // cols)
        if cut is not None:
            s = min((cell_w * 0.86) / cut.width, (cell_h - 110) / cut.height)
            c = cut.resize((max(1, int(cut.width * s)), max(1, int(cut.height * s))), Image.LANCZOS)
            img.alpha_composite(c, (int(cx - c.width / 2), int(top + cell_h - 95 - c.height)))
        p.text((cx, top + cell_h - 45), name, 60, INK)
    brand_mark(img, "br", scale=2.0)
    out = img.convert("RGB").resize((1536, 864), Image.LANCZOS)
    if dst is not None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        out.save(dst, "PNG")
    return out


# ------------------------------------------------------------------------------------------- design
class DesignBudget(RuntimeError):
    pass


def design(settings, gi, cap_usd: float = 2.0, redesign: bool = False, log_fn=print) -> dict:
    """Generate the master + 8 poses (Nano Banana), key them out, check them, write the sheet.
    gi: a GeminiImage. Stops before any call that would take this run over cap_usd."""
    d = max_dir(settings)
    d.mkdir(parents=True, exist_ok=True)
    if ready(settings) and not redesign:
        return {"made": False, "usd": 0.0, "dir": str(d)}
    start = gi.spent_usd

    def gen(prompt, size, aspect, refs):
        if gi.spent_usd - start + gi.price(size) > cap_usd + 1e-9:
            raise DesignBudget(f"would exceed the ${cap_usd:.2f} design cap")
        return gi.generate(prompt, size, aspect, refs)

    master = gen(f"Character design: {CHARACTER}. Standing in a relaxed, friendly pose, smiling, front three-"
                 f"quarter view. {LOOK} {KEY_BG}", "2K", "3:4", [])
    master_path = d / "master.png"
    master.save(master_path, "PNG")
    ref = master_path.read_bytes()
    cutouts, report = {}, {}
    for name, pose in POSES.items():
        cut, probs = None, ["not generated"]
        for attempt in range(2):
            extra = " Make the expression and body language very clear and exaggerated." if attempt else ""
            img = gen(f"The SAME character as in the reference image ({CHARACTER}), exactly the same face, glasses, "
                      f"hair, sweater, coin pin, trousers, shoes and proportions. Pose: {pose}.{extra} {LOOK} {KEY_BG}",
                      "1K", "3:4", [ref])
            cut = key_out(img)
            probs = check_cutout(cut, img.size)
            if not probs:
                break
            log_fn(f"  pose {name}: {'; '.join(probs)}; trying once more" if attempt == 0 else
                   f"  pose {name}: still {'; '.join(probs)} (kept, flagged in the report)")
        cut.save(pose_path(settings, name), "PNG")
        cutouts[name], report[name] = cut, probs
    compose_sheet(cutouts, sheet_path(settings))
    meta = {"poses": list(POSES), "usd": round(gi.spent_usd - start, 4), "problems": report,
            "sha": {n: hashlib.sha256(pose_path(settings, n).read_bytes()).hexdigest()[:16] for n in POSES}}
    (d / "design.json").write_text(json.dumps(meta, indent=2))
    return {"made": True, "usd": meta["usd"], "dir": str(d), "problems": report}


__all__ = ["POSES", "MOOD_POSE", "CHARACTER", "LOOK", "design", "key_out", "check_cutout", "compose_sheet", "ready",
           "load_pose", "pose_path", "sheet_path", "max_dir", "DesignBudget"]
