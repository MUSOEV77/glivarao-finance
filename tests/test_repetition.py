"""No reused worked-example numbers within 30 days, no repeated research topics within 14 days, rotating Short
formats."""
import json
from datetime import date

from glivarao.models import Scene, Script
from glivarao.studio import repetition as R

DAY = date(2026, 11, 24)


def _s(text):
    return Script(format="short", topic="t", title="t", description="", thumbnail_text="",
                  scenes=[Scene(heading="h", narration=text)])


def test_example_numbers_are_not_reused_within_30_days(store):
    facts = ["As of November 2026, the average card rate was 22.36%."]
    s1 = _s("Put $500 a month away for 30 years at 0.05% versus 1% and the gap is $101,744. Cards charge 22.36%.")
    assert R.example_numbers(s1, facts) == {"$500", "0.05%", "1%", "$101744"}          # fact numbers excluded
    R.record_examples(store, s1, date(2026, 11, 23), facts)
    again = _s("Paychecks: save $500 a month at 0.05% instead of 1% and you lose $101,744.")
    assert R.example_issues(again, store, DAY, facts)                                   # no 'example' word needed
    assert R.example_issues(again, store, date(2026, 12, 30), facts) == []              # older than 30 days
    assert R.example_issues(_s("A $3,200 balance at 22.36%."), store, DAY, facts) == []


def test_script_must_match_its_topic():
    from types import SimpleNamespace as N

    b = N(topic="Paychecks", topic_key="paycheck")
    off = _s("Put $500 a month away for 30 years and watch it grow.")
    assert R.topic_issues(off, b)
    on = Script(format="short", topic="t", title="Your Paycheck Leaks", description="", thumbnail_text="",
                scenes=[Scene(heading="h", narration="Your paycheck shrinks before it lands.")])
    assert R.topic_issues(on, b) == []


def test_writer_is_told_which_example_numbers_to_avoid(monkeypatch):
    from glivarao.content import writer
    from glivarao.content.brief import Brief, Fact

    seen = {}
    monkeypatch.setattr("glivarao.scriptgen.claude.generate_with_claude",
                        lambda topic, fmt, st, angle="": seen.setdefault("a", angle) and _s("x"))
    b = Brief("2026-11-24", "credit_card", "Card", "debt", "US", "cards", 1.0, "high", [], "", [], [],
              facts=[Fact("DATA", "x", "s", "u")])
    try:
        writer.write_with_claude(b, "short", None, avoid_numbers={"$5000", "$200"})
    except Exception:  # noqa: BLE001  the stub's script is minimal; only the prompt matters here
        pass
    assert "Do NOT reuse these worked-example numbers" in seen["a"] and "$5000" in seen["a"]


def test_topics_not_repeated_within_14_days(store):
    store.kv_set("used_topics", json.dumps([["2026-11-01", "mortgage"], ["2026-11-20", "credit_card"]]))
    store.kv_set("used_short_topics", json.dumps([["2026-11-15", "hysa"]]))
    assert R.recent_topics(store, DAY) == {"credit_card", "hysa"}


def test_short_formats_rotate(store):
    first = R.next_short_formats(store, 3)
    nxt = R.next_short_formats(store, 3)
    seq = first + nxt
    assert all(a != b for a, b in zip(seq, seq[1:])) and len(set(seq)) == 6


def test_daily_shorts_batch_round_robin_distinct_pillars(store):
    from glivarao.studio import batch

    store.kv_set("batch_mode", "on")
    picked = []
    for _ in range(3):
        t = batch.next_short_topic(store, DAY)
        picked.append(t)
        batch.note_pillar(store, DAY, t.key)
    pillars = [batch._pillar(t.key) for t in picked]
    assert len(set(pillars)) == 3                                 # never the same pillar twice in a day
    card = batch.short_card(store, picked[0])
    assert card["batch_short"]["idea"] and card["launch_facts"][0]["text"] == card["batch_short"]["fact"]
    assert batch.short_card(store, picked[0])["batch_short"]["idea"] != card["batch_short"]["idea"]   # next idea


def test_rejected_shorts_get_replaced_the_same_day(store, settings, monkeypatch):
    from dataclasses import replace
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from glivarao import daily_v2
    from glivarao.studio import delivery

    ws = replace(settings, pace_mode="weekly")
    monkeypatch.setattr(delivery, "now_local", lambda s: datetime(2026, 11, 24, 15, 0, tzinfo=ZoneInfo("Asia/Tashkent")))
    assert daily_v2._still_needed_today(ws, store, DAY) > 0       # nothing good yet: replacements are made
    monkeypatch.setattr(delivery, "now_local", lambda s: datetime(2026, 11, 24, 20, 5, tzinfo=ZoneInfo("Asia/Tashkent")))
    assert daily_v2._still_needed_today(ws, store, DAY) == 0      # after 20:00: no more
