"""Weekly pace (Mon-Sun, Tashkent): exactly 4 long + 21 Shorts a week; a late start is caught up by Sunday, extra
Short publish slots only until the week's 21 are booked; normal weeks after. No network, nothing uploaded."""
import json
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from glivarao.models import JobStatus
from glivarao.studio import week

MON, TUE, SUN = date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 29)


@pytest.fixture
def ws(settings):
    return replace(settings, pace_mode="weekly")


def _made(store, fmt, day, status=JobStatus.PENDING_APPROVAL, topic="t"):
    job = store.create(fmt, topic)
    job.created_at = datetime(day.year, day.month, day.day, 8, 0, tzinfo=timezone.utc).isoformat()
    store.save(job)
    store.transition(job, JobStatus.SCRIPTED, "")
    store.transition(job, JobStatus.RENDERED, "")
    if status in (JobStatus.PENDING_APPROVAL, JobStatus.APPROVED):
        store.transition(job, JobStatus.PENDING_APPROVAL, "")
    if status == JobStatus.APPROVED:
        store.transition(job, JobStatus.APPROVED, "")
    return job.id


def test_normal_week_is_4_long_on_mon_wed_fri_sun_and_3_shorts_a_day(store, ws):
    p = week.plan(store, ws, date(2026, 11, 30), today_done=False)
    assert [d["long"] for d in p["days"]] == [1, 0, 1, 0, 1, 0, 1]
    assert [d["shorts"] for d in p["days"]] == [3] * 7
    assert week.catchup_slots(ws, p) == []


def test_late_start_catches_up_to_exactly_4_and_21_by_sunday(store, ws):
    # Mon Nov 23 (made by hand): 2 long (card debt + credit scores) and Shorts, some approved, one rejected
    _made(store, "long", MON, JobStatus.APPROVED, "credit card")
    _made(store, "long", MON, topic="credit scores")
    _made(store, "short", MON, JobStatus.APPROVED)                     # a day late: only 1 Short on Monday
    rej = store.get(_made(store, "short", MON))
    store.transition(rej, JobStatus.REJECTED, "")                      # rejected: not counted
    _made(store, "short", date(2026, 11, 22))                          # last week: not counted
    c = week.counted(store, TUE)
    assert len(c["long"]) == 2 and len(c["short"]) == 1
    p = week.plan(store, ws, TUE, today_done=False)
    assert [d["date"] for d in p["days"]][0] == "2026-11-24" and p["days"][-1]["date"] == "2026-11-29"
    assert sum(d["long"] for d in p["days"]) == 2 and sum(d["shorts"] for d in p["days"]) == 20
    assert all(d["long"] <= 1 for d in p["days"])
    assert max(d["shorts"] for d in p["days"]) - min(d["shorts"] for d in p["days"]) <= 1   # spread evenly
    slots = week.catchup_slots(ws, p)
    assert slots and all(t == ["09:00"] for _, t in slots)              # 3 normal + 1 extra on those days
    text = week.status_text(store, ws, TUE)
    assert "Counted so far: 2 long + 1 Short " in text and "Week total if every video passes review: 4 long + 21" in text
    assert "Catch-up publish slots" in text


def test_today_done_plans_from_tomorrow(store, ws):
    store.kv_set(f"daily_done:{TUE.isoformat()}", "[]")
    p = week.plan(store, ws, TUE)
    assert p["days"][0]["date"] == "2026-11-25"


def test_pace_check_and_shorts_quota_follow_the_week(store, ws):
    from glivarao import daily_v2
    from glivarao.studio import buffer

    ok, why = daily_v2.pace_check(store, date(2026, 11, 30), ws)
    assert ok                                                           # Monday: long due
    assert buffer.shorts_quota(store, date(2026, 11, 30), ws) == 3
    _made(store, "long", date(2026, 11, 30))
    ok, why = daily_v2.pace_check(store, date(2026, 12, 1), ws)
    assert not ok and "weekly pace" in why                               # Tuesday: not a long day
    for _ in range(4):
        _made(store, "long", date(2026, 12, 2))
    assert not daily_v2.pace_check(store, date(2026, 12, 6), ws)[0]     # 4 already: never a 5th
    for _ in range(21):
        _made(store, "short", date(2026, 12, 2))
    assert buffer.shorts_quota(store, date(2026, 12, 3), ws) == 0       # 21 already: exactly 21


def test_catch_up_publish_slots_only_until_the_week_is_full(store, ws):
    from glivarao.studio import publish_times as P

    now = datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)            # Tue 01:00 New York
    got = [P.next_slot(store, "short", ws, now=now, job_id=f"s{k}") for k in range(5)]
    tue = [g for g in got if g.date() == date(2026, 11, 24)]
    assert len(tue) == 5 and any(g.strftime("%H:%M") == "09:00" for g in tue)   # extra slots while behind
    book = json.loads(store.kv_get("publish_slots"))
    for k in range(30):                                                  # fill the week to 21
        book[f"x{k}"] = {"format": "short", "slot": datetime(2026, 11, 28, 11, 0, tzinfo=P.NY).isoformat()}
    store.kv_set("publish_slots", json.dumps(book))
    later = P.next_slot(store, "short", ws, now=datetime(2026, 11, 25, 6, 0, tzinfo=timezone.utc), job_id="late")
    assert later.strftime("%H:%M") in ("11:00", "15:00", "19:30")        # week full: normal slots only


def test_cli_week_status(store, ws, monkeypatch, capsys):
    from glivarao import __main__ as cli

    monkeypatch.setattr(cli, "get_settings", lambda: ws)
    cli.main(["week-status"])
    assert "target 4 long + 21 Shorts" in capsys.readouterr().out


def test_batch_plan_uses_the_weekly_long_days(store, ws, monkeypatch):
    from glivarao.studio import batch

    store.kv_set("batch_mode", "on")
    monkeypatch.setattr(week, "today_tk", lambda now=None: TUE)
    _made(store, "long", MON, JobStatus.APPROVED, "How to get out of credit card debt (a plan that works)")
    cs = _made(store, "long", MON, topic="How credit scores really work")
    batch.mark_done(store, "how-credit-scores-work", "1", cs)
    text = batch.plan_text(store, settings=ws)
    assert "Dates = the day each part is made" in text and "Fri Nov 27  LONG  ACA" in text
    assert "Sun Nov 29  LONG" in text and "WEEK 2\nMon Nov 30  LONG" in text
    days = [ln[:10] for ln in text.splitlines() if "  LONG  " in ln]
    weekdays = {d[:3] for d in days[2:]}
    assert weekdays <= {"Mon", "Wed", "Fri", "Sun"}                      # normal weeks after week 1
