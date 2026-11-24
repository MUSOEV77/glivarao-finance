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
    s1 = _s("For example, if you owe $5,000 at 22.36% and pay $200 a month, it takes years.")
    assert R.example_numbers(s1) == {"$5000", "22.36%", "$200"}
    R.record_examples(store, s1, date(2026, 11, 1))
    again = _s("Say you owe $5,000 on a card.")
    assert R.example_issues(again, store, DAY) and "$5000" in R.example_issues(again, store, DAY)[0]
    assert R.example_issues(again, store, date(2026, 12, 5)) == []          # older than 30 days: fine
    assert R.example_issues(_s("For example, a $3,200 balance."), store, DAY) == []


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
