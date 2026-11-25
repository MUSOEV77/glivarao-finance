"""My take (asked at 10:00, any language -> US English), money-story format (2 of 4 weekly longs when a documented
story is on file), phone-only YouTube sign-in, daily analytics and the Monday report. No network."""
import json
from dataclasses import replace
from datetime import date

import pytest

from glivarao.studio import mytake


@pytest.fixture
def ws(settings):
    return replace(settings, pace_mode="weekly", telegram_approver_chat_id="42")


class TG:
    def __init__(self):
        self.sent = []

    def call(self, method, **kw):
        self.sent.append((method, kw))
        return {"result": {"message_id": 77}}


def test_take_is_asked_saved_in_english_and_used(ws, store, monkeypatch):
    store.kv_set("batch_mode", "on")
    tg = TG()
    req = mytake.ask(ws, store, date(2026, 11, 29), client=tg)       # Sunday -> Monday is a long day
    assert req and "Tomorrow's long video" in tg.sent[0][1]["text"] and req["msg"] == 77
    monkeypatch.setattr("glivarao.scriptgen.backends.openrouter_chat",
                        lambda *a, **k: ("I paid my card late once and it cost me.", {}))
    eng = mytake.save(ws, store, req, "Однажды я заплатил по карте поздно, и это стоило мне денег.")
    assert eng == "I paid my card late once and it cost me."
    assert mytake.take_for(store, req["entry"]) == eng
    assert mytake.to_english(ws, "Already English.") == "Already English."     # no call for English


def test_story_format_only_with_a_documented_story(store):
    from glivarao.content.brief import Brief, Fact
    from glivarao.studio import formats, stories, week

    b = Brief("2026-11-25", "us_banks", "Bank failures", "x", "US", "banks", 1.0, "high", [], "", [], [],
              facts=[Fact("DATA", "x", "s", "u")])
    stories.add_to_brief(b)
    assert stories.has_story(b) and "money_story" in formats.eligible(b) and week.want_story(store, b)
    store.kv_set("variety_history:long", json.dumps([{"job": "20261124-long-a", "structure": "money_story"},
                                                     {"job": "20261125-long-b", "structure": "money_story"}]))
    assert not week.want_story(store, b, date(2026, 11, 26))                 # 2 this week already
    none = Brief("2026-11-25", "credit_score", "Scores", "x", "US", "x", 1.0, "high", [], "", [], [], facts=[])
    stories.add_to_brief(none)
    assert "money_story" not in formats.eligible(none)                      # never invented


def test_phone_sign_in_saves_a_read_only_token(ws, tmp_path):
    from glivarao.studio import analytics_report as A

    sec = tmp_path / "client.json"
    sec.write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "sec"}}))
    s = replace(ws, youtube_client_secrets_file=sec, youtube_token_file=tmp_path / "tok.json")
    replies = iter([{"device_code": "d", "user_code": "ABC-123", "verification_url": "https://www.google.com/device",
                     "interval": 1}, {"error": "authorization_pending"}, {"access_token": "t", "refresh_token": "r"}])

    class Sess:
        def post(self, url, data, timeout):
            return type("R", (), {"json": lambda self: next(replies)})()

    said = []
    A.device_auth(s, said.append, session=Sess(), sleep=lambda x: None)
    tok = json.loads(s.youtube_token_file.read_text())
    assert "ABC-123" in said[0] and tok["refresh_token"] == "r" and tok["scopes"] == A.READ_SCOPES


def test_daily_pull_and_monday_report(ws, store):
    from glivarao.models import JobStatus
    from glivarao.studio import analytics_report as A
    from glivarao.studio import series as S

    job = store.create("long", "t")
    job.duration_sec = 300
    store.save(job)
    for st in (JobStatus.SCRIPTED, JobStatus.RENDERED, JobStatus.PENDING_APPROVAL, JobStatus.APPROVED):
        store.transition(store.get(job.id), st, "")
    S.set_link(store, job.id, "https://youtu.be/OifqlJEAhKg")
    store.kv_set("variety_history:long", json.dumps([{"job": job.id, "hook_type": "number",
                                                      "thumb_layout": "cream/max_right", "structure": "money_story"}]))

    class Api:
        def reports(self):
            return self

        def query(self, metrics, dimensions=None, **k):
            if dimensions:
                rows = [{"elapsedVideoTimeRatio": r, "audienceWatchRatio": 1 - r / 2} for r in (0.05, 0.1, 0.5)]
            else:
                rows = [{"views": 1000, "averageViewPercentage": 41.0, "videoThumbnailImpressions": 9000,
                         "videoThumbnailImpressionsClickRate": 6.2}]
            self.r = {"columnHeaders": [{"name": n} for n in rows[0]], "rows": [list(x.values()) for x in rows]}
            return self

        def execute(self):
            return self.r

    data = A.pull(ws, store, api=Api(), day=date(2026, 11, 30))
    m = data[job.id]
    assert m["views"] == 1000 and m["ctr"] == 6.2 and m["avp"] == 41.0 and m["r30"] == pytest.approx(0.95)
    text = A.weekly_text(store, data)
    assert "Best hooks" in text and "number" in text and "cream/max_right" in text and "story" in text


def test_new_timers_respect_systemd_limits():
    from tests.test_systemd_limits import UNITS, _ini, max_starts_in, seconds

    for name in ("glivarao-take", "glivarao-analytics"):
        t, s = _ini(UNITS / f"{name}.timer"), _ini(UNITS / f"{name}.service")
        assert max_starts_in(seconds(s["StartLimitIntervalSec"][0]), t) <= int(s["StartLimitBurst"][0])
