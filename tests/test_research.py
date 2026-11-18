"""R1 research engine tests. Offline: all HTTP is faked."""
import json
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import pytest

from glivarao.research.engine import build_candidates, compute_metrics, eligible, score_all
from glivarao.research.finance_filter import gate, market_of, match_concepts
from glivarao.research.run import run_research

TODAY = date(2026, 11, 18)


def ts(days_ago: int) -> int:
    return int(datetime(2026, 11, 18, tzinfo=timezone.utc).timestamp()) - days_ago * 86400


@pytest.mark.parametrize("text,ok", [
    ("How do I pay off credit card debt faster?", True),
    ("Is a dealer offering a rebate for financing a car a red flag?", True),
    ("What happens to a mortgage when the owner died?", True),
    ("Senate passes new bill on election funding", False),
    ("Federal Reserve signals rate cut as recession fears grow", False),
    ("Tariffs push up prices worldwide", False),
    ("Taylor Swift album breaks records", False),
    ("Best hiking trails in Colorado", False),
])
def test_finance_gate(text, ok):
    assert gate(text)[0] is ok


def test_off_topic_markers_apply_even_to_finance_sources():
    assert not gate("Will the election change my 401(k)?", finance_source=True)[0]
    assert gate("Can I remove GnuCash from my computer?", finance_source=True)[0]


def test_market_comes_from_the_subject():
    assert market_of("question tagged united-states", match_concepts("credit card interest")) == "both"
    assert market_of("", match_concepts("Roth IRA contribution")) == "US"
    assert market_of("", match_concepts("TFSA room")) == "CA"
    assert market_of("my pension in the united-kingdom", []) == "other"


SE = [
    {"id": i, "title": t, "tags": tags, "views": v, "score": 3, "answers": 2, "created": ts(d),
     "link": f"https://money.stackexchange.com/q/{i}"}
    for i, (t, tags, v, d) in enumerate([
        ("Why does my credit card balance never go down?", ["credit-card", "united-states"], 4000, 40),
        ("How is credit card interest calculated?", ["credit-card"], 2500, 10),
        ("Should I pay off my credit card or invest?", ["credit-card", "investing"], 1800, 100),
        ("What is a good credit card APR?", ["credit-card", "canada"], 900, 200),
        ("Is a Roth IRA better than a traditional IRA?", ["roth-ira", "united-states"], 3000, 60),
        ("Roth conversion question", ["roth-ira"], 1200, 120),
        ("Can I deduct mortgage interest in the UK?", ["mortgage", "united-kingdom"], 5000, 30),
        ("Who will win the election and what about my stocks?", ["stocks"], 9000, 5),
    ], start=1)
]
CFPB = [{"issue": "Problem with a purchase shown on your statement", "product": "Credit card", "count": 8000,
         "year_ago": 5000, "top_sub_issue": "Credit card company isn't resolving a dispute", "subs": {},
         "window": "", "link": "https://example.test/cfpb"},
        {"issue": "Incorrect information on your report", "product": "Credit reporting", "count": 900000,
         "year_ago": 800000, "top_sub_issue": "Information belongs to someone else", "subs": {}, "window": "",
         "link": "https://example.test/cfpb2"},
        {"issue": "Struggling to pay mortgage", "product": "Mortgage", "count": 2600, "year_ago": 1500,
         "top_sub_issue": "... modification, forbearance, short sale, bankruptcy, or foreclosure", "subs": {},
         "window": "", "link": "https://example.test/cfpb3"}]


def test_candidates_scoring_and_rejections():
    cands, rejected = build_candidates(SE, CFPB, [{"article": "How_to_Rob_a_Bank_(2026_film)", "views_7d": 1}])
    reasons = {r.text: r.reason for r in rejected}
    assert "not US/Canada" in reasons["Can I deduct mortgage interest in the UK?"]
    assert "politics" in reasons["Who will win the election and what about my stocks?"]
    assert "entertainment" in reasons["How to Rob a Bank (2026 film)"]
    assert "bankruptcy" not in cands  # sub-issue text no longer creates false matches
    assert "identity_theft" in cands  # ...but still detects identity theft
    for c in cands.values():
        compute_metrics(c, TODAY)
    score_all(list(cands.values()))
    cc = cands["credit_card"]
    assert cc.metrics["se_questions_365d"] == 4 and cc.metrics["cfpb_yoy_change"] == pytest.approx(0.6)
    assert cc.market == "both" and cc.scores["demand"][1] == "MEASURED"
    assert cc.scores["potential_views"] == (None, "UNAVAILABLE", "needs YouTube Data API key")
    assert cc.confidence != "high"  # can't be high without YouTube data
    assert cands["ira_roth"].market == "US" and eligible(cc)[0]
    assert all(0 <= c.total <= 100 for c in cands.values())
    # a topic with a single source can't be carried by estimates alone
    single = [c for c in cands.values() if len(c.sources) == 1 and not c.se]
    assert single and all(c.scores["curiosity"][0] == 3.0 for c in single)


class FakeSession:
    headers: dict = {}

    def __init__(self):
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        host, path = urlparse(url).netloc, urlparse(url).path
        if host == "api.stackexchange.com":
            body = {"items": [{"question_id": q["id"], "title": q["title"], "tags": q["tags"], "view_count": q["views"],
                               "score": 1, "answer_count": 1, "creation_date": q["created"], "link": q["link"]}
                              for q in SE] if params.get("page") == 1 else [], "has_more": False}
        elif host == "www.consumerfinance.gov":
            buckets = [{"key": i["issue"], "doc_count": i["count"],
                        "sub_issue.raw": {"buckets": [{"key": i["top_sub_issue"], "doc_count": i["count"]}]}}
                       for i in CFPB]
            body = {"aggregations": {"issue": {"issue": {"buckets": buckets}},
                                     "product": {"product": {"buckets": [{"key": "Credit card", "doc_count": 1}]}}}}
        elif "/top/" in path:
            body = {"items": [{"articles": [{"article": "Main_Page", "views": 9}, {"article": "Credit_score", "views": 50}]}]}
        else:
            body = {"items": [{"views": 100 + k} for k in range(401)]}
        return type("R", (), {"status_code": 200, "json": lambda self: body, "raise_for_status": lambda self: None})()


def test_run_research_writes_report(tmp_path):
    rep = run_research(TODAY, tmp_path, session=FakeSession())
    assert [s["ok"] for s in rep["sources"]] == [True, True, True, False, True]
    assert rep["ranked"] and rep["ranked"][0]["rank"] == 1 and rep["recommended"]
    md = (tmp_path / "2026-11-18.md").read_text()
    assert "Report only" in md and "UNAVAILABLE" in md and "will go viral" in md and "Recommended pick" in md
    data = json.loads((tmp_path / "2026-11-18.json").read_text())
    assert all(t["category"] for t in data["ranked"]) and (tmp_path / "raw" / "2026-11-18").exists()
