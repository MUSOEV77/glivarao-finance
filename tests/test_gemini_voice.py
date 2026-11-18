"""Gemini TTS (selected premium voice): all HTTP simulated; no paid call is ever made."""
import base64
from dataclasses import replace

import numpy as np
import pytest

from glivarao.config import Settings
from glivarao.tts.gemini_tts import API, GeminiTTSNarrator, PaidTTSError, SpendLedger, split_by_pauses
from glivarao.tts.kokoro import MODEL
from glivarao.tts.narrator import get_narrator

SR = 24000


def speech_with_gaps(n_sentences=3, seconds=1.0, gap=0.35):
    parts = []
    for k in range(n_sentences):
        parts.append((0.3 * np.sin(np.linspace(0, 2 * np.pi * 180 * seconds, int(seconds * SR)))).astype(np.float32))
        if k < n_sentences - 1:
            parts.append(np.zeros(int(gap * SR), np.float32))
    return np.concatenate(parts)


class FakeGemini:
    def __init__(self, status=200, tokens=800):
        self.calls, self.status, self.tokens = [], status, tokens

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self.status != 200:
            return type("R", (), {"status_code": self.status, "json": lambda s: {}})()
        pcm = (speech_with_gaps() * 32767).astype("<i2").tobytes()
        body = {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}],
            "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": self.tokens}}
        return type("R", (), {"status_code": 200, "json": lambda s: body})()


def narrator(tmp_path, session, **kw):
    return GeminiTTSNarrator("GKEY-1", cache_dir=tmp_path / "c", ledger=SpendLedger(tmp_path / "spend.json"),
                             session=session, **kw)


def test_request_format_voice_and_header(tmp_path):
    g = FakeGemini()
    n = narrator(tmp_path, g).narrate("Welcome to GLIVARAO Finance. Pay more than the minimum. Is it worth it?")
    c = g.calls[0]
    assert c["url"] == API.format(model="gemini-3.8-flash-tts") and "GKEY-1" not in c["url"]
    assert c["headers"] == {"x-goog-api-key": "GKEY-1"}
    cfg = c["json"]["generationConfig"]
    assert cfg["responseModalities"] == ["AUDIO"]
    assert cfg["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Charon"
    prompt = c["json"]["contents"][0]["parts"][0]["text"]
    assert "documentary narrator" in prompt and "Gli-VAR-oh" in prompt and "GLIVARAO" not in prompt
    assert len(n.sentences) == 3 and n.sentences[2].question
    assert all(a.end <= b.start for a, b in zip(n.sentences, n.sentences[1:]))  # boundaries found in the pauses


def test_spend_recorded_from_usage_and_cache_prevents_rebilling(tmp_path):
    g = FakeGemini(tokens=1000)
    a = narrator(tmp_path, g, price_per_m_audio=18.0)
    a.narrate("One sentence here. And another one.")
    assert a.spent_usd == pytest.approx(1000 * 18 / 1e6)
    assert SpendLedger(tmp_path / "spend.json").spent() == pytest.approx(0.018)
    b = narrator(tmp_path, g, price_per_m_audio=18.0)
    b.narrate("One sentence here. And another one.")
    assert len(g.calls) == 1 and b.spent_usd == 0


def test_hard_budget_and_errors(tmp_path):
    SpendLedger(tmp_path / "spend.json").add(19.999, 0)
    with pytest.raises(PaidTTSError):  # BudgetExceeded is a PaidTTSError
        narrator(tmp_path, FakeGemini(), monthly_budget_usd=20).narrate("A sentence that costs money to speak aloud.")
    with pytest.raises(PaidTTSError) as e:
        narrator(tmp_path / "x", FakeGemini(status=429)).narrate("Hello there.")
    assert "GKEY-1" not in str(e.value)


def test_split_by_pauses_falls_back_to_proportional():
    audio = speech_with_gaps(3)
    spans = split_by_pauses(audio, ["a" * 10, "b" * 10, "c" * 10])
    assert spans[0][0] == 0 and abs(spans[0][1] - 1.0) < 0.05 and abs(spans[1][0] - 1.35) < 0.05
    solid = (0.3 * np.ones(SR * 3)).astype(np.float32)  # no gaps -> proportional
    spans = split_by_pauses(solid, ["x" * 10, "y" * 20])
    assert abs(spans[0][1] - 1.0) < 0.01


@pytest.mark.skipif(not MODEL.exists(), reason="Kokoro model not installed")
def test_fallback_chain_same_voice_then_kokoro(tmp_path):
    base = Settings(tts_provider="gemini_tts", allow_paid_apis=True, gemini_api_key="K",
                    tts_cache_dir=str(tmp_path / "c"), tts_spend_ledger_path=str(tmp_path / "s.json"),
                    tts_monthly_budget_usd=20, gemini_tts_price=18, gemini_tts_fallback_price=6)
    script = "\n\n".join(["This scene has a fair number of words in it for estimating cost."] * 40)
    assert get_narrator(base, script, session=FakeGemini()).narrator.model == "gemini-3.8-flash-tts"
    SpendLedger(tmp_path / "s.json").add(19.95, 0)  # nearly at the cap
    tight = get_narrator(base, script, session=FakeGemini())
    assert tight.provider == "gemini_tts" and tight.narrator.model == "gemini-3.8-flash-lite-tts"
    assert tight.voice == "Charon"  # same narrator voice on the cheaper model
    SpendLedger(tmp_path / "s.json").add(0.05, 0)  # at the cap
    assert get_narrator(base, script, session=FakeGemini()).provider == "kokoro"
    off = replace(base, allow_paid_apis=False)
    assert get_narrator(off, script).provider == "kokoro"
