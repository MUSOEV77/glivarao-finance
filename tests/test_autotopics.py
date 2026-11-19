"""Automatic topic selection: fresh signals (official news, Google Trends, search questions), no repeats of the
last 30 videos, category/family rotation, sourced claims, and the topic shown in the Telegram review.
All network access is simulated."""
import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from glivarao.content.brief import build_brief
from glivarao.content.format_writer import write_long_format
from glivarao.research.engine import build_candidates, compute_metrics, eligible, score_all
from glivarao.research.signals import parse_irs, parse_rss, parse_trends, seed_term
from glivarao.studio import factcheck
from glivarao.studio.autopick import pick_topic
from glivarao.studio.planner import input_window_over, plan_next
from glivarao.studio.queue import TopicQueue
from tests.test_authenticity import FakeTG, _stub_render
from tests.test_content_audio_daily import card

DAY = date(2026, 11, 19)
RSS = """﻿<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel>
<item><title>CFPB warns about buy now, pay later late fees</title><link>https://www.consumerfinance.gov/n1</link>
<pubDate>Tue, 17 Nov 2026 00:00:00 -0400</pubDate><description>&lt;p&gt;BNPL loans&lt;/p&gt;</description></item>
<item><title>Election results</title><link>https://example.org/x</link><pubDate>Tue, 17 Nov 2026 00:00:00 -0400</pubDate></item>
</channel></rss>"""
IRS = ('<h2> <a href="/newsroom/401k-limit-increases-to-25500-for-2027" rel="bookmark"> <span>401(k) limit increases '
       'to $25,500 for 2027, IRA limit remains $7,500</span> </a> </h2> </div> <div class="field field__item">'
       'IR-2026-136, Nov. 12, 2026 — The amount individuals can contribute to their 401(k) plans in 2027 has '
       'increased to $25,500.</div>')
TRENDS = """<?xml version="1.0" encoding="UTF-8"?><rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
<channel><item><title>credit card interest rates</title><ht:approx_traffic>2,000+</ht:approx_traffic>
<pubDate>Wed, 18 Nov 2026 19:20:00 -0800</pubDate><ht:news_item><ht:news_item_title>Card rates hit a record</ht:news_item_title>
<ht:news_item_url>https://news.example/rates</ht:news_item_url><ht:news_item_source>News</ht:news_item_source></ht:news_item></item>
<item><title>boston college basketball</title><ht:approx_traffic>200+</ht:approx_traffic></item></channel></rss>"""


# ---------------------------------------------------------------- fresh sources
def test_parsers_keep_source_urls():
    rss = parse_rss(RSS, "CFPB newsroom")
    assert rss[0]["url"] == "https://www.consumerfinance.gov/n1" and rss[0]["date"] == "2026-11-17"
    irs = parse_irs(IRS)[0]
    assert irs["source"] == "IRS (IR-2026-136)" and irs["date"] == "2026-11-12"
    assert irs["url"] == "https://www.irs.gov/newsroom/401k-limit-increases-to-25500-for-2027"
    tr = parse_trends(TRENDS, "US")
    assert tr[0]["traffic"] == 2000 and tr[0]["news"][0]["url"] == "https://news.example/rates"
    assert seed_term("Credit cards, interest and fees") == "credit cards"


def test_new_signals_feed_demand_freshness_and_filter_off_topic():
    news = parse_rss(RSS, "CFPB newsroom") + parse_irs(IRS)
    cands, rejected = build_candidates([], [], [], news, parse_trends(TRENDS, "US"))
    assert "bnpl" in cands and "retirement_401k" in cands and "credit_card" in cands
    assert not any("basketball" in k for k in cands)          # sports trends are ignored
    assert all("Election" not in n["title"] for c in cands.values() for n in c.news)
    cands["credit_card"].searches = ["how credit cards charge interest", "should i pay off my credit card in full"]
    for c in cands.values():
        compute_metrics(c, DAY)
    score_all(list(cands.values()))
    cc = cands["credit_card"]
    assert cc.scores["practical"][0] == 10 and cc.freshness > 0 and eligible(cc)[0]
    assert "Google Trends" in cc.sources and any("trends.google.com" in w for w in cc.why)
    assert any("irs.gov" in w for w in cands["retirement_401k"].why)


