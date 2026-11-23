"""Daily delivery by 20:00 Tashkent: planned start from measured durations, late alerts with a reason, automatic
earlier start after 2 late days, and the 15-minute scheduled gate. No network, nothing is uploaded."""
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from glivarao.config import Settings
from glivarao.storage import JobStore
from glivarao.studio import delivery

TZ = ZoneInfo("Asia/Tashkent")
DAY = date(2026, 11, 23)


def _s(tmp_path):
    s = Settings(output_dir=tmp_path / "out", db_path=tmp_path / "db.sqlite3")
    return s, JobStore(s.db_path)


def _at(h, m, day=DAY):
    return datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)


def test_plan_uses_usual_start_until_measured_work_needs_earlier(tmp_path):
    s, store = _s(tmp_path)
    p = delivery.plan(s, store, DAY)
    assert p["start"] == _at(13, 17) and p["deadline"] == _at(20, 0)
    # defaults: 15 + 45 + 3x8 = 84 min x 1.3 + 20 = ~129 min
    assert p["needed_min"] == 129
    for _ in range(3):   # measured: a long video now takes 400 min
        delivery.record_duration(store, "long", 400 * 60)
    p = delivery.plan(s, store, DAY)
    # (15 + 400 + 24) x 1.3 + 20 = 590.7 min before 20:00 -> 10:09
    assert f"{p['start']:%H:%M}" == "10:09" and "measured" in p["why"] and "20:00" in p["why"]


def test_estimate_is_80th_percentile_of_last_10(tmp_path):
    s, store = _s(tmp_path)
    delivery.record_duration(store, "short", 60)
    assert delivery.estimate(store, "short") == delivery.DEFAULTS["short"]   # fewer than 3 -> safe default
    for v in range(1, 13):
        delivery.record_duration(store, "short", v * 60)
    vals = json.loads(store.kv_get("durations"))["short"]
    assert len(vals) == 10 and delivery.estimate(store, "short") == 10 * 60


def test_due_only_after_planned_start_and_respects_retry_after(tmp_path):
    s, store = _s(tmp_path)
    assert delivery.due(s, store, _at(12, 0))[0] is False
    assert delivery.due(s, store, _at(13, 20))[0] is True
    store.kv_set(f"daily_retry_after:{DAY.isoformat()}", str(_at(15, 0).timestamp()))
    assert delivery.due(s, store, _at(14, 0))[0] is False
    assert delivery.due(s, store, _at(15, 5))[0] is True


def test_start_never_before_0915(tmp_path):
    s, store = _s(tmp_path)
    store.kv_set("delivery_shift_min", "600")
    p = delivery.plan(s, store, DAY)
    assert f"{p['start']:%H:%M}" == "09:15" and "09:15" in p["why"]


def test_input_wait_overridden_only_when_start_is_inside_the_take_window(tmp_path):
    s, store = _s(tmp_path)
    assert not delivery.input_wait_overridden(s, delivery.plan(s, store, DAY))      # 13:17 > 13:00
    store.kv_set("delivery_shift_min", "60")
    assert delivery.input_wait_overridden(s, delivery.plan(s, store, DAY))          # 12:17 < 13:00


def test_late_delivery_alerts_once_with_the_reason(tmp_path, monkeypatch):
    s, store = _s(tmp_path)
    p = delivery.plan(s, store, DAY)
    monkeypatch.setattr(delivery, "now_local", lambda settings: _at(15, 0))
    delivery.start_run(s, store, DAY, p)                       # started 15:00, planned 13:17
    sent = []
    monkeypatch.setattr(delivery, "now_local", lambda settings: _at(20, 25))
    job = ("j-long", "long", "pending_approval", "v.mp4", "")
    assert delivery.delivered(s, store, DAY, job, 120 * 60, lambda st, t: sent.append(t)) == 25
    assert len(sent) == 1
    assert "25 min after 20:00" in sent[0] and "started at 15:00, planned 13:17" in sent[0]
    assert "took 120 min" in sent[0] and "sent anyway" in sent[0]
    delivery.delivered(s, store, DAY, job, 120 * 60, lambda st, t: sent.append(t))
    assert len(sent) == 1                                      # alerted once per video
    assert json.loads(store.kv_get("delivery_late"))[DAY.isoformat()] == 25


def test_on_time_delivery_sends_no_alert(tmp_path, monkeypatch):
    s, store = _s(tmp_path)
    monkeypatch.setattr(delivery, "now_local", lambda settings: _at(13, 17))
    delivery.start_run(s, store, DAY, delivery.plan(s, store, DAY))
    monkeypatch.setattr(delivery, "now_local", lambda settings: _at(15, 0))
    sent = []
    assert delivery.delivered(s, store, DAY, ("j", "short", "pending_approval", "v", ""), 300,
                              lambda st, t: sent.append(t)) == 0
    assert sent == [] and delivery.close_day(s, store, DAY, lambda st, t: sent.append(t)) is None


