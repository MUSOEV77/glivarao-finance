"""Channel focus: 5 pillars only, pillar rotation, tax season, recurring series with links, affiliate links per
pillar. Telegram is simulated; nothing is uploaded."""
import json
from dataclasses import replace
from datetime import date

from glivarao.research.finance_filter import CONCEPTS
from glivarao.studio import pillars as P
from glivarao.studio import series as S
from glivarao.studio.autopick import pick_topic
from glivarao.studio.bot import handle_message
from glivarao.studio.uploadpack import send_pack
from tests.test_content_audio_daily import card
from tests.test_uploadpack import RecTG, approved_job

NOV = date(2026, 11, 19)
JAN = date(2027, 1, 14)


def rep(*cards):
    return {"ranked": [dict(c, rank=i + 1) for i, c in enumerate(cards)]}


def c(key, label, score=80, market="both"):
    return dict(card(key, label), score=score, market=market)


def hist(store, *keys, key="used_topics"):
    store.kv_set(key, json.dumps([["2026-11-01", k, "", "", ""] for k in keys]))


def test_every_concept_is_in_exactly_one_pillar_or_explicitly_out_of_focus():
    for con in CONCEPTS:
        homes = [p.key for p in P.PILLARS.values() if con.key in p.concepts]
        assert len(homes) + (con.key in P.OUT_OF_FOCUS) == 1, con.key


def test_out_of_focus_topics_are_rejected(store):
    r = rep(c("crypto", "Cryptocurrency", 99), c("stocks", "Investing in stocks", 98),
            c("tfsa", "TFSAs", 97, "CA"), c("hysa", "High-yield savings accounts", 50))
    got, why, skipped = pick_topic(r, store, free_writer=False, today=NOV)
    assert got["key"] == "hysa"
    assert any("crypto" in s for s in skipped) and any("single stocks" in s for s in skipped)
    assert any("Canada-only" in s for s in skipped)
    assert why[0].startswith("Pillar: Budgeting and saving")


def test_never_the_same_pillar_twice_in_a_row(store):
    hist(store, "hysa")
    r = rep(c("budgeting", "Budgeting", 99), c("emergency_fund", "Emergency funds", 95),
            c("scams", "Scams and fraud", 40))
    got, _, _ = pick_topic(r, store, free_writer=False, today=NOV)
    assert got["key"] == "scams"


def test_debt_and_credit_at_least_60_percent_of_long_videos(store):
    hist(store, "credit_card", "hysa", "credit_score", "scams")   # only 2 debt in the last 4 -> must be debt
    r = rep(c("index_funds", "Index funds and ETFs", 99), c("student_loan", "Student loans", 30))
    got, why, _ = pick_topic(r, store, free_writer=False, today=NOV)
    assert got["key"] == "student_loan" and any("Channel focus" in w for w in why)
    hist(store, "credit_card", "student_loan", "credit_score", "hysa")   # 3 debt in last 4 -> others allowed
    assert pick_topic(r, store, free_writer=False, today=NOV)[0]["key"] == "index_funds"
    # simulate 30 picks from a varied pool: >= 60% debt in every 5-video window
    pool = [c(k, k, 90 - i) for i, k in enumerate(
        ["hysa", "index_funds", "scams", "budgeting", "credit_card", "bnpl", "credit_score", "student_loan",
         "personal_loan", "auto_loan", "mortgage", "debt_payoff", "credit_report", "debt_collection",
         "emergency_fund", "ira_roth", "identity_theft", "tax_refund"])]
    store.kv_set("used_topics", "[]")
    seq = []
    for n in range(30):
        got, _, _ = pick_topic(rep(*pool), store, free_writer=False, today=NOV)
        assert got is not None, n
        h = json.loads(store.kv_get("used_topics", "[]")) + [["2026-11-01", got["key"], "", "", "", False]]
        store.kv_set("used_topics", json.dumps(h))
        seq.append(P.pillar_of(got["key"]).key)
    assert all(seq[i:i + 5].count("debt") >= 3 for i in range(len(seq) - 4)), seq
    assert len(set(seq)) >= 4                                      # other pillars still appear


def test_other_pillars_capped_and_never_twice_in_a_row(store):
    hist(store, "credit_card", "credit_score", "hysa", "bnpl")
    r = rep(c("budgeting", "Budgeting", 99), c("scams", "Scams and fraud", 50))
    got, _, skipped = pick_topic(r, store, free_writer=False, today=NOV)
    assert got["key"] == "scams" and any("1× in the last 5" in k for k in skipped)


def test_news_videos_at_most_one_in_four(store):
    store.kv_set("used_topics", json.dumps([["2026-11-01", "credit_card", "", "", "", False],
                                            ["2026-11-03", "bnpl", "", "", "", True],
                                            ["2026-11-05", "credit_score", "", "", "", False]]))
    news = dict(c("student_loan", "Student loans", 99), type="timely")
    calm = dict(c("auto_loan", "Car loans", 60), type="evergreen")
    got, why, skipped = pick_topic(rep(news, calm), store, free_writer=False, today=NOV)
    assert got["key"] == "auto_loan" and any("news limit" in k for k in skipped)
    assert any("evergreen" in w for w in why)


