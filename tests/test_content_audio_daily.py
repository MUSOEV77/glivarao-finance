"""Brief/scripts/packaging, audio synthesis and the daily-v2 orchestrator (rendering stubbed; offline)."""
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from glivarao.compliance import check_script
from glivarao.content import calculators as calc
from glivarao.content.brief import build_brief, family_of, pick_card, topic_phrase
from glivarao.content.packaging import finalize_description
from glivarao.content.writer import paid_writer_allowed, write_long_free, write_shorts_free

TODAY = date(2026, 11, 18)


def card(key="credit_card", topic="Credit cards, interest and fees", category="Credit and Debt", conf="medium"):
    return {"key": key, "topic": topic, "category": category, "market": "both", "score": 90.0, "confidence": conf,
            "why": ["evidence"], "viewer_questions": [{"title": "How is card interest calculated?", "views": 900,
                                                       "link": "https://money.stackexchange.com/q/1"}],
            "documented_problems": [{"issue": "Problem with a purchase shown on your statement", "product": "Credit card",
                                     "complaints_90d": 8107, "year_ago": 5131, "top_sub_issue": "dispute",
                                     "link": "https://www.consumerfinance.gov/x"}]}


def test_calculators_match_closed_forms():
    lo = calc.amortized_loan(400_000, 0.065, 30).results
    assert lo["monthly_payment"] == pytest.approx(2528.27, abs=0.01)
    mp = calc.minimum_payment_payoff(5000, 0.24).results
    assert mp["months"] < 1200 and mp["total_interest"] > 5000  # pays off, costs more than the balance
    assert calc.fixed_payment_payoff(5000, 0.24, 200).results["months"] == 36


def test_topic_phrase_keeps_acronyms():
    assert topic_phrase("Bonds, Treasuries and TIPS") == "bonds, treasuries and TIPS"
    assert topic_phrase("401(k) plans and employer matching").startswith("401(k)")


def test_brief_facts_are_typed_and_sourced():
    b = build_brief(card(), TODAY)
    kinds = {f.kind for f in b.facts}
    assert {"DATA", "CALCULATION"} <= kinds
    assert all(f.url for f in b.facts if f.kind == "DATA")
    assert "58%" in b.angle and "Fact sheet" in b.fact_sheet_md()


@pytest.mark.parametrize("key,topic,cat", [
    ("credit_card", "Credit cards, interest and fees", "Credit and Debt"),
    ("mortgage", "Mortgages", "Credit and Debt"),
    ("index_funds", "Index funds and ETFs", "Investing"),
    ("scams", "Scams and fraud", "Financial Mistakes and Scams"),
    ("tfsa", "TFSAs", "Saving and Wealth Building"),
    ("bank_account", "Checking and savings accounts", "Banking and Money"),
    ("credit_report", "Credit reports and credit report errors", "Credit and Debt"),
])
def test_free_writer_outputs_pass_compliance(key, topic, cat):
    b = build_brief(card(key, topic, cat), TODAY)
    long = write_long_free(b)
    assert check_script(long, enforce_length=False).ok
    shorts = write_shorts_free(b)
    assert len(shorts) == 2 and shorts[0].title != shorts[1].title
    for s in shorts:
        rep = check_script(s)
        assert rep.ok, rep.errors
        assert "#Shorts" in s.title and s.thumbnail_text


def test_pick_card_rules():
    rep = {"ranked": [card("credit_card"), card("tag:gnucash", "Gnucash", "Personal Finance"),
                      card("mortgage", "Mortgages"), card("scams", "Scams", "Financial Mistakes and Scams")]}
    assert pick_card(rep, set())["key"] == "credit_card"
    assert pick_card(rep, {"credit_card"})["key"] == "mortgage"           # no repeats
    assert pick_card(rep, {"credit_card"}, recent_categories=["Credit and Debt"] * 2)["key"] == "scams"  # rotation
    assert family_of("tag:gnucash") == "generic"