def test_two_late_days_move_the_start_earlier_and_tell_me(tmp_path):
    s, store = _s(tmp_path)
    store.kv_set("delivery_late", json.dumps({"2026-11-22": 30, DAY.isoformat(): 10}))
    sent = []
    assert delivery.close_day(s, store, DAY, lambda st, t: sent.append(t)) == 45   # ceil(30/15)*15 + 15
    assert "late two days in a row" in sent[0] and "starts at 12:32 instead of 13:17" in sent[0]
    assert "shortened" in sent[0]                               # 12:32 is inside the 'your take' window
    assert delivery.close_day(s, store, DAY, lambda st, t: sent.append(t)) is None  # once per day
    assert f"{delivery.plan(s, store, date(2026, 11, 24))['start']:%H:%M}" == "12:32"


def test_deadline_is_20_00_by_default_and_configurable(tmp_path, monkeypatch):
    s, store = _s(tmp_path)
    assert s.delivery_deadline == "20:00"
    monkeypatch.setattr(delivery, "now_local", lambda settings: _at(13, 17))
    delivery.start_run(s, store, DAY, delivery.plan(s, store, DAY))
    monkeypatch.setattr(delivery, "now_local", lambda settings: _at(20, 5))   # late at 20:05
    sent = []
    assert delivery.delivered(s, store, DAY, ("j", "short", "pending_approval", "v", ""), 300,
                              lambda st, t: sent.append(t)) == 5
    assert "5 min after 20:00" in sent[0]


def test_one_late_day_does_not_shift(tmp_path):
    s, store = _s(tmp_path)
    store.kv_set("delivery_late", json.dumps({"2026-11-21": 30, DAY.isoformat(): 10}))   # not consecutive
    assert delivery.close_day(s, store, DAY, lambda *a: None) is None
    assert delivery.shift_minutes(store) == 0


def test_supervised_scheduled_gate(tmp_path, monkeypatch):
    import glivarao.daily_v2 as d

    s, store = _s(tmp_path)
    calls = []

    def run(*a, **k):
        calls.append(k)
        return d.DailyResult("", "skipped", note="waiting")

    monkeypatch.setattr(d, "run_daily_v2", run)
    monkeypatch.setattr(delivery, "now_local", lambda settings: _at(11, 0))
    assert d.supervised_daily(s, store, today=DAY, scheduled=True, notifier=lambda *a: None) is None
    assert calls == []                                           # before 13:17: not yet
    monkeypatch.setattr(delivery, "now_local", lambda settings: _at(13, 30))
    d.supervised_daily(s, store, today=DAY, scheduled=True, notifier=lambda *a: None)
    assert len(calls) == 1 and calls[0]["deliver_day"] == DAY and calls[0]["ignore_input_wait"] is False
    assert json.loads(store.kv_get(f"delivery_run:{DAY.isoformat()}"))["planned"].startswith("2026-11-23T13:17")
    # nothing produced -> next tick waits ~2 h instead of re-running every 15 minutes
    assert store.kv_get(f"daily_retry_after:{DAY.isoformat()}")
    monkeypatch.setattr(delivery, "now_local", lambda settings: _at(13, 45))
    d.supervised_daily(s, store, today=DAY, scheduled=True, notifier=lambda *a: None)
    assert len(calls) == 1
    # a manual run (not --scheduled) is never gated
    d.supervised_daily(s, store, today=DAY, notifier=lambda *a: None)
    assert len(calls) == 2 and calls[1]["deliver_day"] is None


def test_failed_scheduled_runs_back_off_then_stop_for_the_day(tmp_path, monkeypatch):
    """Crash-loop protection lives in the app (no systemd restarts): 30 min, 1 h, 2 h, then no more today.
    Checks in between exit quietly (return None) without running anything."""
    import pytest

    import glivarao.daily_v2 as d

    s, store = _s(tmp_path)
    runs, alerts = [], []

    def boom(*a, **k):
        runs.append(1)
        raise RuntimeError("research outage")

    monkeypatch.setattr(d, "run_daily_v2", boom)
    note = lambda st, t: alerts.append(t)  # noqa: E731
    clock = {"t": _at(13, 30)}
    monkeypatch.setattr(delivery, "now_local", lambda settings: clock["t"])
    for k, (h, m, wait) in enumerate([(13, 30, "30 min"), (14, 0, "60 min"), (15, 0, "120 min")]):
        clock["t"] = _at(h, m)
        with pytest.raises(RuntimeError):
            d.supervised_daily(s, store, today=DAY, scheduled=True, retries=0, notifier=note)
        assert f"next automatic attempt in {wait}" in alerts[-1]
        clock["t"] = _at(h, m + 15)                                    # the next 15-min check: quiet skip
        assert d.supervised_daily(s, store, today=DAY, scheduled=True, retries=0, notifier=note) is None
    clock["t"] = _at(17, 0)
    with pytest.raises(RuntimeError):
        d.supervised_daily(s, store, today=DAY, scheduled=True, retries=0, notifier=note)
    assert "no more automatic attempts today" in alerts[-1] and len(runs) == 4
    clock["t"] = _at(21, 45)
    assert d.supervised_daily(s, store, today=DAY, scheduled=True, retries=0, notifier=note) is None
    assert len(runs) == 4 and len(alerts) == 4
