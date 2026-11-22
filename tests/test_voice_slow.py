"""Voice prompt: only Google's short form "<direction>: <text>" is ever sent (a long style paragraph was read aloud:
22 words -> 29 s). Slow audio is still guarded (<90 spoken wpm: asked once more, then held, naming the scene).
All HTTP simulated."""
import base64

import numpy as np
import pytest

from glivarao.tts.gemini_tts import (DIRECTION, GeminiTTSNarrator, SpendLedger, active_speech_seconds, spoken_words,
                                     spoken_wpm, tts_prompt)
from glivarao.tts.voice_lock import ENERGETIC_STYLE, VoiceUnavailable


def _speech(seconds, pauses=()):
    sr = 24000
    a = (0.3 * np.sin(np.linspace(0, 2 * np.pi * 150 * seconds, int(seconds * sr)))).astype(np.float32)
    for start, length in pauses:
        a[int(start * sr):int((start + length) * sr)] = 0
    return a


class Gemini:
    """Like the real model: a short '<direction>: ' prefix is followed, anything longer before the text is READ."""

    def __init__(self, always_slow=False):
        self.prompts, self.always_slow = [], always_slow

    def post(self, url, headers=None, json=None, timeout=None):
        prompt = json["contents"][0]["parts"][0]["text"]
        self.prompts.append(prompt)
        head, _, text = prompt.partition(": ")
        spoken = prompt if len(head.split()) > 10 else text
        sec = spoken_words(spoken) / 148 * 60 * (3 if self.always_slow else 1)    # numbers take time to say
        pcm = (_speech(sec) * 32767).astype("<i2")
        body = {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;rate=24000", "data": base64.b64encode(pcm.tobytes()).decode()}}]}}]}
        return type("R", (), {"status_code": 200, "json": lambda s: body})()


SCENE = ("As of November 2026, the average card rate was about twenty-two percent, and most people never notice how "
         "fast it grows.")                                                            # 22 words, like the held scene


def _n(tmp_path, http, **kw):
    return GeminiTTSNarrator("K", voice="Charon", style=f"{ENERGETIC_STYLE} Fast, upbeat delivery.", session=http,
                             cache_dir=tmp_path / "c", ledger=SpendLedger(tmp_path / "s.json"), sleep=lambda s: None,
                             **kw)


def test_only_the_short_direction_is_sent_and_the_speech_is_normal(tmp_path):
    http = Gemini()
    n = _n(tmp_path, http).narrate(SCENE)
    assert http.prompts == [f"{DIRECTION}: {SCENE}"] and len(DIRECTION.split()) <= 10
    assert ENERGETIC_STYLE not in http.prompts[0]                                 # the long style is never sent
    assert 6 < n.duration < 11                                                    # 22 words at ~148 wpm, not 29 s


def test_direction_longer_than_10_words_is_refused(tmp_path):
    with pytest.raises(ValueError, match="at most 10 words"):
        tts_prompt("x", "Narrate as a confident upbeat American male YouTube finance host please")
    with pytest.raises(ValueError):
        _n(tmp_path, Gemini(), direction=ENERGETIC_STYLE)


def test_slow_audio_is_asked_once_more_then_held_naming_the_scene(tmp_path):
    http = Gemini(always_slow=True)
    with pytest.raises(VoiceUnavailable, match="most people never notice"):
        GeminiTTSNarrator("K", voice="Charon", session=http, cache_dir=tmp_path / "c",
                          ledger=SpendLedger(tmp_path / "s.json"), sleep=lambda s: None).narrate(SCENE)
    assert len(http.prompts) == 2 and http.prompts[0] == http.prompts[1]          # same short prompt, no strict mode
    assert (tmp_path / "voice_debug").exists()


def test_old_cached_clips_are_not_reused(tmp_path):
    import hashlib

    n = _n(tmp_path, Gemini())
    old = hashlib.sha256(f"{n.model}|{n.voice}|{n.style}|{SCENE}".encode()).hexdigest()[:24]
    assert n._key_for(SCENE).name != f"gem_{old}.npy"


def test_pauses_and_spelled_out_numbers_are_not_slow_speech():
    assert spoken_words("$1,368.5 billion") >= 8 and spoken_words("22.36%") >= 5
    a = _speech(8.0, pauses=[(2.0, 1.5), (5.0, 1.2)])
    assert active_speech_seconds(a) == pytest.approx(5.3, abs=0.15)
    text = "As of November 2026, the average card rate was 22.36%, on $1,368.5 billion owed."
    assert spoken_wpm(text, _speech(9.0)) > 90


def test_short_scenes_are_not_checked_and_tiny_scenes_are_merged(tmp_path):
    from glivarao.content.short_fit import merge_tiny_scenes
    from glivarao.models import Scene, Script

    n = _n(tmp_path, Gemini(always_slow=True)).narrate("Here's the catch.")
    assert n.duration > 0
    sc = [Scene(heading="Hook", narration="Credit cards can trap you for years if you only pay the minimum."),
          Scene(heading="Wait", narration="Here's why."),
          Scene(heading="Math", narration="Interest is charged on the balance every single month you carry it."),
          Scene(heading="End", narration="This video is for education only and isn't financial advice.")]
    s = merge_tiny_scenes(Script(format="short", topic="t", title="t", description="", thumbnail_text="", scenes=sc))
    assert len(s.scenes) == 3 and s.scenes[0].narration.endswith("Here's why.")


def test_voice_test_command_measures_real_scenes_and_fails_off_pace(settings, tmp_path, monkeypatch, capsys):
    from dataclasses import replace

    from glivarao import __main__ as cli
    from glivarao.tts import voice_test

    s = replace(settings, gemini_api_key="K", tts_cache_dir=str(tmp_path / "c"),
                tts_spend_ledger_path=str(tmp_path / "l.json"), output_dir=tmp_path / "out")
    monkeypatch.setattr(cli, "get_settings", lambda: s)
    monkeypatch.setattr("glivarao.tts.gemini_tts.requests.Session", lambda: Gemini())
    res = voice_test.run(s)
    assert len(res) == 3 and res[2]["scene"] == "disclaimer" and all(r["ok"] for r in res), res
    assert all(r["prompt"].startswith(DIRECTION) for r in res)
    cli.main(["voice-test", "--no-telegram"])
    assert "voice test passed" in capsys.readouterr().out
    monkeypatch.setattr("glivarao.tts.gemini_tts.requests.Session", lambda: Gemini(always_slow=True))
    with pytest.raises(SystemExit):
        cli.main(["voice-test", "--no-telegram"])
