"""Evergreen rule: rank by steady long-term demand (Google Trends 12m/5y stability, YouTube suggestions), not spikes;
75% evergreen / 25% timely with at most 1 date-bound video a week; evergreen titles/scripts carry no dates;
launch list: at most 2 time-sensitive videos."""
import json
from datetime import date, timedelta

from glivarao.compliance import check_script, evergreen_issues
from glivarao.research.engine import evergreen_score
from glivarao.research.signals import evergreen_signals, stability
from glivarao.scriptgen.offline import generate_offline
from glivarao.studio import launch_plan
from glivarao.studio import pillars as P
from glivarao.studio.autopick import pick_topic


def test_stability_and_evergreen_score_prefer_steady_demand():
    steady = stability([60, 62, 58, 61, 63, 59, 60, 62, 61, 60, 58, 62])
    spiky = stability([5, 4, 6, 5, 100, 5, 4, 6, 5, 4, 5, 6])
    assert steady["cv"] < 0.05 and spiky["spike"] > 10
    s_steady = evergreen_score({"trends_t5y_cv": steady["cv"], "trends_t12m_cv": steady["cv"],
                                "trends_t12m_spike": steady["spike"], "youtube_suggestions": 10})
    s_spiky = evergreen_score({"trends_t5y_cv": spiky["cv"], "trends_t12m_cv": spiky["cv"],
                               "trends_t12m_spike": spiky["spike"], "youtube_suggestions": 2})
    assert s_steady[0] >= 9 and s_spiky[0] <= 3 and "Google Trends" in s_steady[1]
    assert evergreen_score({}) is None


class _Resp:
    def __init__(self, text="", status=200, js=None):
        self.text, self.status_code, self._js = text, status, js

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)

    def json(self):
        return self._js


class _FakeGoogle:
    def __init__(self, trends_status=200):
        self.trends_status = trends_status

    def get(self, url, params=None, timeout=None, headers=None):
        if "suggestqueries" in url:
            return _Resp(js=[params["q"], [f"{params['q']} {i}" for i in range(8)]])
        if self.trends_status != 200:
            return _Resp(status=self.trends_status)
        if url.endswith("/explore"):
            return _Resp(")]}'\n" + json.dumps({"widgets": [{"id": "TIMESERIES", "request": {}, "token": "t"}]}))
        pts = [{"value": [v], "hasData": [True]} for v in [50, 52, 48, 51, 49, 50, 53, 47, 50, 51]]
        return _Resp(")]}',\n" + json.dumps({"default": {"timelineData": pts}}))


def test_evergreen_signals_collect_trends_and_youtube_and_fail_soft():
    http = type("H", (), {"s": _FakeGoogle(), "calls": 0})()
    res = evergreen_signals(http, {"credit_score": "Credit scores"}, sleep=lambda s: None)
    d = res.items[0]["credit_score"]
    assert d["t12m"]["cv"] < 0.1 and d["t5y"]["points"] == 10 and d["yt_suggestions"] == 8
    http = type("H", (), {"s": _FakeGoogle(429), "calls": 0})()
    res = evergreen_signals(http, {"a": "Credit scores", "b": "Mortgages"}, sleep=lambda s: None)
    assert "rate-limited" in res.detail and res.items[0]["b"]["yt_suggestions"] == 8   # YouTube still counted


def test_trends_results_are_cached_for_30_days(tmp_path):
    cache = tmp_path / "trends_cache.json"
    http = type("H", (), {"s": _FakeGoogle(), "calls": 0})()
    evergreen_signals(http, {"credit_score": "Credit scores"}, sleep=lambda s: None, cache_path=cache,
                      today=date(2026, 11, 22))
    http = type("H", (), {"s": _FakeGoogle(429), "calls": 0})()           # Google refuses today...
    res = evergreen_signals(http, {"credit_score": "Credit scores"}, sleep=lambda s: None, cache_path=cache,
                            today=date(2026, 12, 10))
    assert res.items[0]["credit_score"]["t5y"]["points"] == 10 and "1 topics from the 30-day cache" in res.detail


