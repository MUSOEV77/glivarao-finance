"""Voice audition: 5 labelled samples to Telegram with pick buttons; the pick locks name + speed + style in .env and
the voice lock, and held videos get re-voiced. Gemini and Telegram are simulated; nothing is paid."""
import json
from dataclasses import replace

import numpy as np
import pytest

from glivarao.studio import voice_audition as VA
from glivarao.tts import voice_lock
from glivarao.tts.gemini_tts import KOKORO_SR, GeminiTTSNarrator, SpendLedger, apply_tempo, words_per_minute
from tests.test_gemini_voice import FakeGemini
from tests.test_uploadpack import RecTG


@pytest.fixture
def vs(settings, tmp_path):
    return replace(settings, allow_paid_apis=True, gemini_api_key="K", tts_cache_dir=str(tmp_path / "c"),
                   tts_spend_ledger_path=str(tmp_path / "s.json"), telegram_bot_token="T",
                   telegram_approver_chat_id="42", tts_provider="gemini_tts")


def test_tempo_hits_target_pace():
    words = " ".join(["word"] * 25)
    a = (0.3 * np.sin(np.linspace(0, 2 * np.pi * 200 * 10, 10 * KOKORO_SR))).astype(np.float32)
    assert round(words_per_minute(words, a)) == 150
    assert 168 <= words_per_minute(words, apply_tempo(a, 170 / 150)) <= 172


def test_audition_sends_five_labelled_samples_with_buttons(vs, store, tmp_path):
    g = FakeGemini()
    res = VA.make_samples(vs, store, tmp_path / "aud", session=g)
    assert [r["voice"] for r in res] == ["Puck", "Sadachbia", "Fenrir", "Achird", "Charon"]
    assert all(r["path"].endswith(".mp3") for r in res)
    assert next(r for r in res if r["voice"] == "Charon")["speed"] == 1.15          # Charon: +15%
    voices = [c["json"]["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"]
              for c in g.calls]
    assert voices == ["Puck", "Sadachbia", "Fenrir", "Achird", "Charon"]
    sent = [c["json"]["contents"][0]["parts"][0]["text"] for c in g.calls]          # only the short direction
    assert all(t.startswith("Say in a warm, confident, upbeat voice: ") and "words per minute" not in t for t in sent)
    tg = RecTG()
    assert VA.send_samples(vs, res, tg) == 5
    audio = [p for m, p in tg.calls if m == "sendAudio"]
    assert len(audio) == 5 and "words/min" in audio[0]["caption"]
    assert audio[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "voicepick:Puck"


def test_pick_locks_voice_speed_style_and_requests_revoice(vs, store, tmp_path, monkeypatch):
    VA.make_samples(vs, store, tmp_path / "aud", session=FakeGemini())
    env = tmp_path / ".env"
    env.write_text("GEMINI_TTS_VOICE=Charon\nGEMINI_TTS_PACE=measured\nOTHER=1\n")
    voice_lock.reset(vs, store)                                                      # old Charon lock
    locked = VA.pick(vs, store, "fenrir", env_path=env)
    text = env.read_text()
    assert "GEMINI_TTS_VOICE=Fenrir" in text and "GEMINI_TTS_PACE=energetic" in text and "OTHER=1" in text
    assert f"GEMINI_TTS_SPEED={locked['GEMINI_TTS_SPEED']}" in text and "TTS_TARGET_WPM=170" in text
    assert oct(env.stat().st_mode)[-3:] == "600"
    new = replace(vs, gemini_tts_voice="Fenrir", gemini_tts_pace="energetic",
                  gemini_tts_style=voice_lock.ENERGETIC_STYLE, gemini_tts_speed=float(locked["GEMINI_TTS_SPEED"]))
    assert voice_lock.verify(new, store)["voice"] == "Fenrir"                      # new lock accepted
    with pytest.raises(voice_lock.VoiceUnavailable):
        voice_lock.verify(vs, store)                                                 # old settings refused
    assert store.kv_get("revoice_requested")
    with pytest.raises(ValueError):
        VA.pick(vs, store, "Kore", env_path=env)


def test_telegram_button_locks_voice(vs, store, tmp_path, monkeypatch):
    from glivarao.publish import telegram

    VA.make_samples(vs, store, tmp_path / "aud", session=FakeGemini())
    monkeypatch.setenv("ENV_FILE", str(tmp_path / ".env"))
    store.kv_set("voice_held", json.dumps({"20261120-short-1": {"since": "2026-11-20", "reason": "402"}}))
    ups = [{"update_id": 1, "callback_query": {"id": "a", "from": {"id": 42},
                                               "message": {"message_id": 3, "chat": {"id": 42}},
                                               "data": "voicepick:Achird"}}]

    class C(RecTG):
        def call(self, method, files=None, **params):
            return ups if method == "getUpdates" else super().call(method, files, **params)

    c = C()
    assert telegram.poll_decisions(store, vs, client=c) == [("Achird", "voice_locked")]
    assert "GEMINI_TTS_VOICE=Achird" in (tmp_path / ".env").read_text()
    assert any("Voice locked: Achird" in t and "1 video(s) on hold" in t for t in c.texts())


def test_narrator_applies_locked_speed(tmp_path):
    g = FakeGemini()
    kw = dict(cache_dir=tmp_path / "c", ledger=SpendLedger(tmp_path / "s.json"), session=g, sleep=lambda s: None)
    slow = GeminiTTSNarrator("K", **kw).narrate("One sentence here. And another. And a third.")
    fast = GeminiTTSNarrator("K", speed=1.2, **kw).narrate("One sentence here. And another. And a third.")
    assert len(g.calls) == 1                                    # same raw audio from the cache: no second charge
    assert fast.duration < slow.duration * 0.9
