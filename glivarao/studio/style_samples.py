"""Doodle style v2 samples for your approval (the old style stays until you approve).

    python -m glivarao style-samples --send        # one command on the server; prints the Nano Banana cost

1. Designs Max ONCE with Nano Banana (master + 8 poses -> transparent cutouts + style sheet), unless he exists.
2. Makes 3 full key scenes for 3 launch-list topics (Max acting in each) and composes the frames with our
   code-drawn cards (number, chart, title) inside the safe area.
3. Makes 3 thumbnails (statement ending with a period + one simple chart + a Max cutout).
4. Checks every frame (text inside the safe area, at most 15% empty) and prints the money spent.
5. Sends the Max sheet, the 3 frames and the 3 thumbnails to Telegram with Approve / Request changes.
Hard cap for this command: $2 of Nano Banana (checked before every call). Images are cached, so running it again
costs nothing for what already exists. Approving sets GLIVARAO_THEME=doodle; production stays paused.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..art import doodle as D
from ..art import doodle_prep, max_assets
from ..models import ChartSpec, Scene
from ..render import doodle as R

VERSION = "doodle-v2"
CAP_USD = 2.0
MAX_EMPTY = 0.15

# (launch-list topic, thumbnail statement, Max pose, scene, shot kind, number)
SAMPLES = [
    ("How to get out of credit card debt (a plan that works)", "Debt Wins", "worried",
     Scene(heading="The average card rate", narration="Late at night at the kitchen table, the card bills keep "
           "coming. As of November 2026, the average rate on cards charged interest was 22.36% a year."),
     "number", "22.36%"),
    ("Why houses got so expensive", "Homes Got Expensive", "shocked",
     Scene(heading="Why houses got so expensive", narration="On a suburban street full of for-sale signs, home "
           "prices climbed far faster than paychecks.",
           chart=ChartSpec(kind="line_series", title="Home prices vs. paychecks (illustration)",
                           source="Illustrative example")), "chart", ""),
    ("Is the US national debt a problem? What it means for your money", "$40 Trillion Owed", "thinking",
     Scene(heading="Is the national debt a problem?", narration="In front of a big government building, Max "
           "wonders what the national debt means for his own loans and savings."), "title", ""),
]


class Spend:
    """Tracks this command's Nano Banana spend against the $2 cap."""

    def __init__(self, gi, cap: float = CAP_USD):
        self.gi, self.cap, self.start = gi, cap, gi.spent_usd

    @property
    def spent(self) -> float:
        return self.gi.spent_usd - self.start

    @property
    def spent_usd(self) -> float:
        return self.gi.spent_usd

    def price(self, size: str) -> float:
        return self.gi.price(size)

    def generate(self, prompt, size, aspect, refs):
        if self.spent + self.gi.price(size) > self.cap + 1e-9:
            raise max_assets.DesignBudget(f"would exceed the ${self.cap:.2f} cap for this command")
        return self.gi.generate(prompt, size, aspect, refs)


def compose_frame(bg_path: Path, scene: Scene, kind: str, num: str, seed: int = 1):
    """Picture (camera mid-move) + code-drawn card + brand mark. Returns (frame, overlay)."""
    from PIL import Image

    size = (1920, 1080)
    frame = R.camera(Image.open(bg_path).convert("RGB"), size, 0.5, "zoom_in")
    ov = R.build_overlay(scene, R.Shot(0.0, 8.0, kind, scene.narration, {"num": num}), size, False, seed)
    frame.paste(ov.img, (0, 0), ov.img)
    D.brand_mark(frame, "tr")
    return frame, ov


def frame_checks(frame, ov) -> list[str]:
    probs = []
    sx0, sy0, sx1, sy1 = R.safe_box(frame.size, False)
    for b in ov.text_boxes:
        if b[0] < sx0 or b[1] < sy0 or b[2] > sx1 or b[3] > sy1:
            probs.append(f"text outside the safe area at {b}")
    e = R.empty_ratio(frame)
    if e > MAX_EMPTY:
        probs.append(f"{e:.0%} of the frame is empty (max {MAX_EMPTY:.0%})")
    return probs


