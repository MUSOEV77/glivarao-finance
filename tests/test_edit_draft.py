"""edit-draft (no LLM) and the story-fact leak: IndyMac ($12B) must never be on a non-story video's fact sheet."""
import json
from datetime import date

import pytest

from glivarao.content.brief import Brief, Fact, build_brief
from glivarao.models import JobStatus, Scene, Script


def test_story_facts_never_leak_into_other_videos():
    card = {"key": "emergency_fund", "topic": "Emergency fund", "category": "x", "market": "US", "score": 1,
            "confidence": "high", "angle": "", "viewer_questions": [], "documented_problems": [],
            "why": [], "launch_facts": []}
    b = build_brief(card, date(2026, 11, 25))
    assert not [f for f in b.facts if "IndyMac" in f.text or f.kind == "STORY"]
    bank = build_brief({**card, "key": "us_banks", "topic": "Banks"}, date(2026, 11, 25))
    assert not [f for f in bank.facts if f.kind == "STORY"]                      # not a story video: none
    story = build_brief({**card, "key": "us_banks", "topic": "Banks", "story": True}, date(2026, 11, 25))
    assert [f for f in story.facts if f.kind == "STORY" and "IndyMac" in f.text]  # only on a money story


@pytest.fixture
def draft(settings, store):
    job = store.create("long", "Emergency fund")
    out = settings.output_dir / job.id
    out.mkdir(parents=True)
    sc = [Scene(heading="h", narration="You have 55% odds. It reports losses of about $12 billion. "
                                        "Savings are guaranteed to grow."),
          Scene(heading="End", narration="You'll miss it less than you'd miss a surprise bill. This video is for "
                                         "education only and isn't financial advice.")]
    (out / "script.json").write_text(Script(format="long", topic="t", title="t", description="d",
                                            thumbnail_text="", scenes=sc).model_dump_json())
    (out / "brief.json").write_text(Brief("2026-11-25", "emergency_fund", "Emergency fund", "x", "US", "x", 1.0,
                                          "high", [], "", [], [], facts=[Fact(
                                              "DATA", "In 2025, 55 percent of US adults had three months saved.",
                                              "Fed", "https://www.federalreserve.gov/x")]).to_json())
    store.transition(job, JobStatus.SCRIPTED, "")
    store.transition(job, JobStatus.REJECTED_COMPLIANCE, "x")
    return job.id, out


def test_edit_draft_without_any_llm(settings, store, draft, monkeypatch):
    from glivarao import daily_v2

    monkeypatch.setattr("glivarao.scriptgen.claude._ask", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    job, out = draft
    r = daily_v2.edit_draft(settings, store, job,
                            replace=[("guaranteed to grow", "likely to grow"),
                                     ("You'll miss it less than you'd miss a surprise bill.",
                                      "You'll likely miss it less than a surprise bill.")],
                            delete=["It reports losses of about $12 billion."])
    text = json.loads((out / "script.json").read_text())
    narr = " ".join(s["narration"] for s in text["scenes"])
    assert "$12 billion" not in narr and "guaranteed" not in narr and "You'll likely miss it less" in narr
    assert len(r["changes"]) == 3 and list(out.glob("script.json.bak-*"))
    with pytest.raises(ValueError, match="not found"):
        daily_v2.edit_draft(settings, store, job, replace=[("no such text", "x")])


def test_edit_draft_cli_show(settings, store, draft, monkeypatch, capsys):
    from glivarao import __main__ as cli

    job, out = draft
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    cli.main(["edit-draft", job, "--show"])
    o = capsys.readouterr().out
    assert "script.json" in o and "[0]" in o and "claims without a source URL" in o
