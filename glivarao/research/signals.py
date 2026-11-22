"""Fresh signals for automatic topic selection (each item keeps its source URL):

* Official news: Federal Reserve press releases (RSS), CFPB newsroom + blog (RSS), IRS news releases (newsroom page).
* Google Trends: daily trending searches for the US (public RSS), with their linked news articles.
* Search questions: Google search suggestions for a topic ("how...", "should I...", "is...").

BLS, FTC and some news sites refuse automated requests from servers (HTTP 403); BLS data series are available
through FRED (api.stlouisfed.org) when FRED_API_KEY is set. Every collector fails soft: a source that is down
just contributes nothing that day, and the report says so.
"""
from __future__ import annotations

import email.utils
import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

from .sources import SourceResult

BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) GLIVARAO-research/0.2"
RSS_FEEDS = [
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("CFPB newsroom", "https://www.consumerfinance.gov/about-us/newsroom/feed/"),
    ("CFPB blog", "https://www.consumerfinance.gov/about-us/blog/feed/"),
]
IRS_NEWS = "https://www.irs.gov/newsroom/news-releases-for-current-month"
TRENDS_RSS = "https://trends.google.com/trending/rss?geo={geo}"
SUGGEST = "https://suggestqueries.google.com/complete/search"
HT = "{https://trends.google.com/trending/rss}"


def _text(http, url: str, params: dict | None = None, save_as: str | None = None) -> str:
    http.calls += 1
    r = http.s.get(url, params=params, timeout=30, headers={"User-Agent": BROWSER_UA})
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() in ("iso-8859-1", "latin-1"):
        r.encoding = "utf-8"  # feeds that don't declare a charset are UTF-8 in practice
    if http.raw_dir and save_as:
        http.raw_dir.mkdir(parents=True, exist_ok=True)
        (http.raw_dir / save_as).write_text(r.text)
    return r.text


def _date(s: str) -> date | None:
    try:
        return email.utils.parsedate_to_datetime(s).date()
    except (TypeError, ValueError):
        return None


def _xml(doc) -> ET.Element:
    if isinstance(doc, bytes):
        doc = doc.decode("utf-8", "replace")
    return ET.fromstring(doc.lstrip("\ufeff \r\n\t").encode())  # some feeds start with a byte-order mark


def parse_rss(xml: str, source: str) -> list[dict]:
    root = _xml(xml)
    out = []
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        d = _date(it.findtext("pubDate") or "")
        desc = re.sub(r"<[^>]+>", " ", html.unescape(it.findtext("description") or ""))
        if title and link:
            out.append({"source": source, "title": title, "url": link, "date": d.isoformat() if d else "",
                        "summary": re.sub(r"\s+", " ", desc).strip()[:400]})
    return out


IRS_ITEM = re.compile(r'<a href="(/newsroom/[a-z0-9-]+)" rel="bookmark">\s*<span>([^<]+)</span>.*?'
                      r'field__item">\s*(IR-\d{4}-\d+), ([A-Z][a-z]{2,4})\.? (\d{1,2}), (\d{4}) — ([^<]+)<', re.S)


def parse_irs(page: str) -> list[dict]:
    out = []
    for path, title, ir, mon, day, year, abstract in IRS_ITEM.findall(page):
        try:
            d = datetime.strptime(f"{mon[:3]} {day} {year}", "%b %d %Y").date().isoformat()
        except ValueError:
            d = ""
        out.append({"source": f"IRS ({ir})", "title": html.unescape(title.strip()), "url": "https://www.irs.gov" + path,
                    "date": d, "summary": html.unescape(abstract.strip())[:400]})
    return out


