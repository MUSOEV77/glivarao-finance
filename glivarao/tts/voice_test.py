"""`python -m glivarao voice-test`: voice 3 real scenes with the REAL Gemini API, exactly as production does (same
short direction, same locked Charon voice, same speed), measure each one and send the audio to Telegram.

Each scene goes through the same per-scene pace correction as production (to TTS_PACE_WPM=158). Pass = every scene
at 150-166 spoken words/min AFTER correction, and none abnormally slow before it (exit code 0); otherwise exit code
1, so a command chain stops before any video is made. Never cached; costs about 1-2 cents.
"""
from __future__ import annotations

from pathlib import Path

SCENES = [
    ("hook", "As of November 2026, the average rate on credit cards that charge interest was 22.36% a year, and most "
             "people never notice it."),
    ("numbers", "Pay only the minimum on a $5,000 balance and you could pay about $1,800 in interest before it's "
                "finally gone."),
    ("disclaimer", "One line, one number: pay more than the minimum every single month. This video is for education "
                   "only and isn't financial advice."),
]
LOW, HIGH = 150.0, 166.0


def run(settings, out_dir: Path | None = None, session=None) -> list[dict]:
    from ..studio.voice_audition import _mp3
    from .gemini_tts import (KOKORO_SR, MIN_SANE_WPM, active_speech_seconds, estimate_usd, spoken_words, spoken_wpm,
                             tts_prompt)
    from .narrator import gemini_narrator

    n = gemini_narrator(settings, session=session)
    out_dir = out_dir or Path(settings.output_dir) / "voice_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    n.check_budget(sum(estimate_usd(t, n.price, n.tps) for _, t in SCENES))
    results = []
    for name, text in SCENES:
        prepped = n._prep(text)
        raw, tokens = n._request(prepped)                      # fresh API call, never the cache
        usd = tokens * n.price / 1e6
        n.ledger.add(usd, tokens)
        before = spoken_wpm(text, raw)
        audio, info = n.pace(text, raw)                       # the same correction production applies
        wpm = spoken_wpm(text, audio)
        path = _mp3(audio, KOKORO_SR, out_dir / f"{name}.mp3")
        results.append({"scene": name, "words": len(text.split()), "spoken_words": spoken_words(text),
                        "seconds": round(active_speech_seconds(audio), 1), "total_seconds": round(len(audio) / KOKORO_SR, 1),
                        "wpm_before": round(before), "factor": info["factor"],
                        "wpm": round(wpm), "ok": LOW <= wpm <= HIGH and before >= MIN_SANE_WPM, "path": str(path),
                        "usd": round(usd, 4),
                        "prompt": tts_prompt(prepped, n.direction)[:80]})
    return results


def send(settings, results: list[dict], client=None) -> None:
    from ..publish.telegram import _client

    c = _client(settings, client)
    chat = settings.telegram_approver_chat_id
    ok = all(r["ok"] for r in results)
    c.call("sendMessage", chat_id=chat, text=(
        f"🎙 Voice test ({settings.gemini_tts_voice}, real API, direction \"{settings.gemini_tts_direction}\"): "
        + ("✅ all scenes at a normal pace" if ok else "❌ a scene is off: production would hold it") + "\n" +
        "\n".join(f"{'✅' if r['ok'] else '❌'} {r['scene']}: {r['wpm_before']} -> {r['wpm']} spoken words/min "
                  f"(atempo x{r['factor']}, {r['words']} words, {r['seconds']} s of speech)" for r in results)))
    for r in results:
        with open(r["path"], "rb") as fh:
            c.call("sendAudio", files={"audio": (Path(r["path"]).name, fh)}, chat_id=chat,
                   title=f"Voice test: {r['scene']}", performer="GLIVARAO",
                   caption=f"{r['scene']}: {r['wpm']} words/min, {r['seconds']} s")


__all__ = ["run", "send", "SCENES", "LOW", "HIGH"]
