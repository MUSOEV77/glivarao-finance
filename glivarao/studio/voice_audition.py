"""Voice audition: the same ~30-second script voiced by several Gemini TTS voices, sent to Telegram as labelled
audio with a button under each one. Tapping a button locks that voice (name, speed, style prompt) in .env, resets
the voice lock on purpose, and re-voices the videos on hold.

    python -m glivarao voice-audition                     # Puck, Sadachbia, Fenrir, Achird, Charon (+15%)
    python -m glivarao voice-pick Puck                    # same as tapping the button

Speed: Gemini TTS has no numeric speed setting, so each sample is asked for an energetic ~170 wpm delivery, then
measured; a pitch-preserving tempo (ffmpeg atempo) brings it to TTS_TARGET_WPM (165-175 wpm). The factor found
here is what gets locked as GEMINI_TTS_SPEED, so every video keeps the same pace. Charon gets a fixed +15%.
Cost: 5 samples x ~30 s of audio, about $0.02 each at the capped voice price; counted in the voice budget.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)

SAMPLE = ("Here's something your credit card company would rather you didn't know. If you owe five thousand "
          "dollars at twenty-two percent and only pay the minimum, you could be paying for well over fifteen years. "
          "That's not a typo. The fix is simpler than you think: pick one fixed payment, automate it, and attack "
          "the highest rate first. Do that, and you'll be debt-free years sooner, with thousands of dollars still "
          "in your pocket. Let's break down exactly how it works.")
CANDIDATES = [("Puck", None), ("Sadachbia", None), ("Fenrir", None), ("Achird", None), ("Charon", 1.15)]
SPEED_RANGE = (0.85, 1.30)


def _env_path() -> Path:
    import os

    return Path(os.environ.get("ENV_FILE", ".env"))


def write_env(updates: dict[str, str], path: Path | None = None) -> None:
    """Set KEY=value lines in .env (same rules as deploy/set-key.sh: owner-only file, values never printed)."""
    path = path or _env_path()
    lines = path.read_text().splitlines() if path.exists() else []
    done, out = set(), []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in updates and not line.lstrip().startswith("#"):
            out.append(f"{key}={updates[key]}")
            done.add(key)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in updates.items() if k not in done]
    path.write_text("\n".join(out) + "\n")
    path.chmod(0o600)


def _mp3(audio: np.ndarray, sr: int, dst: Path) -> Path:
    wav = dst.with_suffix(".wav")
    sf.write(wav, audio, sr, subtype="PCM_16")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "128k",
                    str(dst)], check=True)
    wav.unlink(missing_ok=True)
    return dst


def make_samples(settings, store, out_dir: Path, session=None, candidates=CANDIDATES) -> list[dict]:
    """Synthesize every candidate; returns [{voice, speed, wpm_raw, wpm, path, seconds}] (failed voices skipped)."""
    from .pause import guard

    guard(settings, "voice audition")
    from ..tts.gemini_tts import KOKORO_SR, GeminiTTSNarrator, SpendLedger, apply_tempo, words_per_minute
    from ..tts.voice_lock import ENERGETIC_STYLE, PACES, VoiceUnavailable

    style = f"{ENERGETIC_STYLE} {PACES['energetic']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = settings.tts_target_wpm
    results = []
    for voice, fixed in candidates:
        n = GeminiTTSNarrator(settings.gemini_api_key, model=settings.gemini_tts_model, voice=voice, style=style,
                              price_per_m_audio=settings.gemini_tts_price,
                              tokens_per_sec=settings.gemini_tts_tokens_per_sec,
                              monthly_budget_usd=settings.tts_monthly_budget_usd,
                              cache_dir=Path(settings.tts_cache_dir),
                              ledger=SpendLedger(Path(settings.tts_spend_ledger_path)), session=session,
                              retries=settings.gemini_tts_retries, backoff_sec=settings.gemini_tts_backoff_sec)
        try:
            raw = n._scene_audio(n._prep(SAMPLE))
        except VoiceUnavailable as exc:
            log.warning("audition: %s failed: %s", voice, exc)
            results.append({"voice": voice, "error": str(exc)})
            continue
        wpm_raw = words_per_minute(SAMPLE, raw)
        speed = fixed if fixed else (min(SPEED_RANGE[1], max(SPEED_RANGE[0], target / wpm_raw)) if wpm_raw else 1.0)
        audio = apply_tempo(raw, speed)
        path = _mp3(audio * (0.89 / (float(np.abs(audio).max()) or 1.0)), KOKORO_SR, out_dir / f"{voice}.mp3")
        results.append({"voice": voice, "speed": round(speed, 3), "wpm_raw": round(wpm_raw),
                        "wpm": round(words_per_minute(SAMPLE, audio)), "path": str(path),
                        "seconds": round(len(audio) / KOKORO_SR, 1), "style": style})
    store.kv_set("voice_audition", json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                               "samples": results}))
    return results


def send_samples(settings, results: list[dict], client=None) -> int:
    from ..publish.telegram import _client

    c = _client(settings, client)
    chat = settings.telegram_approver_chat_id
    ok = [r for r in results if "path" in r]
    c.call("sendMessage", chat_id=chat, text=(
        f"🎙 Voice audition: the same 30-second script in {len(ok)} voices, energetic style, tuned to about "
        f"{settings.tts_target_wpm} words per minute. Listen, then tap ✅ under the one you want. It gets locked for "
        "every video (name, speed, style), and the videos on hold are re-voiced with it."))
    for k, r in enumerate(ok, 1):
        label = f"{k}. {r['voice']}" + (" (+15%)" if r["voice"] == "Charon" else "")
        with open(r["path"], "rb") as fh:
            c.call("sendAudio", files={"audio": (f"{k}_{r['voice']}.mp3", fh)}, chat_id=chat, title=label,
                   performer="GLIVARAO voice audition",
                   caption=f"{label}: {r['wpm']} words/min (raw {r['wpm_raw']}, speed ×{r['speed']}), "
                           f"{r['seconds']} s",
                   reply_markup={"inline_keyboard": [[{"text": f"✅ Use {r['voice']}",
                                                       "callback_data": f"voicepick:{r['voice']}"}]]})
    for r in results:
        if "error" in r:
            c.call("sendMessage", chat_id=chat, text=f"⚠️ {r['voice']} could not be generated: {r['error'][:200]}")
    return len(ok)


def pick(settings, store, voice: str, env_path: Path | None = None) -> dict:
    """Lock the chosen audition voice in .env and in the voice lock. Returns the locked values."""
    from ..tts import voice_lock

    data = json.loads(store.kv_get("voice_audition", "{}"))
    sample = next((r for r in data.get("samples", []) if r.get("voice", "").lower() == voice.lower()
                   and "path" in r), None)
    if sample is None:
        raise ValueError(f"{voice} is not in the last audition (run: python -m glivarao voice-audition)")
    values = {"GEMINI_TTS_VOICE": sample["voice"], "GEMINI_TTS_PACE": "energetic",
              "GEMINI_TTS_STYLE": voice_lock.ENERGETIC_STYLE, "GEMINI_TTS_SPEED": str(sample["speed"]),
              "TTS_TARGET_WPM": str(settings.tts_target_wpm)}
    write_env(values, env_path)
    new = replace(settings, gemini_tts_voice=sample["voice"], gemini_tts_pace="energetic",
                  gemini_tts_style=voice_lock.ENERGETIC_STYLE, gemini_tts_speed=float(sample["speed"]))
    voice_lock.reset(new, store)                      # an intentional change: the new lock
    store.kv_set("revoice_requested", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return {**values, "wpm": sample["wpm"]}


__all__ = ["make_samples", "send_samples", "pick", "write_env", "SAMPLE", "CANDIDATES"]
