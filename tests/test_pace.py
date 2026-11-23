"""Same pace for every scene: each scene measured and atempo-corrected to 158 spoken wpm (152-164), factor clamped
0.85-1.20, the < 90 wpm hold guard runs BEFORE correction, Shorts length boost on top, voice-test 150-166."""
import base64

import numpy as np
import pytest

from glivarao.tts.gemini_tts import GeminiTTSNarrator, SpendLedger, spoken_words, spoken_wpm
from glivarao.tts.voice_lock import VoiceUnavailable


class PacedGemini:
    """Speaks each scene at a given raw pace (spoken words/min), like real takes that vary from scene to scene."""

    def __init__(self, paces):
        self.paces, self.k = list(paces), 0

    def post(self, url, headers=None, json=None, timeout=None):
        text = json["contents"][0]["parts"][0]["text"].partition(": ")[2]
        wpm = self.paces[min(self.k, len(self.paces) - 1)]
        self.k += 1
        sec = spoken_words(text) / wpm * 60
        a = (0.3 * np.sin(np.linspace(0, 2 * np.pi * 140 * sec, int(sec * 24000)))).astype(np.float32)
        pcm = (a * 32767).astype("<i2")
        body = {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;rate=24000", "data": base64.b64encode(pcm.tobytes()).decode()}}]}}]}
        return type("R", (), {"status_code": 200, "json": lambda s: body})()


SCENES = ["Most people pay the minimum on their card and never notice how slowly the balance moves.",
          "As of November 2026, the average card rate was about twenty-two percent a year on balances.",
          "Pick one card, pay a fixed amount every month, and watch the interest shrink month by month.",
          "Small steps beat a perfect plan that never starts, so begin with the card that costs the most."]


def _n(tmp_path, http):
    return GeminiTTSNarrator("K", voice="Charon", session=http, cache_dir=tmp_path / "c",
                             ledger=SpendLedger(tmp_path / "s.json"), sleep=lambda s: None, target_wpm=158)


def test_every_scene_lands_at_158_wpm_whatever_the_raw_pace(tmp_path):
    n = _n(tmp_path, PacedGemini([138, 182, 150, 170]))       # real takes vary from scene to scene
    for text in SCENES:
        n.narrate(text)
    for info in n.pace_log:
        assert 152 <= info["wpm_after"] <= 164, n.pace_log
    assert [i["wpm_before"] for i in n.pace_log] == [138, 182, 150, 170]
    assert n.pace_log[0]["factor"] > 1.0 and n.pace_log[1]["factor"] < 1.0         # slow sped up, fast slowed


def test_factor_is_clamped(tmp_path):
    n = _n(tmp_path, PacedGemini([100, 260]))
    n.narrate(SCENES[0])
    n.narrate(SCENES[1])
    assert n.pace_log[0]["factor"] == 1.2 and n.pace_log[1]["factor"] == 0.85


def test_slow_guard_runs_before_correction(tmp_path):
    http = PacedGemini([60, 60])                    # 60 wpm: atempo could "fix" it, but it must be HELD instead
    with pytest.raises(VoiceUnavailable, match="abnormally slow"):
        _n(tmp_path, http).narrate(SCENES[0])
    assert http.k == 2


def test_shorts_boost_applies_on_top(tmp_path):
    n = _n(tmp_path, PacedGemini([158]))
    n.boost = 1.1
    out = n.narrate(SCENES[2])
    assert n.pace_log[0]["boost"] == 1.1 and spoken_wpm(SCENES[2], out.audio) > 164


def test_short_scenes_use_the_median_correction(tmp_path):
    n = _n(tmp_path, PacedGemini([140, 140, 300]))
    n.narrate(SCENES[0])
    n.narrate(SCENES[1])
    n.narrate("Here's the catch.")                 # 3 words: its own measure is unreliable
    f = sorted(x["factor"] for x in n.pace_log[:2])
    assert n.pace_log[2]["factor"] == pytest.approx(f[1], abs=0.002)


def test_voice_test_passes_only_after_correction_in_150_166(settings, tmp_path, monkeypatch):
    from dataclasses import replace

    from glivarao.tts import voice_test

    s = replace(settings, gemini_api_key="K", tts_cache_dir=str(tmp_path / "c"),
                tts_spend_ledger_path=str(tmp_path / "l.json"), output_dir=tmp_path / "out")
    monkeypatch.setattr("glivarao.tts.gemini_tts.requests.Session", lambda: PacedGemini([135, 175, 148]))
    res = voice_test.run(s)
    assert (voice_test.LOW, voice_test.HIGH) == (150.0, 166.0)
    assert all(r["ok"] and 150 <= r["wpm"] <= 166 for r in res), res
    assert [r["wpm_before"] for r in res] == [135, 175, 148]
