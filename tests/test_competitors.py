"""Competitor research: YouTube Data API simulated (no real calls, no key). Patterns only; scores feed the
research ranking; our titles are kept away from competitor titles."""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from glivarao.research import competitors as C

NOW = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)


def _iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


VIDEOS = [  # id, title, days ago, seconds, views
    ("v1", "Why Credit Card Interest Is Destroying Your Budget", 10, 900, 900_000),
    ("v2", "The $1 Trillion Credit Card Debt Problem Explained", 20, 1100, 600_000),
    ("v3", "How Buy Now Pay Later Traps You", 30, 700, 300_000),
    ("v4", "Why Your Credit Score Is Lying to You", 40, 840, 200_000),
    ("v5", "Index Funds Explained", 50, 1300, 20_000),
    ("v6", "Credit card hack #shorts", 5, 45, 50_000),
    ("old", "Old video", 200, 600, 1_000_000),
]


class FakeYT:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, dict(params), headers))
        if method == "search":
            body = {"items": [{"snippet": {"channelId": "UC" + params["q"][:3]}}]}
        elif method == "channels":
            body = {"items": [{"id": params["id"], "snippet": {"title": "Casual Finance"},
                               "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}},
                               "statistics": {"subscriberCount": "1500000"}}]}
        elif method == "playlistItems":
            body = {"items": [{"contentDetails": {"videoId": v, "videoPublishedAt": _iso(d)}}
                              for v, _, d, _, _ in VIDEOS]}
        elif method == "videos":
            ids = params["id"].split(",")
            body = {"items": [{"id": v, "snippet": {"title": t, "publishedAt": _iso(d),
                                                    "thumbnails": {"high": {"url": f"https://i.ytimg.com/{v}.jpg"}}},
                               "contentDetails": {"duration": f"PT{s // 60}M{s % 60}S"},
                               "statistics": {"viewCount": str(n)}} for v, t, d, s, n in VIDEOS if v in ids]}
        else:
            raise AssertionError(method)
        return type("R", (), {"status_code": 200, "json": lambda s: body})()


def test_run_collects_patterns_and_scores(settings, store, tmp_path):
    s = replace(settings, youtube_api_key="YTKEY", competitor_channels="Casual Finance")
    fake = FakeYT()
    rep = C.run(s, store, tmp_path, session=fake, now=NOW)
    assert all("YTKEY" not in json.dumps(p) and h == {"x-goog-api-key": "YTKEY"} for _, p, h in fake.calls)
    assert rep["long_videos"] == 5 and rep["shorts"] == 1                      # 200-day-old video excluded
    assert rep["topics"]["credit_card"]["videos"] == 2
    assert rep["concept_scores"]["credit_card"] > rep["concept_scores"].get("index_funds", 0)
    assert rep["titles"]["with_dollar"] == 0.2 and rep["length"]["median_minutes"] == 15.0
    assert (tmp_path / "latest.json").exists() and "Patterns only" in (tmp_path / f"{rep['date']}.md").read_text()
    # the name lookup (100 units) is cached: a second run doesn't search again
    fake2 = FakeYT()
    C.run(s, store, tmp_path, session=fake2, now=NOW)
    assert not any(m == "search" for m, _, _ in fake2.calls)


def test_scores_feed_research_and_titles_stay_original(tmp_path):
    rep = C.analyze([{"title": t, "seconds": s, "views_per_day": n / d, "views": n} for _, t, d, s, n in VIDEOS])
    rep.update({"days": 90, "all_titles": [t for _, t, *_ in VIDEOS]})
    score, why = C.potential_score("credit_card", rep)
    assert score > 5 and "competitors" in why
    assert C.potential_score("crypto", rep) is None
    assert C.too_similar("Why Credit Card Interest Is Destroying Your Budget!", rep)
    assert C.too_similar("The Minimum Payment Trap: What It Really Costs", rep) is None


def test_missing_key_is_a_clear_error(settings):
    with pytest.raises(C.YouTubeAPIError, match="YOUTUBE_API_KEY"):
        C.run(replace(settings, youtube_api_key=""), None)
