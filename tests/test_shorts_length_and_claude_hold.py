"""Shorts never over 60 s (word cap, measured length, re-voice up to 2x, never sent if still long), Claude-only
writer that holds production and retries hourly, remake, and the slow-audio guard. All external calls simulated."""
import json
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from glivarao import daily_v2
from glivarao.content.brief import build_brief
from glivarao.content.format_writer import write_shorts_format
from glivarao.content.short_fit import trim_to_words, words_for
from glivarao.daily_v2 import render_and_review
from glivarao.models import JobStatus
from tests.test_authenticity import DAY
from tests.test_content_audio_daily import card


def a_short(words=300):
    b = build_brief(card(), DAY)
    sh = write_shorts_format(b, "explainer", n=1)[0]
    filler = " ".join(["This extra sentence keeps going on and on."] * (words // 8))
    scenes = list(sh.scenes)
    scenes[1] = scenes[1].model_copy(update={"narration": scenes[1].narration + " " + filler})
    return b, sh.model_copy(update={"scenes": scenes})


def test_trim_keeps_hook_and_close():
    _, sh = a_short(300)
    assert sh.word_count > 250
    t = trim_to_words(sh, 110)
    assert t.word_count <= 110 and t.scenes[0].narration == sh.scenes[0].narration
    assert t.scenes[-1].narration == sh.scenes[-1].narration
    assert words_for(144, 110, 50) == 38 or words_for(144, 110, 50) >= 40


def _render_stub(monkeypatch, durations):
    import glivarao.render.animated as anim
    import glivarao.render.thumbnail_editorial as te

    calls = []

    def fake_render(script, out, s, voice=None, workers=None):
        calls.append(script.word_count)
        out.mkdir(parents=True, exist_ok=True)
        (out / "video.mp4").write_bytes(b"0")
        (out / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n")
        d = durations[min(len(calls), len(durations)) - 1]
        return SimpleNamespace(video=out / "video.mp4", srt=out / "captions.srt", duration=d, render_seconds=1.0,
                               unknown_words=[], voice="Gemini TTS Puck", scene_starts=[0.0] * len(script.scenes))

    monkeypatch.setattr(anim, "render_animated", fake_render)
    monkeypatch.setattr(te, "make_thumbnail", lambda sc, dst, portrait=False, theme="": (dst.write_bytes(b"j"), dst)[1])
    return calls


def _job(store, settings, sh, b):
    job = store.create("short", "Identity theft")
    out = settings.output_dir / job.id
    out.mkdir(parents=True)
    job.script_path = str(out / "script.json")
    (out / "script.json").write_text(sh.model_dump_json())
    (out / "brief.json").write_text(b.to_json())
    store.transition(job, JobStatus.SCRIPTED, "t")
    return store.get(job.id)


CTX = {"writer": "claude", "creator": "", "item_id": None, "date": DAY.isoformat(), "compliance": "ok",
       "sim": {"summary": "ok", "phrase_overlap": 0.0, "structure_ratio": 0.0}}


def test_long_short_is_capped_then_reshortened_and_shows_length(settings, store, monkeypatch):
    b, sh = a_short(300)
    calls = _render_stub(monkeypatch, [64.0, 49.0])
    sent = {}
    monkeypatch.setattr("glivarao.publish.telegram.request_approval",
                        lambda job, st, s, script, checks, **kw: (sent.update(checks=checks),
                                                                 st.transition(job, JobStatus.PENDING_APPROVAL, "t")))
    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42")
    r = render_and_review(_job(store, s, sh, b), sh, b, [], dict(CTX), s, store, True, 1)
    assert calls[0] <= 110 and len(calls) == 2 and calls[1] < calls[0]     # capped, then trimmed + re-voiced
    assert r[2] == "pending_approval" and "LENGTH: 0:49" in sent["checks"] and "limit 0:60" in sent["checks"]


def test_short_still_over_60s_is_never_sent(settings, store, monkeypatch):
    b, sh = a_short(300)
    calls = _render_stub(monkeypatch, [144.0, 120.0, 95.0])
    alerts = []
    monkeypatch.setattr(daily_v2, "_notify", lambda s, t: alerts.append(t))
    monkeypatch.setattr("glivarao.publish.telegram.request_approval", lambda *a, **k: pytest.fail("sent!"))
    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42")
    job = _job(store, s, sh, b)
    r = render_and_review(job, sh, b, [], dict(CTX), s, store, True, 1)
    assert len(calls) == 3 and r[2] == "failed" and store.get(job.id).status == JobStatus.FAILED
    assert "NOT sent" in alerts[0] and "remake" in alerts[0]


def test_claude_only_holds_production_and_resumes_hourly(settings, store, monkeypatch, tmp_path):
    from glivarao.scriptgen import claude as C
    from tests.test_authenticity import _stub_render

    _stub_render(monkeypatch)
    alerts = []
    monkeypatch.setattr(daily_v2, "_notify", lambda s, t: alerts.append(t))
    state = {"down": True}

    def ask(settings_, prompt, fmt, client=None, ledger=None):
        if state["down"]:
            raise C.ClaudeUnavailable("RateLimitError: 429 quota exceeded")
        from tests.test_production_hardening import script_json
        return json.loads(script_json(25, 112) if fmt == "long" else script_json(4, 25))

    monkeypatch.setattr(C, "_ask", ask)
    s = replace(settings, allow_paid_apis=True, writer="claude_vertex", writer_fallback="none",
                creator_input_wait_hours=0)
    rdir = tmp_path / "r"
    rdir.mkdir()
    (rdir / f"{DAY}.json").write_text(json.dumps({"ranked": [dict(card(), rank=1)]}))
    res = daily_v2.run_daily_v2(s, store, today=DAY, research_dir=rdir, send=True)
    assert res.jobs == [] and "held: waiting for Claude" in res.note
    assert daily_v2.writer_held(store)["reason"].startswith("RateLimitError")
    daily_v2.run_daily_v2(s, store, today=DAY, research_dir=rdir, send=True)
    assert sum("Claude can't write" in a for a in alerts) == 1                      # one alert per day
    state["down"] = False
    res = daily_v2.run_daily_v2(s, store, today=DAY, research_dir=rdir, send=True)
    assert res.jobs and daily_v2.writer_held(store) == {} and any("Claude is writing again" in a for a in alerts)


def test_remake_replaces_a_bad_video(settings, store, monkeypatch):
    b, sh = a_short(300)
    _render_stub(monkeypatch, [45.0])
    old = _job(store, settings, sh, b)
    for st in (JobStatus.RENDERED, JobStatus.PENDING_APPROVAL):
        store.transition(old, st, "t")
    r = daily_v2.remake_video(settings, store, old.id, send=False)
    assert r[0] != old.id and r[2] == "rendered" and store.get(old.id).status == JobStatus.REJECTED
    approved = _job(store, settings, sh, b)
    for st in (JobStatus.RENDERED, JobStatus.PENDING_APPROVAL, JobStatus.APPROVED):
        store.transition(approved, st, "t")
    with pytest.raises(ValueError, match="already approved"):          # approved videos are never remade
        daily_v2.remake_video(settings, store, approved.id, send=False)


def test_abnormally_slow_tts_is_requested_again(tmp_path):
    import base64

    from glivarao.tts.gemini_tts import GeminiTTSNarrator, SpendLedger
    from glivarao.tts.voice_lock import VoiceUnavailable

    class SlowThenOK:
        def __init__(self, seconds):
            self.seconds, self.calls = list(seconds), 0

        def post(self, url, headers=None, json=None, timeout=None):
            self.calls += 1
            sec = self.seconds.pop(0) if self.seconds else 10
            pcm = (0.3 * np.sin(np.linspace(0, 2 * np.pi * 150 * sec, int(sec * 24000))) * 32767).astype("<i2")
            body = {"candidates": [{"content": {"parts": [{"inlineData": {
                "mimeType": "audio/L16;rate=24000", "data": base64.b64encode(pcm.tobytes()).decode()}}]}}]}
            return type("R", (), {"status_code": 200, "json": lambda s: body})()

    text = "This scene has exactly twenty words in it so that the words per minute check can see the speech rate."
    kw = dict(cache_dir=tmp_path / "c", ledger=SpendLedger(tmp_path / "s.json"), sleep=lambda s: None)
    http = SlowThenOK([60, 7])                          # first answer: 60 s for 20 words (20 wpm) -> asked again
    n = GeminiTTSNarrator("K", session=http, **kw).narrate(text)
    assert http.calls == 2 and n.duration < 10
    with pytest.raises(VoiceUnavailable, match="abnormally slow"):
        GeminiTTSNarrator("K", session=SlowThenOK([60, 60]), cache_dir=tmp_path / "c2",
                          ledger=SpendLedger(tmp_path / "s2.json"), sleep=lambda s: None).narrate(text)


def test_fallback_writer_setting_and_production_never_uses_templates(settings, store, monkeypatch):
    from glivarao.config import Settings

    monkeypatch.setenv("FALLBACK_WRITER", "off")
    assert Settings().writer_fallback == "none"
    monkeypatch.setenv("FALLBACK_WRITER", "gemini")
    assert Settings().writer_fallback == "gemini"
    monkeypatch.delenv("FALLBACK_WRITER")
    monkeypatch.delenv("WRITER_FALLBACK", raising=False)
    assert Settings().writer_fallback == "none"                      # default: off
    alerts = []
    monkeypatch.setattr(daily_v2, "_notify", lambda s, t: alerts.append(t))
    prod = replace(settings, mode="production", allow_paid_apis=False, writer="claude_vertex")
    res = daily_v2.run_daily_v2(prod, store, today=DAY, send=True)
    assert res.jobs == [] and "ALLOW_PAID_APIS" in res.note and len(alerts) == 1


def test_claude_quota_status_reads_limits_and_requests(settings, tmp_path):
    from glivarao.scriptgen import vertex_quota as VQ

    class R:
        def __init__(self, body, status=200):
            self._b, self.status_code, self.text = body, status, str(body)

        def json(self):
            return self._b

    class Http:
        def get(self, url, params=None, timeout=None):
            if url.endswith("/quotaInfos"):
                return R({"quotaInfos": [{"metric": "aiplatform.googleapis.com/global_online_prediction_requests_per_base_model",
                                          "dimensionsInfos": [{"dimensions": {"base_model": "anthropic-claude-sonnet"},
                                                               "details": {"value": "0"}}]}]})
            return R({"quotaPreferences": [{"name": "projects/p/locations/global/quotaPreferences/glivarao-sonnet-global-requests",
                                            "quotaId": "GlobalOnlinePredictionRequestsPerMinutePerProjectPerBaseModel",
                                            "quotaConfig": {"preferredValue": "10"}, "reconciling": True}]})

    s = replace(settings, vertex_project_id="proj-1", vertex_region="global")
    lines = VQ.quota_status(s, session=Http())
    assert any("requests" in ln and " 0" in ln for ln in lines)
    assert any("glivarao-sonnet-global-requests" in ln and "PENDING" in ln for ln in lines)

    class Denied(Http):
        def get(self, url, params=None, timeout=None):
            return R({"error": "denied"}, 403)

    assert any("roles/cloudquotas.viewer" in ln for ln in VQ.quota_status(s, session=Denied()))
