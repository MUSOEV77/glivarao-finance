"""Which exact voice made a video? And lock exactly that voice.

    python -m glivarao voice-of --find "credit report" --short      # today's Short about credit reports
    python -m glivarao voice-of 20261120-short-ab12cd               # a known job
    python -m glivarao voice-lock-from 20261120-short-ab12cd        # lock that voice for every video

How it is found (exact, not guessed): every Gemini clip is cached under sha256(model|voice|style|text). For the
job's final script, each candidate (model x voice x style x pace) is hashed and looked up in the cache; the
combination whose clips exist is the one that was used. The speed is measured: raw clip speech time divided by
the speech time in the job's narration track. Newer jobs also record all of this in metadata.json ("tts").
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from itertools import product
from pathlib import Path

import numpy as np

KNOWN_VOICES = ["Charon", "Puck", "Sadachbia", "Fenrir", "Achird", "Kore", "Orus", "Algenib", "Sadaltager",
                "Iapetus", "Enceladus", "Umbriel", "Algieba", "Alnilam", "Rasalgethi", "Schedar", "Zubenelgenubi"]
SPEEDS = (1.0, 1.05, 1.08, 1.1, 1.15, 1.2)


def find_jobs(store, query: str = "", fmt: str | None = None, day: date | None = None, limit: int = 300) -> list:
    day_s = (day or date.today()).strftime("%Y%m%d")
    out = []
    for job in store.list(limit=limit):
        if fmt and job.format != fmt:
            continue
        if day and not job.id.startswith(day_s):
            continue
        if query and query.lower() not in job.topic.lower():
            out_dir = Path(job.video_path).parent if job.video_path else None
            meta = (out_dir / "metadata.json") if out_dir else None
            text = meta.read_text().lower() if meta and meta.exists() else ""
            if query.lower() not in text:
                continue
        out.append(job)
    return out


def _cache_key(cache: Path, model: str, voice: str, style: str, text: str) -> Path:
    h = hashlib.sha256(f"{model}|{voice}|{style}|{text}".encode()).hexdigest()[:24]
    return cache / f"gem_{h}.npy"


def _style_candidates(settings) -> list[tuple[str, str, str]]:
    """(style_text_sent, base_style, pace) for every style/pace the code has ever used plus the current .env."""
    from .gemini_tts import DEFAULT_STYLE
    from .voice_lock import ENERGETIC_STYLE, PACES

    bases = list(dict.fromkeys([settings.gemini_tts_style.strip(), DEFAULT_STYLE.strip(), ENERGETIC_STYLE.strip(),
                                ("Narrate as a warm, deep, confident American male documentary narrator explaining "
                                 "personal finance. Natural, measured pace with real pauses between sentences; clear "
                                 "numbers and money amounts; subtle emphasis on key figures; trustworthy, never "
                                 "theatrical.")]))
    out = [(f"{b} {p}", b, pace) for b, (pace, p) in product(bases, PACES.items())]
    out += [(b, b, "") for b in bases]          # the very first version sent the style without a pace sentence
    return out


def identify(settings, job) -> dict:
    from ..models import Script
    from .gemini_tts import GeminiTTSNarrator, speech_seconds

    out_dir = Path(job.video_path).parent if job.video_path else settings.output_dir / job.id
    meta = json.loads((out_dir / "metadata.json").read_text()) if (out_dir / "metadata.json").exists() else {}
    if meta.get("tts"):
        return {**meta["tts"], "how": "recorded in metadata.json", "job": job.id}
    script = Script.model_validate_json(Path(job.script_path).read_text())
    texts = [GeminiTTSNarrator._prep(s.narration) for s in script.scenes if s.narration.strip()]
    cache = Path(settings.tts_cache_dir)
    label = meta.get("voice", "")
    voices = list(dict.fromkeys([v for v in KNOWN_VOICES if v in label] + [settings.gemini_tts_voice] + KNOWN_VOICES))
    models = list(dict.fromkeys([settings.gemini_tts_model, "gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]))
    best = None
    for model, voice, (style, base, pace) in product(models, voices, _style_candidates(settings)):
        hits = [_cache_key(cache, model, voice, style, t) for t in texts]
        n = sum(p.exists() for p in hits)
        if n and (best is None or n > best[0]):
            best = (n, model, voice, style, base, pace, [p for p in hits if p.exists()])
        if n == len(texts):
            break
    res = {"job": job.id, "topic": job.topic, "format": job.format, "voice_label": label,
           "duration_s": job.duration_sec}
    if best is None:
        return {**res, "how": "not found in the voice cache (cache cleared?)"}
    n, model, voice, style, base, pace, files = best
    raw = sum(speech_seconds(np.load(p)) for p in files)
    speed = None
    wav = out_dir / "narration_kokoro.wav"
    if wav.exists() and n == len(texts):
        import soundfile as sf

        audio, sr = sf.read(wav, dtype="float32")
        final = len(audio) / sr - 0.6 * len(texts)   # minus the fixed 0.15 s lead-in + 0.45 s tail per scene
        if final > 0:
            measured = raw / final
            speed = min(SPEEDS, key=lambda v: abs(v - measured)) if abs(
                min(SPEEDS, key=lambda v: abs(v - measured)) - measured) < 0.03 else round(measured, 2)
    return {**res, "model": model, "voice": voice, "pace": pace or "(none)", "style": base, "style_sent": style,
            "speed": speed if speed is not None else settings.gemini_tts_speed, "speed_measured": speed is not None,
            "scenes_matched": f"{n}/{len(texts)}", "how": "matched in the voice cache (exact)"}


def lock_from(settings, store, job_id: str, env_path: Path | None = None) -> dict:
    from dataclasses import replace

    from ..studio.voice_audition import write_env
    from . import voice_lock

    info = identify(settings, store.get(job_id))
    if "voice" not in info:
        raise ValueError(f"could not identify the voice of {job_id}: {info.get('how')}")
    pace = info["pace"] if info["pace"] in voice_lock.PACES else settings.gemini_tts_pace
    values = {"GEMINI_TTS_MODEL": info["model"], "GEMINI_TTS_VOICE": info["voice"], "GEMINI_TTS_PACE": pace,
              "GEMINI_TTS_STYLE": info["style"], "GEMINI_TTS_SPEED": str(info["speed"]), "TTS_PROVIDER": "gemini_tts"}
    write_env(values, env_path)
    new = replace(settings, gemini_tts_model=info["model"], gemini_tts_voice=info["voice"], gemini_tts_pace=pace,
                  gemini_tts_style=info["style"], gemini_tts_speed=float(info["speed"]))
    voice_lock.reset(new, store)
    store.kv_set("voice_locked_from", json.dumps({"job": job_id, **values}))
    return values


__all__ = ["find_jobs", "identify", "lock_from"]
