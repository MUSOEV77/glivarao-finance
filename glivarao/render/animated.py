"""v2 animated renderer: Kokoro narration + rigged characters + sets + camera + transitions.

Landscape 1920x1080 at 24 fps. Scenes render in parallel worker processes (one ffmpeg segment
each), then are joined, captioned and loudness-normalized (two-pass, -14 LUFS) in a final pass.
The v1 renderer (render/video.py) is untouched and still used unless RENDERER=v2.
"""
from __future__ import annotations

import json
import logging
import multiprocessing as mp
import os
import subprocess
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFilter

from ..anim import rig
from ..anim.actor import Actor, envelope
from ..anim.director import ScenePlan, plan_scene
from ..anim.easing import Noise, clamp, ease_in_out, ease_out, progress
from ..anim.props import coin_shower, flying_bills, icon, sticky_note
from ..anim.sets import LAYOUTS, STAGE_H, STAGE_W, background
from ..art.charts import draw_chart
from ..art.style import Ink, font
from ..config import Settings
from ..models import Script
from ..tts.kokoro import KOKORO_SR, KokoroEngine, Narration
from .subtitles import Cue, chunk_text, write_ass, write_srt
from .video import _ffmpeg_filter_path

log = logging.getLogger(__name__)
W, H, FPS = 1920, 1080, 24
TRANSITION_FRAMES = 12


@dataclass
class AnimatedResult:
    video: Path
    srt: Path
    duration: float
    render_seconds: float
    unknown_words: list[str]
    voice: str


