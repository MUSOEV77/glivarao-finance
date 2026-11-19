"""AI visuals for LONG videos (Nano Banana 2.1), always with a code-drawn fallback.

1. Character reference: our original narrator "Max" (art/characters.py), rendered as a pose sheet on paper
   (data/character/reference.png). Every AI image showing him includes this sheet, so he stays the same.
   The sheet's fingerprint is stored; the same sheet is reused forever unless you delete it on purpose.
2. Thumbnails: 3 options (2K source -> 1280x720 JPEG). The AI draws Max + ONE simple chart with NO numbers or
   text; the 2-3 bold words are added by our code (exact spelling, no invented numbers). You pick in Telegram.
3. Scene illustrations: 10-20 per long video (1K, square), placed in the editorial "plate" of each scene.
If an image fails (API down, cap reached, paid use off) that one image is drawn by code instead.
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from PIL import Image, ImageDraw

from .characters import draw_max
from .editorial_style import PAL, draw_text, face, paper_bg
from .gemini_image import STYLE, GeminiImage, ImageUnavailable

log = logging.getLogger(__name__)
CHARACTER = ("our channel's original mascot 'Max': a friendly man in his early thirties with round glasses, a brown "
             "hair tuft and a green sweater, drawn in simple ink lines. Keep him EXACTLY like the reference sheet "
             "(same face, glasses, hair, sweater, proportions).")
THUMB_SCENES = [("worried, hand on his head", "a bar chart whose bars rise sharply", "deep navy"),
                ("pointing at the chart, confident", "a line chart that falls steeply", "crimson"),
                ("surprised, both hands up", "a simple pie chart with one large slice", "forest green")]
STOP = set("the a an and or of to in on for is are your you what how why this that it its with from at by be as "
           "now still really most new vs".split())


# ------------------------------------------------------------------------------------------- character
def reference_sheet(settings, store=None) -> bytes:
    """PNG bytes of the locked character reference (created once from the code-drawn original)."""
    path = Path(settings.character_ref_path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        sheet = paper_bg(1536, 1024).copy().convert("RGBA")
        for k, pose in enumerate(("talk", "point", "think")):
            fig = draw_max(pose=pose, scale=0.9)
            sheet.alpha_composite(fig, (24 + k * 505, 1024 - fig.height - 40))
        d = ImageDraw.Draw(sheet)
        draw_text(d, (768, 50), "MAX: CHARACTER REFERENCE", "sans_bold", 34, "ink", anchor="mm", tracking=6)
        sheet.convert("RGB").save(path, "PNG")
    data = path.read_bytes()
    if store is not None:
        sha = hashlib.sha256(data).hexdigest()[:16]
        saved = store.kv_get("character_ref_sha")
        if not saved:
            store.kv_set("character_ref_sha", sha)
        elif saved != sha:
            log.warning("character reference changed (%s -> %s): Max may look different in new images", saved, sha)
    return data


# ------------------------------------------------------------------------------------------- thumbnails
FIN = re.compile(r"\b(minimum|interest|debt|credit|card|score|loans?|student|bnpl|subscriptions?|budget|savings?|"
                 r"taxe?s?|refund|irs|scams?|fraud|401\(?k\)?|roth|ira|aca|premium|subsid\w+|rent|paycheck|fees?|"
                 r"payments?|holiday|deadline|cliff|myths?)\b", re.I)


def bold_words(script, n: int) -> list[str]:
    """Three different 2-3 word headlines for the 3 options (exact text, drawn by our code)."""
    base = (script.thumbnail_text or "").replace("#Shorts", "").strip(" .")
    fins = list(dict.fromkeys(re.sub(r"(?<=[A-Z]{3})(ES|S)$", "", m.group(1).upper())
                              for m in FIN.finditer(f"{script.title} {script.topic}")))
    f1 = fins[0] if fins else "MONEY"
    opts = [" ".join(base.split()[:3]) if base else f"{f1} TRUTH",
            f"THE {f1} TRAP" if "TRAP" not in base.upper() else f"STOP THE {f1}",
            f"YOUR {' '.join(fins[1:3])}" if len(fins) >= 3 else f"{f1} MISTAKES?"]
    out = []
    for o in opts:
        o = " ".join(o.split()[:3]).upper().strip(" ,.")
        if o and o not in out:
            out.append(o)
    for extra in (f"{f1} MISTAKE?", f"FIX YOUR {f1}", f"{f1} 101"):
        if len(out) >= n:
            break
        if extra not in out:
            out.append(extra)
    return out[:n]


def _overlay_words(img: Image.Image, words: str) -> Image.Image:
    """Big bold words on the left, on a highlighter band; brand line; 1280x720."""
    img = img.convert("RGB").resize((1280, 720), Image.LANCZOS).convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    ws = words.split()  # the text must stay in the left 45% (the art is on the right): biggest layout that fits

    def fit(lines):
        size = 170
        while size > 56 and (max(face("sans_xbold", size).getlength(ln) for ln in lines) > 540
                             or len(lines) * size * 1.08 > 600):
            size -= 4
        return size

    layouts = [[words], [" ".join(ws[:2]), " ".join(ws[2:])], [" ".join(ws[:1]), " ".join(ws[1:])], ws]
    layouts = [[ln for ln in lay if ln] for lay in layouts if any(lay)]
    lines = max(layouts, key=fit)
    size = fit(lines)
    f = face("sans_xbold", size)
    y = 360 - (len(lines) * size * 1.05) / 2
    for ln in lines:
        if not ln:
            continue
        w = f.getlength(ln)
        d.rectangle((44, y + size * 0.18, 44 + w + 36, y + size * 1.02), fill=(*PAL["amber"], 235))
        draw_text(d, (62, y + size * 0.6), ln, "sans_xbold", size, "ink", anchor="lm")
        y += size * 1.08
    draw_text(d, (62, 60), "GLIVARAO FINANCE", "sans_bold", 24, "crimson", anchor="lm", tracking=6)
    return img.convert("RGB")


def thumbnail_options(script, out: Path, settings, store=None, client: GeminiImage | None = None,
                      fallback=None) -> tuple[list[Path], list[str]]:
    """3 options -> ([paths], [how each was made]). Never fails: falls back to the code-drawn thumbnail."""
    words = bold_words(script, 3)
    paths, how = [], []
    try:
        gi = client or GeminiImage(settings)
        ref = reference_sheet(settings, store)
    except ImageUnavailable as exc:
        gi, ref, why = None, b"", str(exc)
    for k, (pose, chart, colour) in enumerate(THUMB_SCENES):
        dst = out / f"thumbnail_{k + 1}.jpg"
        if gi is not None:
            prompt = (f"YouTube thumbnail artwork, 16:9. Right half: {CHARACTER} He is {pose}, next to {chart} "
                      f"drawn big and simple. The chart has NO numbers, NO labels, NO text at all. Left 45% of the "
                      f"image: plain flat {colour} background, completely empty (text is added later). Topic: "
                      f"{script.topic}. Bold, high contrast, readable at small size. {STYLE} Absolutely no text, "
                      "letters or numbers anywhere in the image.")
            try:
                img = gi.generate(prompt, settings.image_thumb_size, "16:9", [ref])
                _overlay_words(img, words[k]).save(dst, "JPEG", quality=90, optimize=True)
                paths.append(dst)
                how.append(f"AI ({settings.image_thumb_size}) + \"{words[k]}\"")
                continue
            except ImageUnavailable as exc:
                why = str(exc)
        if fallback is not None:  # the existing code-drawn editorial thumbnail, with this option's words
            fallback(script.model_copy(update={"thumbnail_text": words[k].title()}), dst)
            paths.append(dst)
            how.append(f"code-drawn (image API: {why[:60]})")
    return paths, how


# ------------------------------------------------------------------------------------------- scenes
def scene_prompt(scene, with_character: bool) -> str:
    gist = re.sub(r"\s+", " ", scene.narration.replace("*", ""))[:400]
    who = (f"Include {CHARACTER} as the person in the scene." if with_character else
           "No people; objects and symbols only.")
    return (f"Square editorial illustration for a personal-finance documentary scene titled \"{scene.heading}\". "
            f"What the narrator says: {gist} Show ONE clear visual idea (objects, documents, money, a simple "
            f"situation). {who} No numbers, no words, no text, no charts with values. {STYLE}")


def illustrate_scenes(script, out: Path, settings, store=None, client: GeminiImage | None = None):
    """Adds art_path to up to IMAGE_SCENES_MAX scenes of a long video. Returns (script, stats)."""
    script = script.model_copy(update={"scenes": [s.model_copy(update={"art_path": None}) for s in script.scenes]})
    if script.format != "long":
        return script, {"ai": 0, "code": 0, "note": "Shorts keep code-drawn visuals"}
    try:
        gi = client or GeminiImage(settings)
        ref = reference_sheet(settings, store)
    except ImageUnavailable as exc:
        return script, {"ai": 0, "code": len(script.scenes), "note": str(exc)}
    idx = list(range(len(script.scenes)))
    if len(idx) > settings.image_scenes_max:  # spread evenly through the video
        step = len(idx) / settings.image_scenes_max
        idx = sorted({int(i * step) for i in range(settings.image_scenes_max)})
    scenes, ai, note = list(script.scenes), 0, ""
    for n, i in enumerate(idx):
        sc = scenes[i]
        with_char = sc.beat in ("creator", "case", "question") or n % 3 == 0
        try:
            img = gi.generate(scene_prompt(sc, with_char), settings.image_scene_size, "1:1",
                              [ref] if with_char else [])
        except ImageUnavailable as exc:
            note = str(exc)
            if "budget" in note:
                break  # cap reached: the rest stays code-drawn
            continue
        dst = out / "scene_art" / f"scene_{i:02d}.png"
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, "PNG")
        scenes[i] = sc.model_copy(update={"art_path": str(dst)})
        ai += 1
    return (script.model_copy(update={"scenes": scenes}),
            {"ai": ai, "code": len(script.scenes) - ai, "usd": round(gi.spent_usd, 3), "note": note})


def load_art(path: str, size: int) -> Image.Image | None:
    """Square-cropped RGBA for the renderer's plate; None if missing/unreadable (code-drawn fallback)."""
    try:
        im = Image.open(path).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    s = min(im.size)
    im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2))
    return im.resize((size, size), Image.LANCZOS).convert("RGBA")


__all__ = ["reference_sheet", "thumbnail_options", "illustrate_scenes", "load_art", "bold_words", "CHARACTER"]
