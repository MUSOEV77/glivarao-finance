"""make-now <launch #> [--short], clear-hold, and the server clock check. All external calls simulated."""
import json
from dataclasses import replace

import pytest

from glivarao import daily_v2
from glivarao.studio import launch_plan


@pytest.fixture
def paid(settings, monkeypatch):
    from glivarao.scriptgen import claude as C
    from tests.test_authenticity import _stub_render
    from tests.test_production_hardening import script_json

    _stub_render(monkeypatch)
    calls = []

    def ask(settings_, prompt, fmt, client=None, ledger=None):
        calls.append(fmt)
        d = json.loads(script_json(25, 112) if fmt == "long" else script_json(4, 25))
        import random

        r = random.Random(len(calls))
        vocab = ("budget card interest payment savings plan balance credit bill account rate lender monthly "
                 "habit income expense goal fund cash debt score report fee").split()
        for i, sc in enumerate(d["scenes"]):                       # unique wording in every scene, like a real script
            n = len(sc["narration"].split())
            words = [r.choice(vocab) + ("." if k % 12 == 11 else "") for k in range(n)]
            sc["narration"] = f"Part {i} about your credit card. " + " ".join(words[7:])
        d["scenes"][-1]["narration"] += " This video is for education only and isn't financial advice."
        d["scenes"][-2]["heading"] = "What to do this weekend"   # like Claude: the closing action section
        return d

    monkeypatch.setattr(C, "_ask", ask)
    monkeypatch.setattr(launch_plan, "verify_facts", lambda v, session=None: (v.facts, []))
    monkeypatch.setattr(daily_v2, "_notify", lambda s, t: None)
    return replace(settings, allow_paid_apis=True, writer="claude_openrouter"), calls


def test_make_now_long_and_short_for_a_launch_video(paid, store):
    s, calls = paid
    store.kv_set("launch_done", "[]")
    r = daily_v2.make_now(s, store, 1, short=True, send=False)
    assert r.jobs and all(j[1] == "short" for j in r.jobs) and calls == ["short"]
    assert r.topic == launch_plan.LAUNCH[0].topic and launch_plan.done(store) == []    # a Short doesn't use #1 up
    r = daily_v2.make_now(s, store, 1, send=False)
    assert r.jobs and r.jobs[0][1] == "long" and "long" in calls
    made = r.jobs[0][2] in ("rendered", "pending_approval")
    assert launch_plan.done(store) == ([1] if made else [])


def test_make_now_respects_pause_range_and_claude_only(paid, store):
    from glivarao.studio import pause

    s, _ = paid
    with pytest.raises(ValueError, match="1-16"):
        daily_v2.make_now(s, store, 17, send=False)
    with pytest.raises(ValueError, match="Claude only"):
        daily_v2.make_now(replace(s, allow_paid_apis=False), store, 1, send=False)
    pause.pause(s, "test")
    with pytest.raises(pause.Paused):
        daily_v2.make_now(s, store, 1, send=False)


def test_make_now_waits_for_a_running_daily_run(paid, store):
    import fcntl
    from pathlib import Path

    s, _ = paid
    fh = open(Path(s.db_path).with_name("daily.lock"), "w")
    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(daily_v2.Busy):
            daily_v2.make_now(s, store, 1, send=False)
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def test_clear_hold_and_retest(settings, store, monkeypatch, capsys):
    from glivarao import __main__ as cli

    store.kv_set("writer_held", json.dumps({"since": "2026-11-21", "reason": "RateLimitError: 429"}))
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "_store", lambda s: store)
    monkeypatch.setattr("glivarao.scriptgen.vertex_quota.live_test", lambda s: (True, "answered 'OK' ($0.00004)"))
    cli.main(["clear-hold", "--test"])
    out = capsys.readouterr().out
    assert "cleared hold since 2026-11-21" in out and "OK" in out and daily_v2.writer_held(store) == {}


def test_server_clock_uses_the_real_system_zone(monkeypatch):
    from glivarao import doctor

    monkeypatch.setenv("TZ", "Asia/Tashkent")
    assert doctor.system_timezone() == "Asia/Tashkent"
    monkeypatch.delenv("TZ")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: type("R", (), {"stdout": "Asia/Tashkent\n"})())
    assert doctor.system_timezone() == "Asia/Tashkent"          # timedatectl wins over a stale /etc/timezone


def test_make_now_long_reaches_review(paid, store, capsys):
    s, _ = paid
    store.kv_set("launch_done", "[]")
    r = daily_v2.make_now(s, store, 1, send=False)
    print(r.jobs)
    assert r.jobs[0][2] in ("rendered", "pending_approval"), r.jobs
    assert launch_plan.done(store) == [1]


def test_make_now_retries_once_with_the_rejection_reason(paid, store, monkeypatch):
    from glivarao.scriptgen import claude as C

    s, _ = paid
    prompts = []
    good_ask = C._ask

    def ask(settings_, prompt, fmt, client=None, ledger=None):
        prompts.append(prompt)
        d = good_ask(settings_, prompt, fmt)
        if "rejected this script for these reasons" not in prompt:
            d["scenes"][-2]["heading"] = "Recap"           # no closing "What to do" section -> rejected
        return d

    monkeypatch.setattr(C, "_ask", ask)
    store.kv_set("launch_done", "[]")
    r = daily_v2.make_now(s, store, 1, send=False)
    assert [j[2] for j in r.jobs] == ["rejected_compliance", "rendered"], r.jobs
    fix = next(p for p in prompts if "rejected this script for these reasons" in p)
    assert "What to do" in fix and "FACT SHEET" in fix and "federalreserve.gov" in fix
    assert "fixed by Claude, checked again" in r.note and launch_plan.done(store) == [1]


def test_retry_rejected_makes_todays_rejected_videos_again_once(paid, store, monkeypatch):
    from glivarao.scriptgen import claude as C

    s, _ = paid
    good_ask = C._ask
    state = {"broken": True}

    def ask(settings_, prompt, fmt, client=None, ledger=None):
        d = good_ask(settings_, prompt, fmt)
        if state["broken"]:
            d["scenes"][-2]["heading"] = "Recap"          # always non-compliant while "broken"
        return d

    monkeypatch.setattr(C, "_ask", ask)
    store.kv_set("launch_done", "[]")
    r = daily_v2.make_now(s, store, 1, send=False)
    assert [j[2] for j in r.jobs] == ["rejected_compliance", "rejected_compliance"]     # incl. the automatic fix
    state["broken"] = False
    jobs = daily_v2.retry_rejected(s, store, send=False)
    assert len(jobs) == 1 and jobs[0][2] == "rendered", jobs           # one video: its latest attempt is fixed
    assert daily_v2.retry_rejected(s, store, send=False) == []                            # never twice