def make(settings, gi, out_dir: Path, redesign: bool = False, log=print) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    sp = Spend(gi)
    log(f"Max: {'designing (master + 8 poses)' if redesign or not max_assets.ready(settings) else 'already designed'}")
    d = max_assets.design(settings, sp, cap_usd=CAP_USD, redesign=redesign, log_fn=log)
    sheet = max_assets.sheet_path(settings)
    res = {"sheet": sheet, "frames": [], "thumbs": [], "topics": [], "checks": {}, "max": d}
    for k, (topic, words, pose, scene, kind, num) in enumerate(SAMPLES, 1):
        log(f"sample {k}: {topic}")
        img = sp.generate(doodle_prep.key_scene_prompt(scene, False), "2K", "16:9", [sheet.read_bytes()])
        bgp = out_dir / f"scene_{k}.png"
        img.save(bgp, "PNG")
        frame, ov = compose_frame(bgp, scene, kind, num, seed=k)
        fp = out_dir / f"frame_{k}.png"
        frame.save(fp, "PNG")
        res["checks"][f"frame_{k}"] = frame_checks(frame, ov) + [f"empty {R.empty_ratio(frame):.0%}"]
        tp = out_dir / f"thumbnail_{k}.jpg"
        D.thumbnail(words, pose, tp, seed=k, max_img=max_assets.load_pose(settings, pose))
        res["frames"].append(fp)
        res["thumbs"].append(tp)
        res["topics"].append(topic)
    res["usd"] = round(sp.spent, 4)
    (out_dir / "samples.json").write_text(json.dumps(
        {k: ([str(x) for x in v] if isinstance(v, list) else (str(v) if isinstance(v, Path) else v))
         for k, v in res.items()}, indent=2, default=str))
    return res


def summary(settings, res: dict) -> str:
    est = doodle_prep.estimate(settings)
    probs = [f"{k}: {'; '.join(v)}" for k, v in res["checks"].items() if any("outside" in x or "empty (" in x
                                                                          for x in v)]
    maxp = {p: v for p, v in (res["max"].get("problems") or {}).items() if v}
    return (f"Nano Banana spent by this command: ${res['usd']:.2f} (cap ${CAP_USD:.2f}).\n"
            f"Checks: {'all frames pass (text inside the safe area, at most 15% empty)' if not probs else ' | '.join(probs)}"
            + (f"\nMax poses flagged: {maxp}" if maxp else "") + "\n\n"
            f"Estimated Nano Banana cost in this style: ${est['per_long']:.2f} per long video "
            f"({settings.doodle_key_scenes_long} key scenes at 2K), ${est['per_short']:.3f} per Short "
            f"({settings.doodle_key_scenes_short} key scene at 1K) = ${est['per_month']:.2f} a month for "
            f"{settings.long_videos_per_month} long + {settings.shorts_per_month} Shorts; one-time scene library "
            f"${est['library_once']:.2f}. Image budget ${est['budget']:.0f}/month: "
            f"{'fits' if est['fits'] else 'NOT enough, raise IMAGE_MONTHLY_BUDGET_USD'}.")


def send(settings, res: dict, client=None) -> None:
    from ..publish.telegram import _client

    c = _client(settings, client)
    chat = settings.telegram_approver_chat_id
    c.call("sendMessage", chat_id=chat, text=(
        "🎨 New GLIVARAO look, v2 (our own hand-drawn explainer style): Max designed once with Nano Banana (8 "
        "poses, reused in every video, so he never changes and costs nothing after), full hand-drawn scenes with "
        "Max acting in them, our cards for numbers and charts. The current style stays until you approve.\n\n"
        + summary(settings, res)))
    with open(res["sheet"], "rb") as fh:
        c.call("sendPhoto", files={"photo": fh}, chat_id=chat, caption="1/3 Max: the 8 poses (style sheet)")
    for label, key, n in (("Video frames", "frames", "2/3"), ("Thumbnails", "thumbs", "3/3")):
        handles = [open(p, "rb") for p in res[key]]
        try:
            media = [{"type": "photo", "media": f"attach://f{k}",
                      **({"caption": f"{n} {label}: " + " · ".join(f"{i + 1}. {t}" for i, t in
                                                                     enumerate(res["topics"]))} if k == 0 else {})}
                     for k in range(len(handles))]
            c.call("sendMediaGroup", files={f"f{k}": (Path(p).name, h) for k, (p, h) in
                                            enumerate(zip(res[key], handles))}, chat_id=chat, media=media)
        finally:
            for h in handles:
                h.close()
    c.call("sendMessage", chat_id=chat, text=(
        "Approve this style? Approving switches NEW videos to it once you resume production. Production stays "
        "paused either way."),
        reply_markup={"inline_keyboard": [[{"text": "✅ Approve style", "callback_data": f"style:{VERSION}"},
                                           {"text": "✏️ Request changes", "callback_data": "styleedit:x"}]]})


def approve(settings, store, env_path: Path | None = None) -> None:
    """Switch new videos to the doodle theme (in .env)."""
    from .voice_audition import write_env

    write_env({"GLIVARAO_THEME": "doodle"}, env_path)
    store.kv_set("style_approved", json.dumps({"version": VERSION,
                                               "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))


def approved(store) -> bool:
    return json.loads(store.kv_get("style_approved", "{}")).get("version") == VERSION


__all__ = ["make", "send", "summary", "approve", "approved", "compose_frame", "frame_checks", "Spend", "SAMPLES",
           "VERSION", "CAP_USD"]