# ---------------------------------------------------------------- picking rules
def report(*cards):
    return {"ranked": [dict(c, rank=i + 1) for i, c in enumerate(cards)]}


def test_no_repeats_and_rotation(store):
    rep = report(card(), card("debt_payoff", "Paying off debt"), card("mortgage", "Mortgages"),
                 card("retirement_401k", "401(k) plans", "Saving and Wealth Building"))
    first, why, _ = pick_topic(rep, store, free_writer=True)
    assert first["key"] == "credit_card" and any("Ranked #1" in w for w in why)
    store.kv_set("used_topics", json.dumps([[str(DAY), "credit_card", "Credit and Debt", "card", "credit card fees"]]))
    nxt, why, skipped = pick_topic(rep, store, free_writer=True)
    # credit_card: repeat; debt_payoff: same family (card) ; mortgage: same category as previous -> 401(k)
    assert nxt["key"] == "retirement_401k"
    assert any("covered in the last 30" in r for r in skipped) and any("category" in r for r in skipped)
    assert any("Skipped higher-ranked" in w for w in why)


def test_similar_angle_is_skipped(store):
    store.kv_set("used_topics", json.dumps([[str(DAY), "other", "Investing", "invest",
                                             "Mortgages refinancing rates mortgage payments"]]))
    rep = report(card("mortgage", "Mortgages refinancing rates mortgage payments", "Credit and Debt"))
    assert pick_topic(rep, store, free_writer=True)[0] is None


# ---------------------------------------------------------------- planner + daily run
def _report_file(tmp_path, *cards):
    rdir = tmp_path / "r"
    rdir.mkdir(exist_ok=True)
    (rdir / f"{DAY}.json").write_text(json.dumps(report(*cards)))
    return rdir


def test_plan_announces_topic_why_and_sources(settings, store, tmp_path):
    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42")
    rdir = _report_file(tmp_path, card())
    tg = FakeTG()
    it = plan_next(s, store, DAY, rdir, send=True, client=tg)
    assert it.auto and it.status == "awaiting_input" and it.why
    msg = tg.texts()[-1]
    assert "picked automatically" in msg and "Credit cards" in msg and "Why this topic" in msg
    assert plan_next(s, store, DAY, rdir, send=False).id == it.id   # already planned: not picked twice


def test_daily_auto_waits_for_take_then_produces(settings, store, tmp_path, monkeypatch):
    from glivarao.daily_v2 import run_daily_v2

    _stub_render(monkeypatch)
    rdir = _report_file(tmp_path, card())
    res = run_daily_v2(settings, store, today=DAY, research_dir=rdir, send=False)
    assert res.jobs == [] and "waiting up to 10 h" in res.note
    it = TopicQueue(store).items()[0]
    TopicQueue(store).add_input(it.id, "I once found a charge I never made on my statement.")
    res = run_daily_v2(settings, store, today=DAY, research_dir=rdir, send=False)
    assert [j[1] for j in res.jobs] == ["long", "short", "short"]
    meta = json.loads((settings.output_dir / res.jobs[0][0] / "metadata.json").read_text())
    assert meta["creator_input"] and not meta["picked_by_you"] is False


def test_daily_auto_produces_without_take_after_window(settings, store, tmp_path, monkeypatch):
    from glivarao.daily_v2 import run_daily_v2

    _stub_render(monkeypatch)
    rdir = _report_file(tmp_path, card())
    run_daily_v2(settings, store, today=DAY, research_dir=rdir, send=False)
    q = TopicQueue(store)
    it = q.items()[0]
    q.update(it.id, picked_at=(datetime.now(timezone.utc) - timedelta(hours=11)).isoformat(timespec="seconds"))
    assert input_window_over(q.get(it.id), settings)
    res = run_daily_v2(settings, store, today=DAY, research_dir=rdir, send=False)
    assert [j[2] for j in res.jobs] == ["rendered"] * 3
    script = json.loads((settings.output_dir / res.jobs[0][0] / "script.json").read_text())
    assert not any(sc.get("beat") == "creator" for sc in script["scenes"])


