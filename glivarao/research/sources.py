"""Data collectors. Official APIs and public datasets only (no HTML scraping).

Every collector returns a SourceResult that records whether it ran, what it fetched and any error, so
the report can state exactly which numbers were measured. Raw responses are saved for auditing.
"""
from __future__ import annotations

import html
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)
UA = "GLIVARAO-research/0.1 (finance topic research; contact via channel)"


@dataclass
class SourceResult:
    name: str
    ok: bool
    detail: str
    items: list = field(default_factory=list)
    calls: int = 0


class Http:
    def __init__(self, raw_dir: Path | None = None, session=None):
        self.s = session or requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip"})
        self.raw_dir = raw_dir
        self.calls = 0

    def get_json(self, url: str, params: dict | None = None, save_as: str | None = None, timeout: int = 60):
        self.calls += 1
        for attempt in range(3):
            try:
                r = self.s.get(url, params=params, timeout=timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(2 * (attempt + 1))
                    continue
                r.raise_for_status()
                data = r.json()
                if self.raw_dir and save_as:
                    self.raw_dir.mkdir(parents=True, exist_ok=True)
                    (self.raw_dir / save_as).write_text(json.dumps(data))
                return data
            except requests.RequestException as exc:
                if attempt == 2:
                    raise RuntimeError(f"{type(exc).__name__} for {url.split('?')[0]}") from None
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"gave up on {url.split('?')[0]}")


# ------------------------------------------------------------------ Stack Exchange (Personal Finance & Money)
SE_API = "https://api.stackexchange.com/2.3/questions"


def stackexchange(http: Http, today: date, recent_days: int = 365, pages: int = 5) -> SourceResult:
    """Questions from the last year (most-voted) plus the last 30 days (newest)."""
    out, seen = [], set()
    try:
        plans = [("votes", recent_days, pages), ("creation", 30, 2)]
        for sort, days, npages in plans:
            frm = int(datetime.combine(today - timedelta(days=days), datetime.min.time(),
                                       tzinfo=timezone.utc).timestamp())
            to = int(datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc).timestamp())
            for page in range(1, npages + 1):
                d = http.get_json(SE_API, {"site": "money", "sort": sort, "order": "desc", "pagesize": 100,
                                           "page": page, "fromdate": frm, "todate": to, "filter": "default"},
                                  save_as=f"se_{sort}_{page}.json")
                for q in d.get("items", []):
                    if q["question_id"] in seen:
                        continue
                    seen.add(q["question_id"])
                    out.append({"id": q["question_id"], "title": html.unescape(q["title"]), "tags": q["tags"],
                                "views": q["view_count"], "score": q["score"], "answers": q["answer_count"],
                                "created": q["creation_date"], "link": q["link"]})
                if not d.get("has_more"):
                    break
                if d.get("backoff"):
                    time.sleep(int(d["backoff"]))
        return SourceResult("Stack Exchange: Personal Finance & Money", True,
                            f"{len(out)} questions (last {recent_days} days)", out, http.calls)
    except Exception as exc:  # report, don't crash the whole run
        return SourceResult("Stack Exchange: Personal Finance & Money", False, str(exc), out, http.calls)


# ------------------------------------------------------------------ CFPB Consumer Complaint Database (CC0)
CFPB_API = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"


def _cfpb_issue_counts(http: Http, start: date, end: date, tag: str, product: str | None = None) -> dict:
    params = {"size": 0, "no_highlight": "true", "date_received_min": start.isoformat(),
              "date_received_max": end.isoformat()}
    if product:
        params["product"] = product
    d = http.get_json(CFPB_API, params, save_as=f"cfpb_{tag}.json")
    aggs = d["aggregations"]
    issues = {}
    for b in aggs["issue"]["issue"]["buckets"]:
        subs = {s["key"]: s["doc_count"] for s in b.get("sub_issue.raw", {}).get("buckets", [])}
        issues[b["key"]] = {"count": b["doc_count"], "subs": subs}
    products = {b["key"]: b["doc_count"] for b in aggs["product"]["product"]["buckets"]}
    return {"issues": issues, "products": products}


