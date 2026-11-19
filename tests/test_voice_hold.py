"""Locked voice in production: if Gemini "Charon" is unavailable the video is HELD (never another voice), retried
later, released with its review; Telegram alerts on hold, on release, and at 80% / 100% of the voice budget."""
import json
from dataclasses import replace
from types import SimpleNamespace

from glivarao import daily_v2
from glivarao.daily_v2 import held_videos, retry_held_videos, run_daily_v2
from glivarao.models import JobStatus
from glivarao.studio.queue import TopicQueue
from glivarao.tts.gemini_tts import SpendLedger
from glivarao.tts.voice_lock import VoiceUnavailable
from tests.test_authenticity import DAY, TAKE, _stub_render
from tests.test_content_audio_daily import card


def _setup(settings, store, tmp_path, monkeypatch):
    _stub_render(monkeypatch)
    import glivarao.render.animated as anim

    ok_render = anim.render_animated
    state = {"down": True}

    def render(script, out, s, voice=None, workers=None):
        if state["down"]:
            raise VoiceUnavailable("Gemini TTS unavailable after 6 attempts (HTTP 503)")
        r = ok_render(script, out, s, voice, workers)
        r.voice = "Gemini TTS (gemini-3.8-flash-tts) Charon"
        return r

    monkeypatch.setattr(anim, "render_animated", render)
    alerts = []
    monkeypatch.setattr(daily_v2, "_notify", lambda s, text: alerts.append(text))
    s = replace(settings, topic_mode="queue", min_days_between_long=2)
    q = TopicQueue(store)
    it = q.add_proposals([card()], DAY)[0]
    q.pick(it.id, "case_study")
    q.add_input(it.id, TAKE)
    rdir = tmp_path / "r"
    rdir.mkdir()
    return s, state, alerts, rdir


def test_voice_outage_holds_videos_then_releases_them(settings, store, tmp_path, monkeypatch):
    s, state, alerts, rdir = _setup(settings, store, tmp_path, monkeypatch)
    res = run_daily_v2(s, store, today=DAY, research_dir=rdir, send=True)
    assert [j[2] for j in res.jobs] == ["held"] * 4                       # nothing narrated by another voice
    assert all(store.get(j[0]).status == JobStatus.SCRIPTED for j in res.jobs)
    assert len(held_videos(store)) == 4 and len(alerts) == 4 and "ON HOLD" in alerts[0]
    assert TopicQueue(store).items()[0].status == "produced"              # the same topic is not made twice
    # still down an hour later: one quiet retry, no new alerts, no hammering of the API
    assert [r[2] for r in retry_held_videos(s, store, send=True)] == ["held"] and len(alerts) == 4
    state["down"] = False
    done = retry_held_videos(s, store, send=True)
    assert [r[2] for r in done] == ["rendered"] * 4 and held_videos(store) == {}
    meta = json.loads((s.output_dir / done[0][0] / "metadata.json").read_text())
    assert "Charon" in meta["voice"] and meta["creator_input"] == TAKE
    assert sum("rendered with the Charon voice" in a for a in alerts) == 4


def test_budget_alert_at_80_percent_and_at_the_cap(settings, store, monkeypatch, tmp_path):
    alerts = []
    monkeypatch.setattr(daily_v2, "_notify", lambda s, text: alerts.append(text))
    s = replace(settings, tts_provider="gemini_tts", tts_spend_ledger_path=str(tmp_path / "spend.json"))
    led = SpendLedger(tmp_path / "spend.json")
    led.add(15.0, 0)
    daily_v2._budget_alert(s, store, True)
    assert alerts == []
    led.add(1.2, 0)                                                        # $16.20 = 81%
    daily_v2._budget_alert(s, store, True)
    daily_v2._budget_alert(s, store, True)                                 # once per month, not every video
    assert len(alerts) == 1 and "$16.20 of $20.00" in alerts[0] and "81%" in alerts[0]
    led.add(3.8, 0)
    daily_v2._budget_alert(s, store, True)
    assert len(alerts) == 2 and "Cap reached" in alerts[1]


def test_doctor_shows_voice_lock(settings, store, capsys, monkeypatch):
    from glivarao import __main__ as cli

    monkeypatch.setattr(cli, "get_settings", lambda: replace(settings, tts_provider="gemini_tts"))
    cli.main(["voice-lock"])
    out = capsys.readouterr().out
    assert "gemini-3.8-flash-tts" in out and "Charon" in out and "measured" in out
    cli.main(["voice-lock", "--reset"])
    assert json.loads(store.kv_get("voice_lock"))["voice"] == "Charon"
