"""Voice-note transcription for your input.

1. Local and free: faster-whisper (if installed; the model downloads once, ~150 MB for "base.en").
2. Otherwise Gemini (only when ALLOW_PAID_APIS=true and GEMINI_API_KEY is set; a voice note costs a fraction of
   a cent).
3. Otherwise None: the bot asks you to send the same thing as text.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

log = logging.getLogger(__name__)
WHISPER_MODEL = "base.en"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _local(path: Path) -> str | None:
    try:
        from faster_whisper import WhisperModel  # optional dependency
    except ImportError:
        return None
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(path), language="en", vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip() or None


def _gemini(path: Path, settings, session=None) -> str | None:
    if not (settings.allow_paid_apis and settings.gemini_api_key):
        return None
    import requests

    http = session or requests
    body = {"contents": [{"parts": [
        {"text": "Transcribe this voice note exactly, in English. Return only the transcript."},
        {"inline_data": {"mime_type": "audio/ogg", "data": base64.b64encode(path.read_bytes()).decode()}}]}]}
    model = getattr(settings, "gemini_transcribe_model", "gemini-3.5-flash")
    try:
        r = http.post(GEMINI_URL.format(model=model), headers={"x-goog-api-key": settings.gemini_api_key},
                      json=body, timeout=120)
        if r.status_code != 200:
            log.warning("Gemini transcription HTTP %s", r.status_code)
            return None
        parts = r.json()["candidates"][0]["content"]["parts"]
        return " ".join(p.get("text", "") for p in parts).strip() or None
    except Exception as exc:  # noqa: BLE001  (never leak the key; requests errors don't include headers)
        log.warning("Gemini transcription failed: %s", type(exc).__name__)
        return None


def transcribe(path: Path, settings, session=None) -> tuple[str | None, str]:
    """Returns (transcript or None, engine used)."""
    try:
        text = _local(Path(path))
        if text:
            return text, "faster-whisper (local)"
    except Exception as exc:  # noqa: BLE001
        log.warning("local transcription failed: %s", exc)
    text = _gemini(Path(path), settings, session)
    if text:
        return text, "Gemini"
    return None, "none"


__all__ = ["transcribe"]
