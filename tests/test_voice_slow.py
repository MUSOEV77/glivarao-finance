"""'Abnormally slow' voice: Gemini sometimes reads the style instruction aloud. The scene is re-requested with the
transcript clearly marked (same voice + style); pauses and spelled-out numbers don't count as slow speech; tiny
scenes are merged; a held video names the scene. All HTTP simulated."""
import base64

import numpy as np
import pytest

from glivarao.tts.gemini_tts import (GeminiTTSNarrator, SpendLedger, active_speech_seconds, spoken_words,
                                     spoken_wpm)
from glivarao.tts.voice_lock import VoiceUnavailable


def _speech(seconds, pauses=()):
    sr = 24000
    a = (0.3 * np.sin(np.linspace(0, 2 * np.pi * 150 * seconds, int(seconds * sr)))).astype(np.float32)
    for start, length in pauses:
        a[int(start * sr):int((start + length) * sr)] = 0
    return a


class ReadsStyleAloud:
    """Like the real failure: without a clearly marked transcript the model also speaks the ~50-word style text."""

    def __init__(self, always=False):
        self.prompts, self.always = [], always

    def post(self, url, headers=None, json=None, timeout=None):
        prompt = json["contents"][0]["parts"][0]["text"]
        self.prompts.append(prompt)
        text = prompt.split("TRANSCRIPT:\n")[-1] if "TRANSCRIPT:" in prompt else prompt
        words = len(text.split()) if ("TRANSCRIPT:" in prompt and not self.always) else len(prompt.split())
        sec = words / 170 * 60
        pcm = (_speech(sec) * 32767).astype("<i2")
        body = {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;rate=24000", "data": base64.b64encode(pcm.tobytes()).decode()}}]}}]}
        return type("R", (), {"status_code": 200, "json": lambda s: body})()


SCENE = "Pay just the minimum on that card and the interest quietly snowballs for years."   # 14 words
STYLE = ("Narrate as a confident, upbeat American male YouTube finance host talking to a friend: warm, energetic and "
         "clear; numbers and money amounts spoken crisply; trustworthy, never theatrical. Fast, upbeat, energetic "
         "delivery at about 170 words per minute, like a popular YouTube finance explainer.")


def test_style_read_aloud_is_fixed_by_the_strict_transcript_request(tmp_path):
    http = ReadsStyleAloud()
    n = GeminiTTSNarrator("K", voice="Charon", style=STYLE, session=http, cache_dir=tmp_path / "c",
                          ledger=SpendLedger(tmp_path / "s.json"), sleep=lambda s: None).narrate(SCENE)
    assert len(http.prompts) == 2 and "TRANSCRIPT:" in http.prompts[1] and http.prompts[1].startswith(STYLE)
    assert n.duration < 8                                          # the scene alone, not the instructions
    assert (tmp_path / "voice_debug").exists()                     # the rejected first clip is kept for inspection


def test_held_message_names_the_scene(tmp_path):
    with pytest.raises(VoiceUnavailable, match="Pay just the minimum"):
        GeminiTTSNarrator("K", voice="Charon", style=STYLE, session=ReadsStyleAloud(always=True),
                          cache_dir=tmp_path / "c", ledger=SpendLedger(tmp_path / "s.json"),
                          sleep=lambda s: None).narrate(SCENE)


def test_pauses_and_spelled_out_numbers_are_not_slow_speech():
    assert spoken_words("$1,368.5 billion") >= 8 and spoken_words("22.36%") >= 5
    a = _speech(8.0, pauses=[(2.0, 1.5), (5.0, 1.2)])               # 8 s with 2.7 s of pauses
    assert active_speech_seconds(a) == pytest.approx(5.3, abs=0.15)
    text = "As of November 2026, the average card rate was 22.36%, on $1,368.5 billion owed."
    assert spoken_wpm(text, _speech(9.0)) > 90                      # numbers take time to say: not "slow"


def test_short_scenes_are_not_checked_and_tiny_scenes_are_merged(tmp_path):
    from glivarao.content.short_fit import merge_tiny_scenes
    from glivarao.models import Scene, Script

    n = GeminiTTSNarrator("K", style=STYLE, session=ReadsStyleAloud(always=True), cache_dir=tmp_path / "c",
                          ledger=SpendLedger(tmp_path / "s.json"), sleep=lambda s: None).narrate("Here's the catch.")
    assert n.duration > 0                                           # 3 words: never held for "slow"
    sc = [Scene(heading="Hook", narration="Credit cards can trap you for years if you only pay the minimum."),
          Scene(heading="Wait", narration="Here's why."),
          Scene(heading="Math", narration="Interest is charged on the balance every single month you carry it."),
          Scene(heading="End", narration="This video is for education only and isn't financial advice.")]
    s = merge_tiny_scenes(Script(format="short", topic="t", title="t", description="", thumbnail_text="", scenes=sc))
    assert len(s.scenes) == 3 and s.scenes[0].narration.endswith("Here's why.")