def official_news(http, today: date, days: int = 30) -> SourceResult:
    items, notes, ok_any = [], [], False
    for name, url in RSS_FEEDS:
        try:
            items += parse_rss(_text(http, url, save_as=f"rss_{name.replace(' ', '_')}.xml"), name)
            ok_any = True
        except Exception as exc:  # noqa: BLE001  (a feed being down must not stop research)
            notes.append(f"{name}: {type(exc).__name__}")
    try:
        items += parse_irs(_text(http, IRS_NEWS, save_as="irs_news.html"))
        ok_any = True
    except Exception as exc:  # noqa: BLE001
        notes.append(f"IRS: {type(exc).__name__}")
    cutoff = (today - timedelta(days=days)).isoformat()
    items = [i for i in items if not i["date"] or i["date"] >= cutoff]
    detail = f"{len(items)} official items in {days} days" + (f" (unavailable: {', '.join(notes)})" if notes else "")
    return SourceResult("Official news (Fed, CFPB, IRS)", ok_any, detail, items, 0)


def parse_trends(xml: str, geo: str) -> list[dict]:
    root = _xml(xml)
    out = []
    for it in root.iter("item"):
        traffic = re.sub(r"[^\d]", "", it.findtext(f"{HT}approx_traffic") or "") or "0"
        news = [{"title": html.unescape(n.findtext(f"{HT}news_item_title") or ""),
                 "url": n.findtext(f"{HT}news_item_url") or "", "source": n.findtext(f"{HT}news_item_source") or ""}
                for n in it.findall(f"{HT}news_item")]
        d = _date(it.findtext("pubDate") or "")
        out.append({"query": (it.findtext("title") or "").strip(), "traffic": int(traffic), "geo": geo,
                    "date": d.isoformat() if d else "", "news": news[:3],
                    "url": f"https://trends.google.com/trends/explore?geo={geo}&q=" +
                           (it.findtext("title") or "").strip().replace(" ", "+")})
    return out


def google_trends(http) -> SourceResult:
    items, notes = [], []
    for geo in ("US",):  # US-only channel
        try:
            items += parse_trends(_text(http, TRENDS_RSS.format(geo=geo), save_as=f"trends_{geo}.xml"), geo)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{geo}: {type(exc).__name__}")
    return SourceResult("Google Trends (daily trending searches, US + CA)", bool(items),
                        f"{len(items)} trending searches" + (f" (unavailable: {', '.join(notes)})" if notes else ""),
                        items, 0)


SEED_PREFIXES = ("how", "should i", "is")


def seed_term(label: str) -> str:
    """'Credit cards, interest and fees' -> 'credit cards'; '401(k) plans and employer matching' -> '401(k) plans'."""
    t = re.split(r",| and | vs\.? | \(", label)[0].strip().lower()
    return t if len(t) > 2 else label.lower()


def search_questions(http, labels: dict[str, str], delay: float = 0.25) -> SourceResult:
    """key -> list of real search suggestions (questions people type), for each topic label."""
    out, failed = {}, 0
    for key, label in labels.items():
        term, got = seed_term(label), []
        for p in SEED_PREFIXES:
            try:
                http.calls += 1
                r = http.s.get(SUGGEST, params={"client": "firefox", "hl": "en", "gl": "us", "q": f"{p} {term}"},
                               timeout=20, headers={"User-Agent": BROWSER_UA})
                r.raise_for_status()
                got += [s for s in r.json()[1] if s.lower() != f"{p} {term}"]
            except Exception:  # noqa: BLE001
                failed += 1
            time.sleep(delay)
        if got:
            out[key] = list(dict.fromkeys(got))[:15]
    return SourceResult("Google search suggestions (questions people search for)", bool(out),
                        f"{sum(len(v) for v in out.values())} questions for {len(out)} topics"
                        + (f" ({failed} requests failed)" if failed else ""), [out], 0)


def search_url(q: str) -> str:
    return "https://www.google.com/search?q=" + q.replace(" ", "+")


__all__ = ["official_news", "google_trends", "search_questions", "parse_rss", "parse_irs", "parse_trends",
           "seed_term", "search_url"]
