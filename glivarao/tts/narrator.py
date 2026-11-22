"""Chooses the narrator for a whole video.

TTS_PROVIDER=gemini_tts (the channel's locked voice, the default): Gemini TTS "Charon" ONLY. If it can't be used
(paid use off, no key, budget cap, settings changed, API down after retries) VoiceUnavailable is raised and the
video is held; there is no fallback voice and no fallback model.
Other providers (kokoro, google_chirp) are kept for development and tests."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from .gemini_tts import GeminiTTSNarrator, SpendLedger
from .voice_lock import VoiceUnavailable, style_prompt, verify
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
        base = {"google_chirp": "Google Chirp 3 HD", "kokoro": "Kokoro",
                "gemini_tts": f"Gemini TTS ({getattr(self.narrator, 'model', '')})"}[self.provider]
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


def gemini_narrator(settings: Settings, session=None, sleep=None) -> GeminiTTSNarrator:
    kw = {"sleep": sleep} if sleep else {}
    return GeminiTTSNarrator(
        settings.gemini_api_key, model=settings.gemini_tts_model, voice=settings.gemini_tts_voice,
        style=style_prompt(settings), price_per_m_audio=settings.gemini_tts_price,
        tokens_per_sec=settings.gemini_tts_tokens_per_sec, monthly_budget_usd=settings.tts_monthly_budget_usd,
        cache_dir=Path(settings.tts_cache_dir), ledger=SpendLedger(Path(settings.tts_spend_ledger_path)),
        session=session, retries=settings.gemini_tts_retries, backoff_sec=settings.gemini_tts_backoff_sec,
        speed=settings.gemini_tts_speed, direction=settings.gemini_tts_direction, **kw)


def _gemini_choice(settings: Settings, script_text: str, session, store, sleep) -> NarratorChoice:
    """The locked voice or nothing: the whole video must fit the monthly cap before the first paid call."""
    if not settings.allow_paid_apis:
        raise VoiceUnavailable("paid voice is switched off (ALLOW_PAID_APIS=false)")
    if not settings.gemini_api_key:
        raise VoiceUnavailable("GEMINI_API_KEY is not set")
    if store is None:
        from ..storage import JobStore

        store = JobStore(settings.db_path)
    verify(settings, store)  # pinned model + settings unchanged since the voice was locked
    n = gemini_narrator(settings, session, sleep)
    n.check_budget(n.uncached_estimate_usd([s for s in script_text.split("\n\n") if s.strip()]))
    return NarratorChoice(n, "gemini_tts", settings.gemini_tts_voice)


def get_narrator(settings: Settings, script_text: str = "", kokoro_voice: str | None = None,
                 session=None, store=None, sleep=None) -> NarratorChoice:
    if settings.tts_provider == "gemini_tts":
        return _gemini_choice(settings, script_text, session, store, sleep)
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
    """Narrate every scene with one voice. Gemini (locked voice): any failure raises VoiceUnavailable and the
    video is held (scenes already synthesized are cached, so the retry doesn't pay for them twice).
    Development providers only: if the paid API fails part-way, the whole video is redone with Kokoro.
    Returns (narrations, final_choice)."""
    try:
        return [choice.narrator.narrate(t) for t in texts], choice
    except PaidTTSError as exc:
        if choice.provider in ("kokoro", "gemini_tts"):
            raise
        log.warning("paid TTS failed (%s); using Kokoro backup for the whole video", exc)
        backup = kokoro_choice(settings, kokoro_voice, f"paid TTS error: {exc}")
        return [backup.narrator.narrate(t) for t in texts], backup
