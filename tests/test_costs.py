"""Per-video real spend (cost-report): every billed amount is tied to the video it was made for, including the
script drafts written before the video existed and auto-retried rejections. Nothing paid is ever called."""
import json
from pathlib import Path

import pytest

from glivarao import daily_v2
from glivarao.studio import cost_report, costs
from tests.test_e2e_dryrun import fake_claude, world  # noqa: F401  (fixture)


def test_ledgers_log_spend_against_the_current_video(tmp_path):
    from glivarao.art.gemini_image import ImageLedger
    from glivarao.scriptgen.claude import ClaudeSpendLedger
    from glivarao.tts.gemini_tts import SpendLedger

    with costs.tag("job-1"):
        ClaudeSpendLedger(tmp_path / "c.json").add(0.10, 1000, 500)
        SpendLedger(tmp_path / "t.json").add(0.02, 400)
        ImageLedger(tmp_path / "i.json").add(0.04, "1K")
    ClaudeSpendLedger(tmp_path / "c.json").add(0.01, 10, 10)                 # not inside a video
    ev, links = costs.load([tmp_path])
    got = costs.per_tag(ev, links)
    assert got["job-1"] == pytest.approx({"claude": 0.10, "voice": 0.02, "images": 0.04})
    assert got[""]["claude"] == pytest.approx(0.01)
    # the monthly budget ledger is unchanged in behaviour
    assert ClaudeSpendLedger(tmp_path / "c.json").spent() == pytest.approx(0.11)


def test_links_follow_drafts_and_retries(tmp_path):
    with costs.tag("draft:short:a"):
        costs.record("claude", 0.05, tmp_path)
    costs.link("draft:short:a", "job-1", tmp_path)
    with costs.tag("job-1"):
        costs.record("claude", 0.02, tmp_path)
    costs.link("job-1", "job-2", tmp_path)       # rejected job-1 was fixed as job-2
    with costs.tag("job-2"):
        costs.record("voice", 0.03, tmp_path)
    ev, links = costs.load([tmp_path])
    assert costs.per_tag(ev, links) == {"job-2": pytest.approx({"claude": 0.07, "voice": 0.03, "images": 0.0})}


def test_cost_tag_is_never_written_into_script_json():
    from glivarao.models import Script

    from glivarao.scriptgen.prompts import normalize_direction

    d = fake_claude("x", "short", 1)
    d["scenes"] = [normalize_direction(sc) for sc in d["scenes"]]
    s = Script.model_validate({**d, "format": "short", "topic": "T"}).model_copy(update={"cost_tag": "draft:x"})
    assert "cost_tag" not in json.loads(s.model_dump_json()) and s.model_copy().cost_tag == "draft:x"


def test_cost_report_end_to_end(world, monkeypatch):  # noqa: F811
    """Make launch #1 as a Short and as a long video with simulated billing; the report shows each video's own
    Claude + voice spend, averages per long / per Short and the monthly estimate at 16 long + 90 Shorts."""
    from glivarao.scriptgen import claude as C
    from glivarao.scriptgen.claude import ClaudeSpendLedger

    s, store, calls = world

    def billed_ask(settings_, prompt, fmt, client=None, ledger=None):
        calls.append((fmt, prompt[:60]))
        (ledger or ClaudeSpendLedger(Path(settings_.claude_spend_ledger_path))).add(0.01, 1000, 500)
        return fake_claude(prompt, fmt, len(calls))

    monkeypatch.setattr(C, "_ask", billed_ask)
    jobs = []
    for short in (True, False):
        r = daily_v2.make_now(s, store, 1, short=short, send=False)
        jobs.append(r.jobs[-1])
        assert r.jobs[-1][2] == "rendered"
    rep = cost_report.build(s, store)
    rows = {v["id"]: v for v in rep["videos"]}
    assert set(rows) == {j[0] for j in jobs}
    claude_calls = len(calls)
    assert sum(v["claude"] for v in rows.values()) == pytest.approx(0.01 * claude_calls)   # every call accounted
    assert all(v["claude"] > 0 and v["voice"] > 0 for v in rows.values())
    assert rep["avg"]["long"]["n"] == 1 and rep["avg"]["short"]["n"] == 1
    want = round(rep["avg"]["long"]["total"] * 16 + rep["avg"]["short"]["total"] * 90, 2)
    assert rep["month_estimate"]["usd"] == want
    out = cost_report.text(rep)
    assert "Average per long video (n=1" in out and "Average per Short (n=1" in out and "16 long + 90 Shorts" in out
    assert rep["unused_drafts"] == {"claude": 0.0, "voice": 0.0, "images": 0.0}


def test_cost_report_cli_without_data(settings, tmp_path, capsys):
    import argparse
    from dataclasses import replace

    from glivarao import __main__ as M

    s = replace(settings, claude_spend_ledger_path=str(tmp_path / "c.json"),
                tts_spend_ledger_path=str(tmp_path / "t.json"), image_spend_ledger_path=str(tmp_path / "i.json"))
    M.cmd_cost_report(argparse.Namespace(days=30, json=False), s)
    assert "Per-video tracking starts with this version" in capsys.readouterr().out