def test_review_message_starts_with_topic_and_why(settings, store, tmp_path, monkeypatch):
    import glivarao.publish.telegram as tg_mod
    from glivarao.daily_v2 import run_daily_v2

    _stub_render(monkeypatch)
    sent = {}

    def fake_request(job, store_, s, script, checks, **kw):
        sent.setdefault("checks", []).append(checks)
        return store_.transition(job, tg_mod.JobStatus.PENDING_APPROVAL, "test")

    monkeypatch.setattr(tg_mod, "request_approval", fake_request)
    monkeypatch.setattr("glivarao.render.video.preview_clip", lambda v, d: v)
    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42", creator_input_wait_hours=0)
    monkeypatch.setattr("glivarao.studio.planner.announce", lambda *a, **k: None)
    rdir = _report_file(tmp_path, card())
    run_daily_v2(s, store, today=DAY, research_dir=rdir, send=True)
    first = sent["checks"][0]
    assert first.startswith("TOPIC: Credit cards, interest and fees (picked automatically by research)")
    assert "WHY THIS TOPIC" in first and "Reject" in first and "every claim has a source url" in first.lower()


# ---------------------------------------------------------------- every claim has a source URL
def test_every_claim_has_a_source_url_including_calculations():
    for key, fam_card in (("credit_card", card()), ("mortgage", card("mortgage", "Mortgages")),
                          ("retirement_401k", card("retirement_401k", "401(k) plans", "Saving and Wealth Building"))):
        b = build_brief(fam_card, DAY)
        for style in ("explainer", "comparison", "case_study"):
            claims = factcheck.check_claims(write_long_format(b, style), b)
            assert claims and not factcheck.needs_source(claims), (key, style, factcheck.needs_source(claims))
            assert all(c.url.startswith("https://") for c in claims)


def test_free_writer_script_with_unsourced_claim_is_not_rendered(settings, store, tmp_path, monkeypatch):
    import glivarao.daily_v2 as d

    _stub_render(monkeypatch)
    real = d._write_long

    def with_bad_claim(*a, **k):
        s = real(*a, **k)
        bad = s.scenes[1].model_copy(update={"narration": "About 73% of Americans carry a balance."})
        return s.model_copy(update={"scenes": [s.scenes[0], bad] + s.scenes[2:]})

    monkeypatch.setattr(d, "_write_long", with_bad_claim)
    s = replace(settings, creator_input_wait_hours=0)
    res = d.run_daily_v2(s, store, today=DAY, research_dir=_report_file(tmp_path, card()), send=False)
    assert res.jobs[0][2] == "rejected_compliance" and "without a source URL" in res.jobs[0][4]


def test_news_breakdown_quotes_official_release_with_url():
    c = card("retirement_401k", "401(k) plans and employer matching", "Saving and Wealth Building")
    c["documented_problems"] = []
    c["official_news"] = [parse_irs(IRS)[0]]
    b = build_brief(c, DAY)
    s = write_long_format(b, "news_breakdown")
    assert "IRS announced: 401(k) limit increases to $25,500" in s.scenes[0].narration
    claims = factcheck.check_claims(s, b)
    assert any(c.url.startswith("https://www.irs.gov/newsroom/") for c in claims) and not factcheck.needs_source(claims)
    assert "irs.gov/newsroom" in factcheck.add_sources_to_description(s.description, claims)


def test_agency_words_do_not_create_false_topics():
    from glivarao.research.engine import _news_text
    from glivarao.research.finance_filter import match_concepts

    keys = lambda t: [c.key for c in match_concepts(_news_text(t))]  # noqa: E731
    assert "bonds" not in keys("Treasury, IRS issue final rules to help Americans save for retirement")
    assert "stocks" not in keys("IRS shares Agency Financial Report for fiscal year 2026")
    assert "bonds" in keys("Treasury bills yields rise")
    assert "retirement_401k" in keys("401(k) limit increases to $25,500 for 2027")


def test_description_lists_sources_of_claims_not_search_evidence():
    c = card()
    c["viewer_questions"] = []
    c["search_questions"] = ["how credit cards charge interest"]
    b = build_brief(c, DAY)
    s = write_long_format(b, "explainer")
    assert "google.com/search" not in s.description and "consumerfinance.gov" in s.description
    assert b.viewer_questions and "google.com/search" in b.viewer_questions[0]["link"]  # still in the evidence