def test_launch_list_waits_for_approval_then_comes_first_with_checked_facts(settings, store, monkeypatch, tmp_path):
    from glivarao.studio import launch_plan
    from glivarao.studio.planner import plan_next

    store.kv_set("launch_done", "[1, 2]")                       # progress on the OLD list
    monkeypatch.setattr(launch_plan, "verify_facts", lambda v, session=None: (
        v.facts[1:], [(v.facts[0], "DROPPED: '3-3/4 to 4 percent' is no longer on the page")]))
    assert launch_plan.awaiting_approval(store)
    assert plan_next(settings, store, NOV, tmp_path, send=False) is None   # nothing planned before your ✅
    launch_plan.approve(store)                                  # the new list starts from video 1
    item = plan_next(settings, store, NOV, tmp_path, send=False)
    assert item.topic == launch_plan.LAUNCH[0].topic and item.card["launch"] == 1
    assert item.card["affiliate_category"] == "high-yield savings" and item.card["market"] == "US"
    assert any("DROPPED" in w for w in item.why)
    first = launch_plan.LAUNCH[0].facts[0].text
    assert first not in [f["text"] for f in item.card["launch_facts"]]     # a dropped fact never reaches the script
    assert launch_plan.done(store) == [1] and launch_plan.remaining(store) == 15
    assert len(launch_plan.LAUNCH) == 16 and len({v.slug for v in launch_plan.LAUNCH}) == 16
    from glivarao.studio.affiliates import CATEGORIES

    for v in launch_plan.LAUNCH:                              # every number in the list has an official US URL
        assert v.affiliate in CATEGORIES and P.pillar_of(v.key) is not None, v.slug
        for f in v.facts:
            assert f.url.startswith("https://") and any(d in f.url for d in (
                ".gov", "annualcreditreport.com", "newyorkfed.org", "federalreserve.gov", "freddiemac.com")), f.url


def test_launch_list_approval_button_in_telegram(settings, store):
    from dataclasses import replace

    from glivarao.publish.telegram import poll_decisions
    from glivarao.studio import launch_plan
    from tests.conftest import FakeTelegramSession

    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42")
    tg = FakeTelegramSession()
    from glivarao.publish.telegram import TelegramClient

    client = TelegramClient("T", session=tg)
    launch_plan.send_for_approval(s, store, client)
    sent = tg.calls[-1][1]
    assert "US-only" in sent["text"] and sent["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == \
        f"launch:{launch_plan.VERSION}"
    tg.updates = [{"update_id": 1, "callback_query": {"id": "c1", "from": {"id": 42}, "data": f"launch:{launch_plan.VERSION}",
                                                      "message": {"chat": {"id": 42}}}}]
    poll_decisions(store, s, client)
    assert launch_plan.approved(store) and launch_plan.done(store) == []
    assert any("still PAUSED" in str(c[1]) for c in tg.calls)


def test_taxes_favoured_in_tax_season_and_series_name():
    t = P.PILLARS["taxes"]
    assert P.priority_bonus(t, ["debt"], JAN)[0] > P.priority_bonus(t, ["debt"], NOV)[0] + 20
    assert P.series_for("income_tax", date(2026, 12, 5)) == "Tax Season 2027"
    assert P.series_for("income_tax", JAN) == "Tax Season 2027"
    assert P.series_for("income_tax", date(2026, 7, 1)) == "Tax Smart"
    assert P.series_for("credit_card", NOV) == "Money Traps" and P.series_for("bank_fees", NOV) == "Money Traps"
    # in tax season taxes may take 3 of the last 5, but never twice in a row
    assert P.rotation_block(t, ["taxes", "debt", "taxes", "budget"], JAN) is None
    assert P.rotation_block(t, ["taxes", "debt", "taxes", "budget"], NOV) is not None
    assert P.rotation_block(t, ["debt", "taxes"], JAN) == "same pillar as the previous video"


def test_tax_topic_wins_in_january(store):
    hist(store, "scams")
    r = rep(c("hysa", "High-yield savings accounts", 80), c("income_tax", "Personal income taxes and refunds", 70))
    assert pick_topic(r, store, free_writer=False, today=JAN)[0]["key"] == "income_tax"
    store.kv_set("used_topics", "[]")
    hist(store, "scams")
    assert pick_topic(r, store, free_writer=False, today=date(2026, 7, 1))[0]["key"] == "hysa"


def _meta(job, **kw):
    from pathlib import Path

    p = Path(job.video_path).parent / "metadata.json"
    m = json.loads(p.read_text())
    m.update(kw)
    p.write_text(json.dumps(m))


def test_series_links_end_screen_and_affiliates_in_pack(settings, store, tmp_path):
    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42", telegram_max_upload_mb=1900,
                affiliate_disclosure="Disclosure: some links may be affiliate links.")
    tg = RecTG()
    ep1 = approved_job(s, store, tmp_path)
    _meta(ep1, series="Money Traps", pillar="debt", description="Body\n\nDisclosure: some links may be affiliate links.")
    send_pack(ep1, s, store, tg)
    pack_msg = max(int(k) for k in json.loads(store.kv_get("pack_messages", "{}")))
    # you upload, then reply to the pack with the link
    assert handle_message({"text": "https://youtu.be/abc123", "reply_to_message": {"message_id": pack_msg}},
                          store, s, tg) == "link"
    assert handle_message({"text": "/affiliate monarch https://aff.example/exp"}, store, s, tg) == "affiliate_add"
    assert handle_message({"text": "/playlist money traps https://www.youtube.com/playlist?list=PL123"},
                          store, s, tg) == "playlist"
    tg2 = RecTG()
    ep2 = approved_job(s, store, tmp_path)
    _meta(ep2, series="Money Traps", pillar="debt", topic_key="credit_card",
          description="Body two\n\nDisclosure: some links may be affiliate links.")
    send_pack(ep2, s, store, tg2)
    texts = "\n".join(tg2.texts())
    assert "episode 2" in texts
    desc = next(t for t in tg2.texts() if t.startswith("<b>DESCRIPTION"))
    assert "https://youtu.be/abc123" in desc and "PL123" in desc and "aff.example/exp" in desc
    assert desc.index("aff.example/exp") < desc.index("Disclosure: some links")      # disclosure next to links
    assert "Choose specific video" in texts and "abc123" in texts
    assert "Rocket Money" in texts and "placeholders" in texts      # not approved yet: listed, not in the text


