"""The channel voice is LOCKED: Gemini TTS, voice "Charon", pinned model version, fixed pace and style.

* The model must be an exact, pinned model ID: names containing "latest", "preview" or "exp" are refused, because
  aliases can be repointed to a different model (and a different-sounding voice) without notice.
* The first successful narration records a fingerprint of model + voice + pace + style. If the settings in .env
  ever change, rendering stops (videos are held, you get a Telegram alert) until you confirm the change on purpose:
      python -m glivarao voice-lock --reset
* There is NO fallback voice. If Gemini is unavailable (after retries with backoff), over budget, or paid use is
  switched off, the video is held and re-rendered later (see daily_v2.retry_held_videos).
"""
from __future__ import annotations

import hashlib
import json
import re

PINNED_MODEL = "gemini-3.8-flash-tts"   # Google's stable Gemini TTS model (Sept 2026); not an alias
LOCKED_VOICE = "Charon"
PACES = {
    "measured": "Natural, measured pace with real pauses between sentences.",
    "slow": "Slow, deliberate pace with generous pauses between sentences.",
    "brisk": "Brisk but clear pace with short pauses between sentences.",
}
UNPINNED = re.compile(r"latest|preview|\bexp\b|-exp", re.I)


class VoiceUnavailable(RuntimeError):
    """The locked voice can't be used right now. The video is held, never narrated by another voice."""


def check_model(model: str) -> None:
    if not model or UNPINNED.search(model):
        raise VoiceUnavailable(f"GEMINI_TTS_MODEL={model!r} is not a pinned model version (use {PINNED_MODEL})")


def style_prompt(settings) -> str:
    pace = PACES.get(settings.gemini_tts_pace)
    if pace is None:
        raise VoiceUnavailable(f"GEMINI_TTS_PACE={settings.gemini_tts_pace!r} must be one of {', '.join(PACES)}")
    return f"{settings.gemini_tts_style.strip()} {pace}"


def fingerprint(settings) -> dict:
    style = style_prompt(settings)
    return {"provider": "gemini_tts", "model": settings.gemini_tts_model, "voice": settings.gemini_tts_voice,
            "pace": settings.gemini_tts_pace, "style_sha": hashlib.sha256(style.encode()).hexdigest()[:16]}


def verify(settings, store) -> dict:
    """Raise VoiceUnavailable unless the current .env voice settings are pinned and match the recorded lock.
    Records the lock on first use. Returns the fingerprint."""
    check_model(settings.gemini_tts_model)
    fp = fingerprint(settings)
    if store is None:
        return fp
    saved = store.kv_get("voice_lock")
    if not saved:
        store.kv_set("voice_lock", json.dumps(fp))
        return fp
    old = json.loads(saved)
    if old != fp:
        diff = ", ".join(f"{k}: {old.get(k)!r} → {fp.get(k)!r}" for k in fp if old.get(k) != fp.get(k))
        raise VoiceUnavailable(f"voice settings changed ({diff}). If this is intentional, run "
                               "`python -m glivarao voice-lock --reset` on the server")
    return fp


def reset(settings, store) -> dict:
    check_model(settings.gemini_tts_model)
    fp = fingerprint(settings)
    store.kv_set("voice_lock", json.dumps(fp))
    return fp


__all__ = ["VoiceUnavailable", "PINNED_MODEL", "LOCKED_VOICE", "PACES", "check_model", "style_prompt",
           "fingerprint", "verify", "reset"]
