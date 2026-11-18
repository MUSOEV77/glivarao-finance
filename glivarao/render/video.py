"""Assemble narration audio + animated frames + burned subtitles into an MP4 with ffmpeg."""
from __future__ import annotations

import logging
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..models import Script
from ..tts import SAMPLE_RATE, amplitude_envelope, synthesize, wav_duration
from .scene import Layout, SceneRenderer, frame_bytes
from .subtitles import Cue, scene_cues, write_ass, write_srt

log = logging.getLogger(__name__)
OUTPUT_FPS = 30


@dataclass
class RenderResult:
    video: Path
    srt: Path
    duration: float
    render_seconds: float


def _ffmpeg_filter_path(p: Path) -> str:
    return str(p.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def narrate(script: Script, workdir: Path, settings: Settings, provider: str | None = None):
    """Synthesize each scene; returns list of (wav_path, duration)."""
    out = []
    for i, scene in enumerate(script.scenes):
        wav = workdir / "audio" / f"scene_{i:03d}.wav"
        dur = synthesize(scene.narration, wav, settings, provider)
        out.append((wav, dur))
    return out


def concat_wavs(parts: list[Path], dst: Path) -> None:
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        for p in parts:
            with wave.open(str(p), "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))


def render_video(script: Script, workdir: Path, settings: Settings, tts_provider: str | None = None,
                 burn_subtitles: bool = True) -> RenderResult:
    t0 = time.time()
    workdir.mkdir(parents=True, exist_ok=True)
    layout = Layout.for_format(script.format)
    fps = settings.fps

    audio_parts = narrate(script, workdir, settings, tts_provider)
    narration = workdir / "narration.wav"
    concat_wavs([p for p, _ in audio_parts], narration)
    total = wav_duration(narration)

    # timing + captions
    cues: list[Cue] = []
    bounds, t = [], 0.0
    max_words = 4 if layout.portrait else 9
    for scene, (_, dur) in zip(script.scenes, audio_parts):
        cues += scene_cues(scene.narration, t, max(0.5, dur - 0.35), max_words)
        bounds.append((t, t + dur))
        t += dur
    srt = write_srt(cues, workdir / "captions.srt")
    ass = write_ass(cues, workdir / "captions.ass", layout.w, layout.h, layout.portrait)

    video = workdir / "video.mp4"
    vf = [f"fps={OUTPUT_FPS}"]
    if burn_subtitles:
        fonts_dir = Path(__file__).resolve().parents[2] / "assets" / "fonts"
        vf.append(f"ass='{_ffmpeg_filter_path(ass)}':fontsdir='{_ffmpeg_filter_path(fonts_dir)}'")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{layout.w}x{layout.h}", "-r", str(fps), "-i", "-",
        "-i", str(narration),
        "-vf", ",".join(vf),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",  # YouTube-friendly loudness
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", "-shortest", str(video),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        frame_cursor = 0
        for i, (scene, (wav, _)) in enumerate(zip(script.scenes, audio_parts)):
            start, end = bounds[i]
            end_frame = int(round(end * fps))
            n = max(1, end_frame - frame_cursor)
            env = amplitude_envelope(wav, fps)
            renderer = SceneRenderer(scene, layout, i, len(script.scenes))
            for f in range(n):
                loud = float(env[f]) if f < len(env) else 0.0
                proc.stdin.write(frame_bytes(renderer.frame(f, n, fps, loud)))
            frame_cursor += n
            log.info("scene %d/%d rendered (%d frames)", i + 1, len(script.scenes), n)
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg failed while encoding")
    except BrokenPipeError as exc:
        proc.kill()
        raise RuntimeError("ffmpeg exited early (check filters / fonts)") from exc
    return RenderResult(video=video, srt=srt, duration=total, render_seconds=time.time() - t0)


def probe(path: Path) -> dict:
    """Return width/height/duration/codecs via ffprobe."""
    import json

    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,width,height:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    return {"width": v["width"], "height": v["height"], "video_codec": v["codec_name"],
            "audio_codec": a["codec_name"] if a else None, "duration": float(data["format"]["duration"])}


def preview_clip(src: Path, dst: Path, seconds: int = 45, height: int = 480) -> Path:
    """Small low-res clip for Telegram review (bot uploads are limited to 50 MB)."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-t", str(seconds),
                    "-vf", f"scale=-2:{height}", "-c:v", "libx264", "-crf", "28", "-preset", "veryfast",
                    "-c:a", "aac", "-b:a", "96k", str(dst)], check=True)
    return dst


__all__ = ["render_video", "probe", "preview_clip", "RenderResult"]
