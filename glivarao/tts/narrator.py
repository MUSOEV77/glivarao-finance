"""Chooses the narrator for a whole video: the approved paid voice when allowed and affordable, otherwise the
free Kokoro am_michael backup. The choice is made once per video (never mid-video), so a video always has
one consistent voice, and the reason for any fallback is recorded for the reviewer."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from .google_chirp import (BudgetExceeded, GoogleChirpNarrator, PaidTTSError, UsageLedger, monthly_char_limit)
from .kokoro import KokoroEngine

log = logging.getLogger(__name__)


@dataclass
class NarratorChoice:
    narrator: object
    provider: str
    voice: str
    note: str = ""          # why the backup was used, if it was

    @property
    def label(self) -> str:
        base = {"google_chirp": "Google Chirp 3 HD", "kokoro": "Kokoro"}[self.provider]
        return f"{base} {self.voice}" + (f" (backup: {self.note})" if self.note else "")


def kokoro_choice(settings: Settings, voice: str | None = None, note: str = "") -> NarratorChoice:
    v = voice or settings.kokoro_voice
    return NarratorChoice(KokoroEngine.get(v), "kokoro", v, note)


def paid_choice(settings: Settings, session=None) -> GoogleChirpNarrator:
    return GoogleChirpNarrator(
        settings.google_tts_api_key, voice=settings.google_tts_voice, rate=settings.google_tts_rate,
        cache_dir=Path(settings.tts_cache_dir), ledger=UsageLedger(Path(settings.tts_ledger_path)),
        char_limit=monthly_char_limit(settings.tts_monthly_budget_usd, settings.tts_price_per_million,
                                      settings.tts_free_chars_per_month), session=session)


def get_narrator(settings: Settings, script_text: str = "", kokoro_voice: str | None = None,
                 session=None) -> NarratorChoice:
    if settings.tts_provider != "google_chirp":
        return kokoro_choice(settings, kokoro_voice)
    if not settings.allow_paid_apis:
        return kokoro_choice(settings, kokoro_voice, "paid voice not approved (ALLOW_PAID_APIS=false)")
    if not settings.google_tts_api_key:
        return kokoro_choice(settings, kokoro_voice, "GOOGLE_TTS_API_KEY not set")
    n = paid_choice(settings, session)
    try:
        n.check_budget(n.uncached_chars(script_text))  # whole video must fit, or the whole video uses the backup
    except BudgetExceeded as exc:
        return kokoro_choice(settings, kokoro_voice, str(exc))
    return NarratorChoice(n, "google_chirp", settings.google_tts_voice)


def narrate_all(choice: NarratorChoice, texts: list[str], settings: Settings, kokoro_voice: str | None = None):
    """Narrate every scene with one voice. If the paid API fails part-way, redo the whole video with the
    backup so voices are never mixed. Returns (narrations, final_choice)."""
    try:
        return [choice.narrator.narrate(t) for t in texts], choice
    except PaidTTSError as exc:
        if choice.provider == "kokoro":
            raise
        log.warning("paid TTS failed (%s); using Kokoro backup for the whole video", exc)
        backup = kokoro_choice(settings, kokoro_voice, f"paid TTS error: {exc}")
        return [backup.narrator.narrate(t) for t in texts], backup