def test_links_without_reply_go_to_newest_unlinked_and_bad_input_is_explained(settings, store, tmp_path):
    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42")
    tg = RecTG()
    assert handle_message({"text": "https://youtu.be/zzz"}, store, s, tg) == "link_unknown"
    S.record_episode(store, "J1", "Scam Alert", "scams", "Scam one", "long", NOV)
    assert handle_message({"text": "https://youtu.be/zzz"}, store, s, tg) == "link"
    assert S.episodes(store)[0]["url"] == "https://youtu.be/zzz"
    assert handle_message({"text": "/affiliate coinbase https://x.example"}, store, s, tg) == "affiliate_help"
    assert handle_message({"text": "/affiliate wise http://insecure.example"}, store, s, tg) == "affiliate_help"
    assert handle_message({"text": "/affiliate"}, store, s, tg) == "affiliate_list"
    assert "placeholder" in tg.texts()[-1] and "Rocket Dollar" in tg.texts()[-1]


def test_affiliates_one_or_two_per_long_video_none_in_shorts(store):
    from glivarao.studio import affiliates as A

    for k in ("rocketmoney", "monarch", "freetaxusa", "turbotax"):
        A.set_link(store, k, f"https://aff.example/{k}")
    links, _ = A.for_video(store, "cost_of_living", "budget", "long")
    assert [n for n, _ in links] == ["Rocket Money", "Monarch Money"]           # max 2, topic match first
    assert A.for_video(store, "tax_filing", "taxes", "long")[0][0][0] == "FreeTaxUSA"
    assert A.for_video(store, "cost_of_living", "budget", "short") == ([], [])  # never in Shorts
    assert A.for_video(store, "scams", "scams", "long") == ([], [])             # nothing fits: no link
    A.set_link(store, "monarch", None)
    assert len(A.for_video(store, "budgeting", "budget", "long")[0]) == 1


def test_free_writer_can_make_tax_videos_without_unsourced_claims(store):
    from glivarao.compliance import check_script
    from glivarao.content.brief import build_brief
    from glivarao.content.format_writer import write_long_format
    from glivarao.daily_v2 import finance_only_check
    from glivarao.studio import factcheck
    from glivarao.studio.formats import eligible

    b = build_brief(c("tax_refund", "Tax refunds and refund delays"), JAN)
    assert b.family == "tax"
    for style in eligible(b):
        s = write_long_format(b, style)
        assert finance_only_check(s)[0], style
        assert not factcheck.needs_source(factcheck.check_claims(s, b, "")), style
        assert check_script(s, enforce_length=False).ok, (style, check_script(s, enforce_length=False).errors)
    # the free writer is allowed to pick tax topics now, and in tax season taxes may return after one video
    hist(store, "income_tax", "scams")
    r = rep(c("tax_credits", "Tax credits (EITC, Child Tax Credit)", 90), c("hysa", "High-yield savings", 60))
    assert pick_topic(r, store, free_writer=True, today=JAN)[0]["key"] == "tax_credits"