def cfpb(http: Http, today: date, window_days: int = 90) -> SourceResult:
    """Complaint counts by issue: last `window_days` vs the same window one year earlier (seasonality-neutral)."""
    name = "CFPB Consumer Complaint Database (US)"
    try:
        end = today - timedelta(days=1)
        start = end - timedelta(days=window_days)
        cur = _cfpb_issue_counts(http, start, end, "current")
        prev = _cfpb_issue_counts(http, start - timedelta(days=365), end - timedelta(days=365), "year_ago")
        # map each issue to its main product (issue names are product-specific in the CFPB taxonomy)
        best: dict[str, tuple[int, str]] = {}  # issue -> (count, product where it occurs most)
        for k, prod in enumerate(list(cur["products"])[:12]):
            per = _cfpb_issue_counts(http, start, end, f"product_{k}", product=prod)
            for iss, v in per["issues"].items():
                if v["count"] > best.get(iss, (0, ""))[0]:
                    best[iss] = (v["count"], prod)
        issue_product = {iss: prod for iss, (_, prod) in best.items()}
        items = []
        for iss, v in cur["issues"].items():
            before = prev["issues"].get(iss, {}).get("count", 0)
            top_sub = max(v["subs"].items(), key=lambda kv: kv[1])[0] if v["subs"] else ""
            items.append({"issue": iss, "product": issue_product.get(iss, ""), "count": v["count"],
                          "year_ago": before, "top_sub_issue": top_sub, "subs": v["subs"],
                          "window": f"{start.isoformat()}..{end.isoformat()}",
                          "link": "https://www.consumerfinance.gov/data-research/consumer-complaints/search/"
                                  f"?date_received_min={start.isoformat()}&date_received_max={end.isoformat()}"
                                  f"&issue={quote(iss)}"})
        return SourceResult(name, True, f"{len(items)} complaint issues, {start}..{end} vs one year earlier", items,
                            http.calls)
    except Exception as exc:
        return SourceResult(name, False, str(exc), [], http.calls)


# ------------------------------------------------------------------ Wikipedia pageviews (Wikimedia REST API)
WM = "https://wikimedia.org/api/rest_v1/metrics/pageviews"


def wiki_top(http: Http, today: date, days: int = 7) -> SourceResult:
    """Most-read English Wikipedia articles for each of the last `days` days (discovery of trending concepts)."""
    name = "Wikipedia most-read articles"
    out: dict[str, int] = {}
    got, failed = 0, []
    for k in range(1, days + 1):  # one failed day must not discard the others
        d = today - timedelta(days=k)
        try:
            data = http.get_json(f"{WM}/top/en.wikipedia/all-access/{d.year}/{d.month:02d}/{d.day:02d}",
                                 save_as=f"wiki_top_{d.isoformat()}.json")
            for a in data["items"][0]["articles"]:
                out[a["article"]] = out.get(a["article"], 0) + a["views"]
            got += 1
        except Exception:
            failed.append(d.isoformat())
    items = [{"article": k, "views_7d": v} for k, v in sorted(out.items(), key=lambda kv: -kv[1])]
    note = f"{len(items)} distinct top articles over {got} of {days} days"
    if failed:
        note += f" (unavailable: {', '.join(failed)})"
    return SourceResult(name, got > 0, note, items, http.calls)


def wiki_series(http: Http, article: str, today: date, days: int = 400) -> list[int] | None:
    """Daily human pageviews for one article (None if the article doesn't exist)."""
    end = today - timedelta(days=1)
    start = end - timedelta(days=days)
    url = (f"{WM}/per-article/en.wikipedia/all-access/user/{quote(article, safe='')}/daily/"
           f"{start:%Y%m%d}/{end:%Y%m%d}")
    try:
        d = http.get_json(url, save_as=f"wiki_{article[:60].replace('/', '_')}.json")
        return [i["views"] for i in d.get("items", [])]
    except RuntimeError:
        return None


# ------------------------------------------------------------------ YouTube Data API (needs a key)
def youtube_unavailable(reason: str) -> SourceResult:
    return SourceResult("YouTube Data API (competitor views & competition)", False, reason)
