"""Voice configuration: the channel voice is Gemini TTS "Charon" (locked, pinned model; Kokoro stays only as a
development engine), approved Kokoro voices only, no paid TTS without approval,
pronunciation lexicon, and mastering targets."""
import numpy as np
import pytest
import soundfile as sf

from glivarao.config import Settings
from glivarao.tts import TTSError, synthesize
from glivarao.tts.kokoro import APPROVED_VOICES, DEFAULT_VOICE, MODEL, KokoroEngine, VoiceNotApproved, normalize_text


def test_channel_voice_is_locked_gemini_charon():
    s = Settings()
    assert (s.tts_provider, s.gemini_tts_voice, s.gemini_tts_model, s.gemini_tts_pace) == (
        "gemini_tts", "Charon", "gemini-3.8-flash-tts", "measured")
    assert s.tts_monthly_budget_usd == 20 and s.tts_alert_ratio == 0.8
    assert DEFAULT_VOICE == "am_michael" and s.kokoro_voice == "am_michael"   # development engine only
    assert APPROVED_VOICES == {"am_michael": "primary", "am_fenrir": "backup", "am_puck": "backup"}


def test_unapproved_voice_refused():
    with pytest.raises(VoiceNotApproved):
        KokoroEngine.get("am_santa")


@pytest.mark.parametrize("provider", ["elevenlabs", "google"])
def test_paid_tts_needs_owner_approval(provider, tmp_path):
    s = Settings(mode="production", allow_paid_apis=False, elevenlabs_api_key="k", elevenlabs_voice_id="v",
                 google_tts_api_key="k")
    with pytest.raises(TTSError, match="paid service"):
        synthesize("hello", tmp_path / "x.wav", s, provider=provider)


def test_text_rules():
    assert normalize_text("Up 5% YoY, about 1/12 of the APR in the U.S. today") == \
        "Up 5% year over year, about one twelfth of the APR in the US today"


@pytest.mark.skipif(not MODEL.exists(), reason="Kokoro model not installed")
def test_brand_and_finance_words_have_explicit_pronunciations():
    e = KokoroEngine.get("am_michael")
    for word in ["GLIVARAO", "HELOC", "FINRA", "Equifax", "Experian", "Zelle", "Venmo", "Interac", "Klarna",
                 "Afterpay", "Schwab"]:
        e.unknown = []
        ph = e.phonemize(word)
        assert not e.unknown, word
        assert len(ph.split()) == 1, (word, ph)  # said as one word, not spelled letter by letter


def test_master_to_lufs_hits_targets(tmp_path):
    from glivarao.anim.audio import SR, master_to_lufs

    t = np.arange(SR * 8) / SR
    x = (0.05 * np.sin(2 * np.pi * 220 * t) * (1 + 0.5 * np.sin(2 * np.pi * 0.5 * t))).astype(np.float32)
    x[SR:SR + 50] = 0.99  # a sharp transient that would clip if gain were applied before limiting
    src = tmp_path / "in.wav"
    sf.write(src, x, SR, subtype="PCM_16")
    rep = master_to_lufs(src, tmp_path / "out.wav")
    assert abs(rep["after"]["lufs"] + 14) <= 0.5
    assert rep["after"]["true_peak"] <= -1.4
