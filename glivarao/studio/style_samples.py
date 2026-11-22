"""Doodle style samples for your approval (the old style stays until you approve).

    python -m glivarao style-samples            # make them (output/style_samples/doodle-v1/), print the paths
    python -m glivarao style-samples --send     # ...and send them to Telegram with Approve / Request changes

What is made (all code-drawn: no Nano Banana call, nothing is spent):
1. Max style reference sheet (the same file is sent with every Nano Banana request in this style).
2. 3 video frames + 3 thumbnails for 3 launch-list topics.
3. A 14-second silent motion sample: two shots with the slow camera pan/zoom and the hard cut between them.

Tapping Approve sets GLIVARAO_THEME=doodle in .env, so videos made AFTER you resume production use the new style.
Approving does not resume production.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..art import doodle as D
from ..models import ChartSpec, Scene, Script
from ..render import doodle as R

VERSION = D.VERSION

# (launch-list topic, thumbnail statement, Max's emotion, the scene shown in the sample frame, shot kind)
SAMPLES = [
    ("How to get out of credit card debt (a plan that works)", "Debt Wins", "worried",
     Scene(heading="The average card rate", narration="As of November 2026, the average rate on cards charged "
           "interest was 22.36% a year.", illustration="credit_card", key_points=[]), "number", "22.36%"),
    ("Why houses got so expensive", "Homes Got Expensive", "shocked",
     Scene(heading="Why houses got so expensive", narration="Home prices climbed far faster than paychecks.",
           illustration="house", chart=ChartSpec(kind="line_series", title="Home prices vs. paychecks (illustration)",
                                                 source="Illustrative example")), "chart", ""),
    ("Is the US national debt a problem? What it means for your money", "$40 Trillion Owed", "thinking",
     Scene(heading="Is the national debt a problem?", narration="What does the national debt mean for your money?",
           illustration="bank", key_points=[]), "title", ""),
]


def _script(scene: Scene, topic: str) -> Script:
    end = Scene(heading="What to do", narration="This video is for education only and isn't financial advice.")
    return Script(title=topic, description="", tags=[], thumbnail_text="", hook="", scenes=[scene, end],
                  format="long", topic=topic)


def make(out_dir: Path) -> dict:
    """Render everything into out_dir. Returns {"reference": path, "frames": [...], "thumbs": [...], "motion": path}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    res = {"reference": out_dir / "max_reference_sheet.png", "frames": [], "thumbs": [], "topics": []}
    D.reference_sheet(res["reference"])
    for k, (topic, words, emo, scene, kind, num) in enumerate(SAMPLES, 1):
        shot = R.Shot(0.0, 8.0, kind, scene.narration, {"num": num})
        canvas = R.draw_shot(scene, shot, False, 0, seed=k)
        frame = R.camera(canvas, (1920, 1080), 0.5, "zoom_in")
        D.brand_mark(frame, "tr")
        fp = out_dir / f"frame_{k}.png"
        frame.save(fp, "PNG")
        tp = out_dir / f"thumbnail_{k}.jpg"
        D.thumbnail(words, emo, tp, seed=k)
        res["frames"].append(fp)
        res["thumbs"].append(tp)
        res["topics"].append(topic)
    res["motion"] = motion_sample(out_dir / "motion_sample.mp4")
    (out_dir / "samples.json").write_text(json.dumps({k: [str(x) for x in v] if isinstance(v, list) else str(v)
                                                      for k, v in res.items()}, indent=2))
    return res


def motion_sample(dst: Path, seconds: float = 14.0) -> Path:
    """Two shots (title, then the big number) with the camera moves and the hard cut, silent, 1920x1080 24 fps."""
    scene = Scene(heading="How credit card interest piles up", illustration="credit_card",
                  narration="Here's how card interest piles up. As of November 2026, the average rate on cards charged "
                            "interest was 22.36% a year.")
    script = _script(scene, "How to get out of credit card debt")
    sentences = [(0.0, 7.0, "Here's how card interest piles up."),
                 (7.0, seconds, "As of November 2026, the average rate on cards charged interest was 22.36% a year.")]
    frames = R.DoodleFrames(script, 0, sentences, int(seconds * R.FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r",
           str(R.FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(dst)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(seconds * R.FPS)):
        proc.stdin.write(np.asarray(frames.frame(f, False), dtype=np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("motion sample encode failed")
    return dst


def send(settings, res: dict, client=None) -> None:
    from ..publish.telegram import _client

    c = _client(settings, client)
    chat = settings.telegram_approver_chat_id
    c.call("sendMessage", chat_id=chat, text=(
        "🎨 New GLIVARAO look for your approval (our own hand-drawn explainer style): off-white paper, black marker "
        "doodles, Max in a green sweater with a gold pin, brand green #1f8a4c + gold, a small GLIVARAO mark, slow "
        "camera pan/zoom with a cut every 6-10 seconds. Thumbnails: a 2-3 word statement ending with a period, one "
        "simple chart (grey history + green/gold spike), Max with an emotion.\n\nAll drawn by code: Max looks the same "
        "in every video, and nothing was spent. The current style stays until you approve."))
    with open(res["reference"], "rb") as fh:
        c.call("sendPhoto", files={"photo": fh}, chat_id=chat,
               caption="1/4 Max style reference sheet (also sent with every Nano Banana request in this style)")
    for label, key in (("Video frames", "frames"), ("Thumbnails", "thumbs")):
        handles = [open(p, "rb") for p in res[key]]
        try:
            media = [{"type": "photo", "media": f"attach://f{k}",
                      **({"caption": f"{'2/4' if key == 'frames' else '3/4'} {label}: " +
                                     " · ".join(f'{n + 1}. {t}' for n, t in enumerate(res['topics']))} if k == 0 else {})}
                     for k in range(len(handles))]
            c.call("sendMediaGroup", files={f"f{k}": (Path(p).name, h) for k, (p, h) in
                                            enumerate(zip(res[key], handles))}, chat_id=chat, media=media)
        finally:
            for h in handles:
                h.close()
    with open(res["motion"], "rb") as fh:
        c.call("sendVideo", files={"video": fh}, chat_id=chat, supports_streaming=True,
               caption="4/4 Motion sample (14 s, silent): slow camera move on each drawing, hard cut to the next shot")
    c.call("sendMessage", chat_id=chat, text=(
        "Approve this style? Approving switches NEW videos to the doodle style once you resume production. "
        "Production stays paused either way."),
        reply_markup={"inline_keyboard": [[{"text": "✅ Approve style", "callback_data": f"style:{VERSION}"},
                                           {"text": "✏️ Request changes", "callback_data": "styleedit:x"}]]})


def approve(settings, store, env_path: Path | None = None) -> None:
    """Switch new videos to the doodle theme (in .env) and lock the Max reference sheet."""
    from .voice_audition import write_env

    write_env({"GLIVARAO_THEME": "doodle"}, env_path)
    D.reference_sheet(Path(settings.doodle_ref_path))
    store.kv_set("style_approved", json.dumps({"version": VERSION,
                                               "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))


def approved(store) -> bool:
    return json.loads(store.kv_get("style_approved", "{}")).get("version") == VERSION


__all__ = ["make", "send", "approve", "approved", "motion_sample", "SAMPLES", "VERSION"]
