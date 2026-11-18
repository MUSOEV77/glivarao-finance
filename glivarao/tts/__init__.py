"""Text-to-speech narration (American English male voice).

Providers
- elevenlabs : production. Requires ELEVENLABS_API_KEY and a US-English male ELEVENLABS_VOICE_ID.
- google     : production. Google Cloud Text-to-Speech, default voice en-US-Neural2-D (male).
- espeak     : DEV PLACEHOLDER ONLY (robotic). Never publish with it.
- silent     : silence sized to the text (~150 wpm). For CI/tests.

Every provider returns a 48 kHz mono 16-bit WAV so downstream timing is uniform.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import requests

from ..config import Settings

SAMPLE_RATE = 48_000


class TTSError(RuntimeError):
    pass


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def _normalize(src: Path, dst: Path, pad_sec: float = 0.35) -> None:
    """Convert anything ffmpeg reads to 48k mono s16 WAV, with a short tail pause."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", str(SAMPLE_RATE),
           "-af", f"apad=pad_dur={pad_sec}", "-sample_fmt", "s16", str(dst)]
    subprocess.run(cmd, check=True)


def _silent(text: str, dst: Path) -> None:
    seconds = max(1.0, len(text.split()) / 150 * 60) + 0.35
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"\x00\x00" * int(seconds * SAMPLE_RATE))


def _espeak(text: str, dst: Path) -> None:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise TTSError("espeak-ng not installed (apt-get install espeak-ng) — or use TTS_PROVIDER=silent")
    raw = dst.with_suffix(".raw.wav")
    subprocess.run([exe, "-v", "en-us+m3", "-s", "160", "-w", str(raw), text], check=True)
    _normalize(raw, dst)
    raw.unlink(missing_ok=True)


def _elevenlabs(text: str, dst: Path, s: Settings) -> None:
    if not (s.elevenlabs_api_key and s.elevenlabs_voice_id):
        raise TTSError("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are required")
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{s.elevenlabs_voice_id}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": s.elevenlabs_api_key, "accept": "audio/mpeg"},
        json={"text": text, "model_id": s.elevenlabs_model_id,
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        timeout=120,
    )
    if resp.status_code != 200:
        raise TTSError(f"ElevenLabs HTTP {resp.status_code}: {resp.text[:200]}")
    mp3 = dst.with_suffix(".mp3")
    mp3.write_bytes(resp.content)
    _normalize(mp3, dst)
    mp3.unlink(missing_ok=True)


def _google(text: str, dst: Path, s: Settings) -> None:
    if not s.google_tts_api_key:
        raise TTSError("GOOGLE_TTS_API_KEY is required")
    resp = requests.post(  # key in a header, not the URL, so it can't leak via exception messages
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        headers={"X-Goog-Api-Key": s.google_tts_api_key},
        json={"input": {"text": text},
              "voice": {"languageCode": "en-US", "name": s.google_tts_voice},
              "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": SAMPLE_RATE, "speakingRate": 1.0}},
        timeout=120,
    )
    if resp.status_code != 200:
        raise TTSError(f"Google TTS HTTP {resp.status_code}: {resp.text[:200]}")
    raw = dst.with_suffix(".raw.wav")
    raw.write_bytes(base64.b64decode(resp.json()["audioContent"]))
    _normalize(raw, dst)
    raw.unlink(missing_ok=True)


def synthesize(text: str, dst: Path, settings: Settings, provider: str | None = None) -> float:
    """Synthesize `text` to `dst` (WAV). Returns duration in seconds."""
    provider = provider or settings.tts_provider
    dst.parent.mkdir(parents=True, exist_ok=True)
    if provider == "silent":
        _silent(text, dst)
    elif provider == "espeak":
        _espeak(text, dst)
    elif provider == "elevenlabs":
        _elevenlabs(text, dst, settings)
    elif provider == "google":
        _google(text, dst, settings)
    else:
        raise TTSError(f"Unknown TTS provider {provider!r}")
    return wav_duration(dst)


def amplitude_envelope(path: Path, fps: int) -> np.ndarray:
    """Per-frame loudness in [0,1], used to drive character mouth animation."""
    data, sr = read_wav_mono(path)
    hop = max(1, sr // fps)
    n = int(np.ceil(len(data) / hop))
    env = np.array([np.sqrt(np.mean(data[i * hop:(i + 1) * hop] ** 2)) if i * hop < len(data) else 0.0
                    for i in range(n)])
    peak = env.max() if env.size and env.max() > 0 else 1.0
    return np.clip(env / peak, 0, 1)