# ------------------------------------------------------------------ frame composition
@lru_cache(maxsize=4)
def _shadow(w: int) -> Image.Image:
    img = Image.new("RGBA", (w + 40, 80), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((20, 20, w + 20, 60), fill=(60, 40, 30, 70))
    return img.filter(ImageFilter.GaussianBlur(8))


def _title_card(frame: Image.Image, text: str, t: float):
    """Hand-lettered scene title that slides in, holds, and slides out (screen space)."""
    if t > 3.6:
        return
    p_in, p_out = ease_out(progress(t, 0.25, 0.5)), ease_in_out(progress(t, 3.0, 0.5))
    if p_in <= 0:
        return
    f = font(64)
    tw = int(f.getlength(text)) + 80
    x = int(-tw + (tw + 60) * p_in - (tw + 80) * p_out)
    ink = Ink(frame, seed=int(t * 8) % 3 + 40, wobble=1.4, width=5)
    ink.poly([(x, 52), (x + tw, 46), (x + tw + 14, 132), (x - 6, 138)], fill=(255, 253, 247))
    ink.text((x + 40, 92), text, 64, anchor="lm")
    ink.line([(x + 40, 124), (x + 40 + (tw - 80) * ease_out(progress(t, 0.6, 0.6)), 121)], color="green", width=7)


def _chart(spec, w: int, h: int, pr: float, boil: int) -> Image.Image:
    """Charts are drawn at 80% size and scaled up so labels stay readable on a phone."""
    k = 1.25
    return draw_chart(spec, int(w / k), int(h / k), pr, boil).resize((w, h), Image.LANCZOS)


class SceneFrames:
    def __init__(self, script: Script, idx: int, plan: ScenePlan, env: np.ndarray):
        self.scene = script.scenes[idx]
        self.plan, self.idx = plan, idx
        self.L = LAYOUTS[plan.set]
        self.bg = background(plan.set)
        self.actors = [Actor(a, env if a.speaking else None, FPS) for a in plan.actors]
        self.noise = Noise(idx * 31 + 3, 0.4)
        self._chart_cache: dict[int, Image.Image] = {}
        bx0, by0, bx1, by1 = self.L.board
        self.board = (bx0, by0, bx1 - bx0, by1 - by0)

    def _content(self, stage: Image.Image, t: float, boil: int):
        s, plan = self.scene, self.plan
        bx, by, bw, bh = self.board
        if s.chart.kind != "none" and plan.chart_start is not None and t >= plan.chart_start - 0.3:
            appear = ease_out(progress(t, plan.chart_start - 0.3, 0.4))
            pr = progress(t, plan.chart_start, plan.chart_dur)
            if pr >= 1:
                if boil not in self._chart_cache:
                    self._chart_cache[boil] = _chart(s.chart, bw, bh, 1.0, boil)
                chart = self._chart_cache[boil]
            else:
                chart = _chart(s.chart, bw, bh, pr, boil)
            if appear < 1:
                chart = chart.copy()
                chart.putalpha(chart.getchannel("A").point(lambda a: int(a * appear)))
            stage.paste(chart, (bx, int(by + (1 - appear) * 40)), chart)
        elif plan.icon_start is not None:
            if plan.notes:
                icon(stage, s.illustration, bx + 230, by + bh / 2, 420, t, plan.icon_start, boil)
            else:
                icon(stage, s.illustration, bx + bw / 2, by + bh / 2, 540, t, plan.icon_start, boil)
        for k, (text, t0) in enumerate(plan.notes):
            if s.chart.kind == "none":
                sticky_note(stage, text, bx + 470, by + 40 + k * 220, t, t0, k, boil)
        main = plan.actors[0]
        for kind, t0 in plan.fx:
            if kind == "coins":
                coin_shower(stage, main.x + 170, main.x + 420, self.L.floor_y - 18, t, t0, boil, seed=self.idx)
            elif kind == "bills":
                flying_bills(stage, main.x + 180, self.L.floor_y - 560, bx + bw / 2, by + bh / 2, t, t0, boil,
                             seed=self.idx)

    def frame(self, f: int) -> Image.Image:
        t = f / FPS
        boil = (f // 3) % 3  # ~8 fps line boil: alive, not jittery
        stage = self.bg.copy()
        self._content(stage, t, boil)
        for actor in self.actors:
            pose, x, ey = actor.state(t)
            sc = actor.p.scale
            img = rig.draw(actor.p.name, pose, sc, boil)
            rx, ry = rig.ROOT[actor.p.name]
            feet = (995 if actor.p.name == "max" else 712) * sc
            sh = _shadow(int(220 * sc))
            stage.paste(sh, (int(x - sh.width / 2), int(self.L.floor_y - 40)), sh)
            stage.paste(img, (int(x - rx * sc), int(self.L.floor_y - feet + ey)), img)
        cx, cy, z = self.plan.cam(t, self.noise)
        z = max(z, W / STAGE_W + 1e-3)
        vw, vh = W / z, H / z
        cx = clamp(cx, vw / 2, STAGE_W - vw / 2)
        cy = clamp(cy, vh / 2, STAGE_H - vh / 2)
        frame = stage.transform((W, H), Image.AFFINE, (1 / z, 0, cx - vw / 2, 0, 1 / z, cy - vh / 2),
                                resample=Image.BILINEAR)
        _title_card(frame, self.scene.heading, t)
        return frame


def _transition(kind: str, prev: Image.Image, cur: Image.Image, f: int) -> Image.Image:
    e = ease_in_out((f + 1) / TRANSITION_FRAMES)
    if kind == "fade":
        return Image.blend(prev, cur, e)
    if kind == "push":
        out = Image.new("RGB", (W, H))
        off = int(e * W)
        out.paste(prev, (-off, 0))
        out.paste(cur, (W - off, 0))
        ImageDraw.Draw(out).line([(W - off, 0), (W - off, H)], fill=(38, 34, 46), width=8)
        return out
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    if kind == "iris":
        r = e * 1.15 * (W ** 2 + H ** 2) ** 0.5 / 2
        cx, cy = W * 0.35, H * 0.45
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    else:  # wipe: a hand-torn paper edge sweeps across
        x = e * (W + 200) - 100
        pts = [(0, 0), (x, 0)] + [(x + 40 * np.sin(k * 1.7), k * H / 12) for k in range(13)] + [(0, H)]
        d.polygon(pts, fill=255)
    out = Image.composite(cur, prev, mask)
    edge = mask.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(7))
    out.paste((38, 34, 46), (0, 0), edge)
    return out


# ------------------------------------------------------------------ parallel segment rendering
_JOB: dict = {}  # per-process job data, set by _init_worker in each spawned worker


def _init_worker(job: dict) -> None:
    _JOB.update(job)


def _render_segment(i: int) -> str:
    script, plans, envs, starts, workdir = (_JOB[k] for k in ("script", "plans", "envs", "starts", "workdir"))
    n_frames = starts[i + 1] - starts[i]
    seg = workdir / f"seg_{i:03d}.mp4"
    sf_ = SceneFrames(script, i, plans[i], envs[i])
    prev_last = None
    if i > 0 and plans[i].transition != "cut":
        prev_last = SceneFrames(script, i - 1, plans[i - 1], envs[i - 1]).frame(starts[i] - starts[i - 1] - 1)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-threads", "2",
           "-pix_fmt", "yuv420p", str(seg)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(n_frames):
        img = sf_.frame(f)
        if prev_last is not None and f < TRANSITION_FRAMES:
            img = _transition(plans[i].transition, prev_last, img, f)
        proc.stdin.write(np.asarray(img, dtype=np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"segment {i} encode failed")
    return str(seg)


def _loudnorm_args(wav: Path) -> str:
    """Two-pass EBU R128 normalization to -14 LUFS (YouTube reference level)."""
    base = "loudnorm=I=-14:TP=-1.5:LRA=11"
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(wav), "-af", base + ":print_format=json",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    m = json.loads(out[out.rindex("{"):out.rindex("}") + 1])
    return (f"{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
            f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")


def render_animated(script: Script, workdir: Path, settings: Settings, voice: str = "am_michael",
                    workers: int | None = None) -> AnimatedResult:
    if script.format != "long":
        raise NotImplementedError("v2 renderer currently supports landscape (long) videos; Shorts use v1")
    t0 = time.time()
    workdir.mkdir(parents=True, exist_ok=True)
    engine = KokoroEngine.get(voice)
    narrations: list[Narration] = [engine.narrate(s.narration) for s in script.scenes]
    unknown = sorted({w for n in narrations for w in n.unknown_words})
    log.info("narration synthesized in %.1fs", time.time() - t0)

    audio = np.concatenate([n.audio for n in narrations])
    raw_wav = workdir / "narration_kokoro.wav"
    sf.write(raw_wav, audio, KOKORO_SR, subtype="PCM_16")
    total = len(audio) / KOKORO_SR

    # exact sentence-timed captions
    cues, offset, starts_sec = [], 0.0, []
    for n in narrations:
        starts_sec.append(offset)
        for s in n.sentences:
            chunks = chunk_text(s.text, 9)
            span = s.end - s.start
            total_chars = sum(len(c) for c in chunks) or 1
            tt = offset + s.start
            for c in chunks:
                d = span * len(c) / total_chars
                cues.append(Cue(tt, tt + d, c))
                tt += d
        offset += n.duration
    starts_sec.append(offset)
    srt = write_srt(cues, workdir / "captions.srt")
    ass = write_ass(cues, workdir / "captions.ass", W, H, portrait=False)

    plans, prev_sets = [], []
    for i, (scene, n) in enumerate(zip(script.scenes, narrations)):
        p = plan_scene(scene, n.sentences, n.duration, i, prev_sets, first=i == 0)
        plans.append(p)
        prev_sets.append(p.set)
    envs = [envelope(n.audio, KOKORO_SR, FPS) for n in narrations]
    frame_starts = [int(round(s * FPS)) for s in starts_sec]

    job = dict(script=script, plans=plans, envs=envs, starts=frame_starts, workdir=workdir)
    workers = workers or max(1, (os.cpu_count() or 2))
    t1 = time.time()
    # "spawn" (not fork): the parent holds ONNX Runtime threads, and forking a threaded process can deadlock
    with mp.get_context("spawn").Pool(workers, initializer=_init_worker, initargs=(job,)) as pool:
        segs = pool.map(_render_segment, range(len(script.scenes)), chunksize=1)
    log.info("frames rendered in %.1fs", time.time() - t1)

    concat = workdir / "segments.txt"
    concat.write_text("".join(f"file '{Path(s).name}'\n" for s in segs))
    joined = workdir / "video_noaudio.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
                    "-c", "copy", str(joined)], check=True)
    fonts_dir = Path(__file__).resolve().parents[2] / "assets" / "fonts"
    video = workdir / "video.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-i", str(raw_wav),
        "-vf", f"ass='{_ffmpeg_filter_path(ass)}':fontsdir='{_ffmpeg_filter_path(fonts_dir)}'",
        "-af", _loudnorm_args(raw_wav), "-ar", "48000",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(video)], check=True)
    for s in segs:
        Path(s).unlink(missing_ok=True)
    joined.unlink(missing_ok=True)
    return AnimatedResult(video, srt, total, time.time() - t0, unknown, voice)


__all__ = ["render_animated", "SceneFrames", "AnimatedResult"]