def test_evergreen_scripts_have_no_dates_or_this_week_wording():
    s = generate_offline("Credit card interest", "long")
    assert evergreen_issues(s, 2026) == []
    bad = s.model_copy(update={"title": "Credit card rates in November 2026: what changed this week"})
    issues = " | ".join(evergreen_issues(bad, 2026))
    assert "2026" in issues and "November" in issues and "this week" in issues
    ok = s.model_copy(update={"title": "What caused the 2008 financial crisis"})
    assert evergreen_issues(ok, 2026) == []                                # history is fine
    scenes = list(s.scenes)
    scenes[1] = scenes[1].model_copy(update={"narration": "Right now the average card rate is 22.36%."})
    issues = evergreen_issues(s.model_copy(update={"scenes": scenes}), 2026)
    assert any("as of" in i for i in issues)
    assert any("Not evergreen" in e for e in check_script(bad, enforce_length=True, evergreen=True).errors)
    assert not any("Not evergreen" in e for e in check_script(bad, enforce_length=True, evergreen=False).errors)


def test_at_most_one_date_bound_video_per_week(store):
    today = date(2026, 12, 3)
    hist = [[(today - timedelta(days=d)).isoformat(), k, "", "", "", n]
            for d, k, n in ((9, "credit_score", False), (8, "budgeting", False), (5, "income_tax", True))]
    store.kv_set("used_topics", json.dumps(hist))
    card = lambda key, typ, score: {"key": key, "topic": key, "category": "Credit and Debt", "market": "US",  # noqa
                                    "score": score, "confidence": "high", "type": typ, "news": typ == "timely",
                                    "why": [], "sources": ["x"], "rank": 1}
    report = {"ranked": [card("credit_card", "timely", 99), card("student_loan", "evergreen", 70)]}
    c, why, skipped = pick_topic(report, store, free_writer=False, today=today)
    assert c["key"] == "student_loan" and any("per week" in k or "news video in" in k for k in skipped), skipped
    # the 1-in-4 rule alone would allow it (3 evergreen videos since), but it is still the same week
    hist = [[(today - timedelta(days=6)).isoformat(), "income_tax", "", "", "", True]] + \
        [[(today - timedelta(days=d)).isoformat(), k, "", "", "", False]
         for d, k in ((4, "budgeting"), (3, "credit_score"), (2, "hysa"))]
    store.kv_set("used_topics", json.dumps(hist))
    c, why, skipped = pick_topic(report, store, free_writer=False, today=today)
    assert c["key"] == "student_loan" and any("per week" in k for k in skipped), skipped
    assert P.NEWS_EVERY == 4 and P.NEWS_PER_WEEK == 1


def test_launch_list_is_evergreen_first_with_at_most_two_timely():
    timely = [v for v in launch_plan.LAUNCH if v.news]
    assert len(timely) <= launch_plan.MAX_TIMELY == 2 and len(launch_plan.LAUNCH) == 16
    pos = [v.n for v in timely]
    assert all(b - a >= 4 for a, b in zip(pos, pos[1:]))                 # never 2 in a week at ~4 long a week
    for v in launch_plan.LAUNCH:
        if not v.news:
            fake = generate_offline("x", "long").model_copy(update={"title": v.topic})
            assert evergreen_issues(fake, 2026) == [], v.topic
            assert all("as of" in f.text.lower() or not any(ch.isdigit() for ch in f.text) or
                       "2008" in f.text or "For 2027" in f.text or "2022" in f.text or "since" in f.text.lower()
                       or "63 percent" in f.text or "$250,000" in f.text or "March 2026" in f.text
                       or "90 days" in f.text or "$208 billion" in f.text or "third quarter" in f.text
                       or "100% and 400%" in f.text for f in v.facts), v.slug
    assert {"how-credit-scores-work", "what-caused-2008", "how-the-fed-affects-you", "national-debt-problem",
            "how-bank-failures-work", "snowball-vs-avalanche", "why-houses-expensive", "what-happens-in-recession",
            "get-out-of-card-debt"} <= {v.slug for v in launch_plan.LAUNCH}
