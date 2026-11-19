"""Buffer (2 long + 6 Shorts ready), production lead, Tashkent quiet hours, health report and alerts."""
import json
from dataclasses import replace
from datetime import date, datetime, timezone

from glivarao.models import JobStatus
from glivarao.studio import buffer, health, quiet

NIGHT = datetime(2026, 11, 19, 19, 30, tzinfo=timezone.utc)   # 00:30 Tashkent
MORNING = datetime(2026, 11, 20, 3, 30, tzinfo=timezone.utc)  # 08:30 Tashkent
DAY = date(2026, 11, 19)


def _approved(store, fmt, slot=None):
    j = store.create(fmt, "t")
    for st in (JobStatus.SCRIPTED, JobStatus.RENDERED, JobStatus.PENDING_APPROVAL, JobStatus.APPROVED):
        store.transition(j, st, "test")
    if slot:
        book = json.loads(store.kv_get("publish_slots", "{}"))
        book[j.id] = {"format": fmt, "slot": slot}
        store.kv_set("publish_slots", json.dumps(book))
    return j


def test_buffer_counts_ready_videos_and_shorts_quota(settings, store):
    s = replace(settings, buffer_long=2, buffer_shorts=6)
    _approved(store, "long", "2099-01-01T14:00:00-05:00")
    _approved(store, "long", "2000-01-01T14:00:00-05:00")          # already published (slot passed)
    for _ in range(2):
        _approved(store, "short", "2099-01-02T11:00:00-05:00")
    b = buffer.status(store, s)
    assert (b["ready_long"], b["ready_shorts"], b["low_long"], b["low_shorts"]) == (1, 2, True, True)
    assert buffer.shorts_quota(store, DAY, s, b) == 4                  # catch up the 4 missing Shorts
    assert buffer.shorts_quota(store, DAY, s, None) == 3               # normal day: 3 (90 a month)
    store.kv_set("short_counts", json.dumps({"2026-11-01": 88}))
    assert buffer.shorts_quota(store, DAY, s, b) == 2                  # never above 90 a month
    assert "⚠️ Long videos: 1 approved and ready (target 2)" in buffer.text(b, s)


def test_low_buffer_allows_an_early_long_video(settings, store):
    from glivarao.daily_v2 import pace_check

    s = replace(settings, buffer_long=2, production_lead_days=3)
    store.kv_set("long_dates", json.dumps(["2026-11-%02d" % d for d in range(1, 18, 2)]))   # 9 made by Nov 17
    ok, why = pace_check(store, DAY, s)                     # due by Nov 22: ceil(16*22/30)=12 -> allowed
    assert ok
    store.kv_set("long_dates", json.dumps(["2026-11-%02d" % d for d in range(1, 14)]))   # 13 made, 12 due
    assert not pace_check(store, DAY, replace(s, buffer_long=0))[0]      # on pace, buffer fine -> wait
    assert pace_check(store, DAY, s)[0]                                   # buffer empty -> make one early


def test_quiet_hours_queue_messages_until_morning(settings, store, monkeypatch):
    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42", quiet_start="23:00",
                quiet_end="08:00")
    assert quiet.is_quiet(s, NIGHT) and not quiet.is_quiet(s, MORNING)
    assert quiet.is_quiet(s, datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc))      # 23:00 Tashkent
    assert not quiet.is_quiet(s, datetime(2026, 11, 19, 17, 59, tzinfo=timezone.utc))
    from glivarao.publish.telegram import notify
    from tests.test_uploadpack import RecTG

    tg = RecTG()
    notify(s, "render failed", client=tg, now=NIGHT)
    assert tg.texts() == [] and quiet.pending(store) == (1, 0)
    assert quiet.flush(s, store, tg, now=NIGHT) == 0
    assert quiet.flush(s, store, tg, now=MORNING) == 1 and "render failed" in tg.texts()[0]
    assert quiet.pending(store) == (0, 0)


def test_health_report_and_alerts(settings, store, tmp_path):
    from glivarao.tts.gemini_tts import SpendLedger

    s = replace(settings, buffer_long=2, buffer_shorts=6, tts_spend_ledger_path=str(tmp_path / "v.json"),
                claude_spend_ledger_path=str(tmp_path / "c.json"), disk_alert_gb=10**9)
    SpendLedger(tmp_path / "v.json").add(17.0, 0)
    a = health.alerts(s, store)
    assert any("Voice (Gemini Charon): $17.00 of $20.00" in x for x in a)
    assert any("Disk low" in x for x in a) and any("Buffer low" in x for x in a)
    assert not any("Buffer low" in x or "Voice" in x for x in health.alerts(s, store))  # once per day / month
    r = health.report(s, store)
    for part in ("BUFFER", "PACE", "Launch list:", "SPEND", "Voice: Charon"):
        assert part in r
