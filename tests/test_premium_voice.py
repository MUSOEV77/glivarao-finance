"""Premium voice (Google Chirp 3 HD) integration: all HTTP is simulated; no paid call is ever made."""
import base64
import io
from dataclasses import replace

import numpy as np
import pytest
import soundfile as sf

from glivarao.config import Settings
from glivarao.tts.google_chirp import (API, BudgetExceeded, GoogleChirpNarrator, PaidTTSError, UsageLedger,
                                       billable_text, monthly_char_limit)
from glivarao.tts.kokoro import MODEL
from glivarao.tts.narrator import get_narrator, narrate_all


def wav_b64(seconds=0.5, sr=24000):
    buf = io.BytesIO()
    sf.write(buf, (0.3 * np.sin(np.linspace(0, 900, int(seconds * sr)))).astype(np.float32), sr, format="WAV",
             subtype="PCM_16")
    return base64.b64encode(buf.getvalue()).decode()


class FakeGoogle:
    def __init__(self, status=200, reject_pronunciations=False):
        self.calls, self.status, self.reject = [], status, reject_pronunciations

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self.reject and "customPronunciations" in json["input"]:
            return type("R", (), {"status_code": 400, "json": lambda s: {}})()
        if self.status != 200:
            return type("R", (), {"status_code": self.status, "json": lambda s: {}})()
        return type("R", (), {"status_code": 200, "json": lambda s: {"audioContent": wav_b64()}})()


def narrator(tmp_path, session, limit=0):
    return GoogleChirpNarrator("KEY-123", cache_dir=tmp_path / "cache", ledger=UsageLedger(tmp_path / "ledger.json"),
                               char_limit=limit, session=session)


def test_request_format_and_key_in_header(tmp_path):
    g = FakeGoogle()
    n = narrator(tmp_path, g).narrate("This is GLIVARAO Finance. Is it worth it?")
    c = g.calls[0]
    assert c["url"] == API and "KEY-123" not in c["url"] and c["headers"] == {"X-Goog-Api-Key": "KEY-123"}
    assert c["json"]["voice"] == {"languageCode": "en-US", "name": "en-US-Chirp3-HD-Charon"}
    assert c["json"]["audioConfig"]["audioEncoding"] == "LINEAR16"
    assert c["json"]["input"]["customPronunciations"]["pronunciations"][0]["phrase"] == "GLIVARAO"
    assert [s.question for s in n.sentences] == [False, True] and n.sentences[0].end < n.sentences[1].start


def test_cache_prevents_paying_twice_and_ledger_counts(tmp_path):
    g = FakeGoogle()
    text = "Pay more than the minimum. Check every statement."
    a = narrator(tmp_path, g)
    a.narrate(text)
    billed = sum(len(x) for x in billable_text(text))
    assert a.billed_chars == billed and UsageLedger(tmp_path / "ledger.json").used() == billed
    b = narrator(tmp_path, g)
    b.narrate(text)  # same text again: served from cache
    assert len(g.calls) == 2 and b.billed_chars == 0


def test_monthly_cap_is_enforced(tmp_path):
    assert monthly_char_limit(20, 30, 0) == 666_666 and monthly_char_limit(20, 30, 1_000_000) == 1_666_666
    UsageLedger(tmp_path / "ledger.json").add(990)
    n = narrator(tmp_path, FakeGoogle(), limit=1000)
    with pytest.raises(BudgetExceeded):
        n.narrate("This sentence is longer than ten characters.")


def test_rejected_pronunciation_field_retries_plain_text(tmp_path):
    g = FakeGoogle(reject_pronunciations=True)
    narrator(tmp_path, g).narrate("Welcome to GLIVARAO Finance.")
    assert len(g.calls) == 2 and "customPronunciations" not in g.calls[1]["json"]["input"]


def test_api_error_never_leaks_key(tmp_path):
    with pytest.raises(PaidTTSError) as e:
        narrator(tmp_path, FakeGoogle(status=403)).narrate("Hello there.")
    assert "KEY-123" not in str(e.value)


@pytest.mark.parametrize("over", [dict(allow_paid_apis=False), dict(google_tts_api_key="")])
def test_paid_voice_requires_approval_and_key(tmp_path, over):
    s = replace(Settings(tts_provider="google_chirp", allow_paid_apis=True, google_tts_api_key="K",
                         tts_cache_dir=str(tmp_path / "c"), tts_ledger_path=str(tmp_path / "l.json")), **over)
    if not MODEL.exists():
        pytest.skip("Kokoro model not installed")
    choice = get_narrator(s, "Some text.", session=FakeGoogle())
    assert choice.provider == "kokoro" and choice.note and "backup" in choice.label


@pytest.mark.skipif(not MODEL.exists(), reason="Kokoro model not installed")
def test_budget_or_api_failure_falls_back_to_kokoro_for_whole_video(tmp_path):
    base = Settings(tts_provider="google_chirp", allow_paid_apis=True, google_tts_api_key="K",
                    tts_cache_dir=str(tmp_path / "c"), tts_ledger_path=str(tmp_path / "l.json"),
                    tts_monthly_budget_usd=0.00003, tts_price_per_million=30, tts_free_chars_per_month=0)
    choice = get_narrator(base, "A long script " * 20, session=FakeGoogle())
    assert choice.provider == "kokoro" and "cap" in choice.note            # would exceed the cap: backup
    ok = replace(base, tts_monthly_budget_usd=20)
    choice = get_narrator(ok, "Hello.", session=FakeGoogle(status=500))
    assert choice.provider == "google_chirp"
    narrations, final = narrate_all(choice, ["First scene.", "Second scene."], ok)
    assert final.provider == "kokoro" and "paid TTS error" in final.note and len(narrations) == 2