def test_chapters_inserted_for_long_videos():
    d = finalize_description("Intro\n\n{CHAPTERS}\nEnd", ["Hook", "How", "Math", "Tiny", "Plan"],
                             [0, 12.5, 40, 45, 70], True)
    assert "0:00 Hook" in d and "0:40 Math" in d and "Tiny" not in d  # chapters must be >= 10 s apart
    assert "{CHAPTERS}" not in finalize_description("x {CHAPTERS}", ["a"], [0], False)


def test_paid_writer_requires_explicit_approval():
    assert not paid_writer_allowed(SimpleNamespace(allow_paid_apis=False, anthropic_api_key="sk-x"))
    assert not paid_writer_allowed(SimpleNamespace(allow_paid_apis=True, anthropic_api_key=""))
    assert paid_writer_allowed(SimpleNamespace(allow_paid_apis=True, anthropic_api_key="sk-x"))


def test_audio_synthesis_and_ducking():
    from glivarao.anim import audio as A

    for k, peak in A.SFX_PEAK.items():
        s = A.sfx(k)
        assert np.isfinite(s).all() and abs(float(np.abs(s).max()) - peak) < 1e-3
    v = np.zeros(A.SR * 6, dtype=np.float32)
    v[A.SR:3 * A.SR] = 0.5 * np.sin(np.linspace(0, 4000, 2 * A.SR))
    g = A.duck_gain(v)
    assert g[2 * A.SR] < 0.5 * g[5 * A.SR]  # music ducks while the narrator speaks
    out = A.mix(v, [(4.0, "coin"), (4.5, "whoosh")], seed=1)
    assert len(out) == len(v) and float(np.abs(out).max()) <= 0.951


def test_daily_v2_orchestration_with_stubbed_render(settings, store, tmp_path, monkeypatch):
    import glivarao.render.animated as anim
    import glivarao.render.thumbnail_v3 as th
    from glivarao.daily_v2 import run_daily_v2

    rdir = tmp_path / "research"
    rdir.mkdir()
    (rdir / "2026-11-18.json").write_text(json.dumps({"ranked": [card(), card("mortgage", "Mortgages",
                                                                              "Saving and Wealth Building")]}))

    def fake_render(script, out, s, voice=None, workers=None):
        out.mkdir(parents=True, exist_ok=True)
        (out / "video.mp4").write_bytes(b"0" * 100)
        (out / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n")
        return SimpleNamespace(video=out / "video.mp4", srt=out / "captions.srt", duration=60.0, render_seconds=1.0,
                               unknown_words=[], voice=f"Kokoro {voice or 'am_michael'}",
                               scene_starts=[i * 15.0 for i in range(len(script.scenes))])

    monkeypatch.setattr(anim, "render_animated", fake_render)
    monkeypatch.setattr(th, "make_thumbnail_v3", lambda sc, dst, portrait=False: (dst.write_bytes(b"jpg"), dst)[1])
    import glivarao.render.thumbnail_editorial as te

    monkeypatch.setattr(te, "make_thumbnail", lambda sc, dst, portrait=False, theme="": (dst.write_bytes(b"jpg"), dst)[1])
    from dataclasses import replace

    settings = replace(settings, topic_mode="auto", min_days_between_long=0, creator_input_wait_hours=0)
    res = run_daily_v2(settings, store, today=TODAY, research_dir=rdir)
    assert res.topic == "Credit cards, interest and fees" and res.writer.startswith("free")
    assert [j[1] for j in res.jobs] == ["long", "short", "short"]
    assert all(j[2] == "rendered" for j in res.jobs)  # Telegram not configured -> stays rendered, nothing uploaded
    meta = json.loads((settings.output_dir / res.jobs[0][0] / "metadata.json").read_text())
    assert "Chapters:" in meta["description"] and meta["voice"].startswith("Kokoro")
    # next day: the same topic is not repeated
    import shutil

    shutil.copy(rdir / "2026-11-18.json", rdir / "2026-11-19.json")
    res2 = run_daily_v2(settings, store, today=date(2026, 11, 19), research_dir=rdir)
    assert res2.topic == "Mortgages"
