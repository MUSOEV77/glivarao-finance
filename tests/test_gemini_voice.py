"""Gemini TTS, the locked channel voice: all HTTP simulated; no paid call is ever made."""
import base64
from dataclasses import replace

import numpy as np
import pytest

from glivarao.config import Settings
from glivarao.tts.gemini_tts import API, GeminiTTSNarrator, SpendLedger, split_by_pauses
from glivarao.tts.voice_lock import VoiceUnavailable
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
    """status: one HTTP status for every call, or a list consumed call by call (last one repeats)."""

    def __init__(self, status=200, tokens=800):
        self.calls, self.status, self.tokens = [], status, tokens

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        st = self.status
        if isinstance(st, list):
            st = st[min(len(self.calls), len(st)) - 1]
        if st != 200:
            return type("R", (), {"status_code": st, "headers": {}, "json": lambda s: {}})()
        pcm = (speech_with_gaps() * 32767).astype("<i2").tobytes()
        body = {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}],
            "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": self.tokens}}
        return type("R", (), {"status_code": 200, "json": lambda s: body})()


def narrator(tmp_path, session, **kw):
    kw.setdefault("sleep", lambda s: None)
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
    assert prompt.startswith("Say in a warm, confident, upbeat voice: ")          # short direction only
    assert "documentary narrator" not in prompt and "Gli-VAR-oh" in prompt and "GLIVARAO" not in prompt
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
    with pytest.raises(VoiceUnavailable, match="monthly voice budget"):
        narrator(tmp_path, FakeGemini(), monthly_budget_usd=20).narrate("A sentence that costs money to speak aloud.")
    g = FakeGemini(status=429)
    waits = []
    with pytest.raises(VoiceUnavailable) as e:
        narrator(tmp_path / "x", g, sleep=waits.append).narrate("Hello there.")
    assert "GKEY-1" not in str(e.value) and len(g.calls) == 6          # 1 try + 5 retries
    assert [round(w) for w in waits] == [5, 10, 20, 40, 80] or all(a < b for a, b in zip(waits, waits[1:]))


def test_backoff_recovers_from_temporary_errors_and_stops_on_permanent_ones(tmp_path):
    g = FakeGemini(status=[503, 429, 200])
    n = narrator(tmp_path, g).narrate("Hello there. Second sentence.")
    assert len(g.calls) == 3 and n.duration > 0
    g404 = FakeGemini(status=404)
    with pytest.raises(VoiceUnavailable, match="model was not found"):
        narrator(tmp_path / "y", g404).narrate("Hello there.")
    assert len(g404.calls) == 1                                       # no pointless retries


def test_unpinned_models_are_refused(tmp_path):
    for bad in ("gemini-flash-latest", "gemini-3.1-flash-tts-preview", "gemini-2.0-flash-exp"):
        with pytest.raises(VoiceUnavailable, match="not a pinned"):
            narrator(tmp_path, FakeGemini(), model=bad)


def test_split_by_pauses_falls_back_to_proportional():
    audio = speech_with_gaps(3)
    spans = split_by_pauses(audio, ["a" * 10, "b" * 10, "c" * 10])
    assert spans[0][0] == 0 and abs(spans[0][1] - 1.0) < 0.05 and abs(spans[1][0] - 1.35) < 0.05
    solid = (0.3 * np.ones(SR * 3)).astype(np.float32)  # no gaps -> proportional
    spans = split_by_pauses(solid, ["x" * 10, "y" * 20])
    assert abs(spans[0][1] - 1.0) < 0.01


def locked(tmp_path, **kw):
    return replace(Settings(tts_provider="gemini_tts", allow_paid_apis=True, gemini_api_key="K",
                            tts_cache_dir=str(tmp_path / "c"), tts_spend_ledger_path=str(tmp_path / "s.json"),
                            db_path=tmp_path / "db.sqlite3", tts_monthly_budget_usd=20, gemini_tts_price=18), **kw)


def test_no_fallback_voice_ever(tmp_path):
    from glivarao.storage import JobStore
    from glivarao.tts.narrator import narrate_all

    base = locked(tmp_path)
    store = JobStore(base.db_path)
    script = "\n\n".join(["This scene has a fair number of words in it for estimating cost."] * 40)
    ok = get_narrator(base, script, session=FakeGemini(), store=store)
    assert ok.provider == "gemini_tts" and ok.narrator.model == "gemini-3.8-flash-tts" and ok.voice == "Charon"
    SpendLedger(tmp_path / "s.json").add(19.95, 0)  # nearly at the cap: no cheaper model, no Kokoro
    with pytest.raises(VoiceUnavailable, match="budget"):
        get_narrator(base, script, session=FakeGemini(), store=store)
    with pytest.raises(VoiceUnavailable, match="ALLOW_PAID_APIS"):
        get_narrator(replace(base, allow_paid_apis=False), script, store=store)
    with pytest.raises(VoiceUnavailable, match="GEMINI_API_KEY"):
        get_narrator(replace(base, gemini_api_key=""), script, store=store)
    down = get_narrator(locked(tmp_path / "d"), "Hi.", session=FakeGemini(status=503), store=store,
                        sleep=lambda s: None)
    with pytest.raises(VoiceUnavailable):
        narrate_all(down, ["First scene.", "Second scene."], base)


def test_voice_settings_are_locked_after_first_use(tmp_path):
    from glivarao.storage import JobStore
    from glivarao.tts import voice_lock

    store = JobStore(tmp_path / "db.sqlite3")
    s = locked(tmp_path)
    get_narrator(s, "Hi.", session=FakeGemini(), store=store)            # records the lock
    for change in ({"gemini_tts_voice": "Puck"}, {"gemini_tts_pace": "brisk"},
                   {"gemini_tts_style": "Read cheerfully."}, {"gemini_tts_model": "gemini-3.8-flash-lite-tts"}):
        with pytest.raises(VoiceUnavailable, match="voice settings changed"):
            get_narrator(replace(s, **change), "Hi.", session=FakeGemini(), store=store)
    with pytest.raises(VoiceUnavailable, match="must be one of"):
        voice_lock.style_prompt(replace(s, gemini_tts_pace="fast"))
    voice_lock.reset(replace(s, gemini_tts_pace="slow"), store)           # an intentional change
    assert get_narrator(replace(s, gemini_tts_pace="slow"), "Hi.", session=FakeGemini(), store=store).voice == "Charon"
    g = FakeGemini()
    n = get_narrator(replace(s, gemini_tts_pace="slow"), "Hi.", session=g, store=store)
    n.narrator.narrate("Hello there.")
    assert "Slow, deliberate pace" not in g.calls[0]["json"]["contents"][0]["parts"][0]["text"]   # never sent
