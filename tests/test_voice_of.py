"""voice-of finds the exact voice/style/speed of a past job from the voice cache; voice-lock-from locks it."""
import json
from dataclasses import replace

import numpy as np
import soundfile as sf

from glivarao.content.brief import build_brief
from glivarao.content.format_writer import write_shorts_format
from glivarao.tts import voice_lock
from glivarao.tts.gemini_tts import KOKORO_SR, GeminiTTSNarrator, SpendLedger
from glivarao.tts.voice_of import find_jobs, identify, lock_from
from tests.test_authenticity import DAY
from tests.test_content_audio_daily import card


class SpeechFake:
    """Fake Gemini TTS: speech-like audio sized to the text (~160 wpm) with pauses."""

    def post(self, url, headers=None, json=None, timeout=None):
        import base64
        text = json["contents"][0]["parts"][0]["text"].split("\n\n", 1)[-1]
        sec = max(1.0, len(text.split()) / 160 * 60)
        t = np.linspace(0, sec, int(sec * 24000))
        pcm = (0.3 * np.sin(2 * np.pi * 180 * t) * 32767).astype("<i2")
        body = {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;rate=24000", "data": base64.b64encode(pcm.tobytes()).decode()}}]}}]}
        return type("R", (), {"status_code": 200, "json": lambda s: body})()


def test_voice_of_finds_exact_voice_style_speed_and_locks_it(settings, store, tmp_path):
    s = replace(settings, tts_provider="gemini_tts", tts_cache_dir=str(tmp_path / "cache"),
                gemini_tts_voice="Puck", gemini_tts_pace="energetic", gemini_tts_style=voice_lock.ENERGETIC_STYLE)
    sh = write_shorts_format(build_brief(card("credit_report", "Credit reports and credit report errors"), DAY),
                             "explainer", n=1)[0]
    job = store.create("short", "Credit reports and credit report errors")
    out = s.output_dir / job.id
    out.mkdir(parents=True)
    job.script_path, job.video_path, job.duration_sec = str(out / "script.json"), str(out / "video.mp4"), 66.0
    (out / "script.json").write_text(sh.model_dump_json())
    store.save(job)
    n = GeminiTTSNarrator("K", voice="Puck", style=voice_lock.style_prompt(s), cache_dir=tmp_path / "cache",
                          ledger=SpendLedger(tmp_path / "sp.json"), session=SpeechFake(), speed=1.15)
    audio = np.concatenate([n.narrate(sc.narration).audio for sc in sh.scenes])
    sf.write(out / "narration_kokoro.wav", audio, KOKORO_SR)
    # the .env now says something else (e.g. Charon): the job's own voice must still be found
    now = replace(s, gemini_tts_voice="Charon", gemini_tts_pace="measured")
    assert [j.id for j in find_jobs(store, "credit report", "short")] == [job.id]      # today, by topic
    info = identify(now, store.get(job.id))
    assert info["voice"] == "Puck" and info["pace"] == "energetic" and info["style"] == voice_lock.ENERGETIC_STYLE
    assert info["speed"] == 1.15 and info["how"].startswith("matched") and info["scenes_matched"].split("/")[0] == \
        info["scenes_matched"].split("/")[1]
    env = tmp_path / ".env"
    env.write_text("GEMINI_TTS_VOICE=Charon\n")
    vals = lock_from(now, store, job.id, env_path=env)
    assert vals["GEMINI_TTS_VOICE"] == "Puck" and "GEMINI_TTS_SPEED=1.15" in env.read_text()
    locked = replace(now, gemini_tts_voice="Puck", gemini_tts_pace="energetic", gemini_tts_speed=1.15,
                     gemini_tts_style=voice_lock.ENERGETIC_STYLE)
    assert voice_lock.verify(locked, store)["voice"] == "Puck"
    assert json.loads(store.kv_get("voice_locked_from"))["job"] == job.id


def test_voice_of_cli_prints_time_title_and_settings(settings, store, monkeypatch, capsys, tmp_path):
    from glivarao import __main__ as cli
    from glivarao.models import JobStatus

    s = replace(settings, tts_cache_dir=str(tmp_path / "c"))
    monkeypatch.setattr(cli, "get_settings", lambda: s)
    sh = write_shorts_format(build_brief(card("credit_report", "Credit reports and credit report errors"), DAY),
                             "explainer", n=1)[0]
    job = store.create("short", "Credit reports and credit report errors")
    out = s.output_dir / job.id
    out.mkdir(parents=True)
    job.script_path, job.video_path, job.duration_sec = str(out / "script.json"), str(out / "video.mp4"), 66.0
    (out / "script.json").write_text(sh.model_dump_json())
    (out / "metadata.json").write_text(json.dumps({"title": "Blindly trusting your report", "tts": {
        "voice": "Puck", "model": "gemini-3.8-flash-tts", "pace": "energetic", "style": "x", "speed": 1.15}}))
    store.save(job)
    for st in (JobStatus.SCRIPTED, JobStatus.RENDERED, JobStatus.PENDING_APPROVAL):
        store.transition(store.get(job.id), st, "t")
    cli.main(["voice-of", "--find", "credit report", "--short"])
    o = capsys.readouterr().out
    assert "1:06" in o and "sent" in o and "Tashkent" in o and "Blindly trusting your report" in o
    assert "Puck" in o and "1.15" in o and "recorded in metadata.json" in o
