"""Competitor research (YouTube Data API v3, read-only, your own YOUTUBE_API_KEY).

    python -m glivarao competitors            # weekly via glivarao-competitors.timer

For a set of similar macro-finance channels (COMPETITOR_CHANNELS, default: Casual Finance and similar explainer
channels) it collects the videos of the last 90 days and reports PATTERNS, never content to copy:
  * topics: which of our research concepts their best videos are about, and how well those videos do
    (views per day), plus the most common title keywords;
  * titles: length, numbers, dollar amounts, questions, "you/your", years;
  * thumbnail text: word counts and common words (OCR, only if tesseract is installed);
  * length: median minutes, share under 10 / 10-20 / over 20 minutes; Shorts are counted separately.
Results feed the research ranking as the "potential views" score (reports/competitors/latest.json), and our
titles are checked so they are never close to a competitor's title.

Quota: channel lookup by name costs 100 units once (cached); each weekly run costs about 5 units per channel.
The free daily quota is 10,000 units. The key is sent in a header, never in the URL.
"""
from __future__ import annotations

import io
import json
import logging
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)
API = "https://www.googleapis.com/youtube/v3/"
DEFAULT_CHANNELS = ["Casual Finance", "How Money Works", "Economics Explained", "Money & Macro",
                    "The Plain Bagel", "Two Cents"]
STOP = set("the a an and or of to in on for is are was why how what your you with this that it its from at by be "
           "as not now no do does will can just about into than more most new vs who when where".split())
TITLE_SIMILAR = 0.6


class YouTubeAPIError(RuntimeError):
    pass


class YouTube:
    def __init__(self, api_key: str, session=None):
        if not api_key:
            raise YouTubeAPIError("YOUTUBE_API_KEY is not set (put it in .env with deploy/set-key.sh)")
        self._key, self.http = api_key, session or requests.Session()
        self.units = 0

    def get(self, method: str, cost: int = 1, **params) -> dict:
        r = self.http.get(API + method, params=params, headers={"x-goog-api-key": self._key}, timeout=30)
        self.units += cost
        if r.status_code != 200:
            reason = ""
            try:
                reason = r.json()["error"]["errors"][0]["reason"]
            except Exception:  # noqa: BLE001
                pass
            raise YouTubeAPIError(f"YouTube API {method}: HTTP {r.status_code} {reason}".strip())
        return r.json()


# --------------------------------------------------------------------------------------------- collection
def resolve_channel(yt: YouTube, name: str, store=None) -> dict | None:
    """'UC…' id, '@handle' or a channel name (name lookups are cached in the kv table: 100 units once)."""
    cache = json.loads(store.kv_get("yt_channels", "{}")) if store is not None else {}
    if name in cache:
        cid = cache[name]
    elif name.startswith("UC"):
        cid = name
    elif name.startswith("@"):
        items = yt.get("channels", part="id", forHandle=name).get("items", [])
        cid = items[0]["id"] if items else None
    else:
        items = yt.get("search", cost=100, part="snippet", type="channel", q=name, maxResults=1).get("items", [])
        cid = items[0]["snippet"]["channelId"] if items else None
    if not cid:
        return None
    if store is not None and name not in cache:
        cache[name] = cid
        store.kv_set("yt_channels", json.dumps(cache))
    items = yt.get("channels", part="snippet,contentDetails,statistics", id=cid).get("items", [])
    if not items:
        return None
    ch = items[0]
    return {"id": cid, "title": ch["snippet"]["title"], "uploads": ch["contentDetails"]["relatedPlaylists"]["uploads"],
            "subscribers": int(ch["statistics"].get("subscriberCount", 0) or 0)}


def _seconds(iso: str) -> int:
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    d, h, mi, s = (int(x or 0) for x in m.groups()) if m else (0, 0, 0, 0)
    return d * 86400 + h * 3600 + mi * 60 + s


def recent_videos(yt: YouTube, channel: dict, days: int = 90, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    ids, token = [], None
    for _ in range(6):  # up to 300 uploads
        kw = {"pageToken": token} if token else {}
        page = yt.get("playlistItems", part="contentDetails", playlistId=channel["uploads"], maxResults=50, **kw)
        batch = [(it["contentDetails"]["videoId"], it["contentDetails"].get("videoPublishedAt", "")) for it in
                 page.get("items", [])]
        ids += [v for v, p in batch if p and datetime.fromisoformat(p.replace("Z", "+00:00")) >= since]
        token = page.get("nextPageToken")
        if not token or (batch and batch[-1][1] and
                         datetime.fromisoformat(batch[-1][1].replace("Z", "+00:00")) < since):
            break
    out = []
    for i in range(0, len(ids), 50):
        for v in yt.get("videos", part="snippet,contentDetails,statistics", id=",".join(ids[i:i + 50])).get("items", []):
            pub = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
            age = max(1.0, (now - pub).total_seconds() / 86400)
            views = int(v["statistics"].get("viewCount", 0) or 0)
            thumbs = v["snippet"].get("thumbnails", {})
            out.append({"id": v["id"], "channel": channel["title"], "title": v["snippet"]["title"],
                        "published": pub.date().isoformat(), "seconds": _seconds(v["contentDetails"]["duration"]),
                        "views": views, "views_per_day": round(views / age, 1),
                        "thumbnail": (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("default") or {}).get("url", "")})
    return out


# --------------------------------------------------------------------------------------------- analysis
def _words(title: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9$%']+", title.lower()) if w not in STOP and len(w) > 2]


def title_patterns(titles: list[str]) -> dict:
    n = max(1, len(titles))
    share = lambda rx: round(sum(bool(re.search(rx, t, re.I)) for t in titles) / n, 2)  # noqa: E731
    return {"videos": len(titles), "median_chars": statistics.median([len(t) for t in titles]) if titles else 0,
            "median_words": statistics.median([len(t.split()) for t in titles]) if titles else 0,
            "with_number": share(r"\d"), "with_dollar": share(r"\$\d"), "question": share(r"\?"),
            "you_your": share(r"\byou(r)?\b"), "with_year": share(r"\b20\d\d\b"),
            "all_caps_word": share(r"\b[A-Z]{3,}\b"), "colon_or_dash": share(r"[:—–|]")}


def ocr_thumbnails(videos: list[dict], session=None, limit: int = 40) -> dict:
    """Thumbnail text via tesseract (optional). Returns {} if OCR isn't installed."""
    try:
        import pytesseract
        from PIL import Image
        pytesseract.get_tesseract_version()
    except Exception:  # noqa: BLE001
        return {}
    http = session or requests.Session()
    counts, words = [], {}
    for v in videos[:limit]:
        if not v.get("thumbnail"):
            continue
        try:
            img = Image.open(io.BytesIO(http.get(v["thumbnail"], timeout=20).content)).convert("L")
            text = pytesseract.image_to_string(img)
        except Exception:  # noqa: BLE001
            continue
        ws = [w for w in re.findall(r"[A-Za-z$0-9%]+", text) if len(w) > 1]
        counts.append(len(ws))
        for w in ws:
            if w.lower() not in STOP:
                words[w.upper()] = words.get(w.upper(), 0) + 1
    if not counts:
        return {}
    return {"thumbnails_read": len(counts), "median_words": statistics.median(counts),
            "no_text_share": round(sum(c == 0 for c in counts) / len(counts), 2),
            "common_words": sorted(words, key=lambda w: -words[w])[:15]}


def analyze(videos: list[dict]) -> dict:
    from .finance_filter import match_concepts

    longs = [v for v in videos if v["seconds"] > 70]
    shorts = [v for v in videos if 0 < v["seconds"] <= 70]
    mins = [v["seconds"] / 60 for v in longs]
    by_concept: dict[str, list[float]] = {}
    for v in longs:
        for c in match_concepts(v["title"])[:2]:
            by_concept.setdefault(c.key, []).append(v["views_per_day"])
    kw: dict[str, list[float]] = {}
    for v in longs:
        for w in set(_words(v["title"])):
            kw.setdefault(w, []).append(v["views_per_day"])
    top_kw = sorted(((w, len(vs), statistics.median(vs)) for w, vs in kw.items() if len(vs) >= 3),
                    key=lambda x: -x[2])[:25]
    med_all = statistics.median([v["views_per_day"] for v in longs]) if longs else 0
    concept_scores = {}
    for k, vs in by_concept.items():  # 0-10: how this topic performs vs the median competitor long video
        rel = statistics.median(vs) / med_all if med_all else 1.0
        concept_scores[k] = round(max(0.0, min(10.0, 5 + 2.5 * (rel - 1) + 0.5 * min(len(vs), 4))), 1)
    return {
        "long_videos": len(longs), "shorts": len(shorts),
        "length": {"median_minutes": round(statistics.median(mins), 1) if mins else None,
                   "under_10": round(sum(m < 10 for m in mins) / max(1, len(mins)), 2),
                   "10_to_20": round(sum(10 <= m <= 20 for m in mins) / max(1, len(mins)), 2),
                   "over_20": round(sum(m > 20 for m in mins) / max(1, len(mins)), 2)},
        "titles": title_patterns([v["title"] for v in longs]),
        "topics": {k: {"videos": len(vs), "median_views_per_day": round(statistics.median(vs), 1),
                       "score": concept_scores[k]} for k, vs in sorted(by_concept.items(), key=lambda x: -len(x[1]))},
        "keywords": [{"word": w, "videos": n, "median_views_per_day": round(m, 1)} for w, n, m in top_kw],
        "concept_scores": concept_scores, "median_views_per_day": med_all,
    }


# --------------------------------------------------------------------------------------------- run + use
def run(settings, store=None, out_dir: Path = Path("reports/competitors"), session=None,
        now: datetime | None = None) -> dict:
    yt = YouTube(settings.youtube_api_key, session)
    names = [n.strip() for n in settings.competitor_channels.split(",") if n.strip()] or DEFAULT_CHANNELS
    channels, videos, missing = [], [], []
    for name in names:
        try:
            ch = resolve_channel(yt, name, store)
        except YouTubeAPIError as exc:
            if "quota" in str(exc).lower() or "403" in str(exc):
                raise
            ch = None
        if ch is None:
            missing.append(name)
            continue
        channels.append(ch)
        videos += recent_videos(yt, ch, settings.competitor_days, now)
    rep = analyze(videos)
    rep["thumbnail_text"] = ocr_thumbnails(sorted(videos, key=lambda v: -v["views_per_day"]), session)
    rep.update({"date": (now or datetime.now(timezone.utc)).date().isoformat(), "days": settings.competitor_days,
                "channels": [{"name": c["title"], "subscribers": c["subscribers"]} for c in channels],
                "not_found": missing, "quota_units": yt.units,
                "top_videos": [{k: v[k] for k in ("channel", "title", "views_per_day", "seconds", "published")}
                               for v in sorted(videos, key=lambda v: -v["views_per_day"])[:25]],
                "all_titles": [v["title"] for v in videos]})
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{rep['date']}.json").write_text(json.dumps(rep, indent=2))
    (out_dir / "latest.json").write_text(json.dumps(rep, indent=2))
    (out_dir / f"{rep['date']}.md").write_text(render_markdown(rep))
    return rep


def render_markdown(r: dict) -> str:
    t, ln = r["titles"], r["length"]
    L = [f"# Competitor patterns ({r['date']}, last {r['days']} days)", "",
         "Patterns only. Never copy their characters, thumbnails, titles or wording.", "",
         "Channels: " + ", ".join(f"{c['name']} ({c['subscribers']:,} subs)" for c in r["channels"]),
         f"Long videos: {r['long_videos']} · Shorts: {r['shorts']} · API units used: {r['quota_units']}", "",
         "## Length", f"Median {ln['median_minutes']} min · under 10 min {ln['under_10']:.0%} · 10-20 min "
         f"{ln['10_to_20']:.0%} · over 20 min {ln['over_20']:.0%}", "", "## Titles",
         f"Median {t['median_words']} words / {t['median_chars']} characters · numbers {t['with_number']:.0%} · "
         f"$ amounts {t['with_dollar']:.0%} · questions {t['question']:.0%} · you/your {t['you_your']:.0%} · "
         f"years {t['with_year']:.0%} · ALL-CAPS word {t['all_caps_word']:.0%}", "", "## Topics that perform"]
    L += [f"- {k}: {v['videos']} videos, median {v['median_views_per_day']:,} views/day → score {v['score']}/10"
          for k, v in list(r["topics"].items())[:15]]
    L += ["", "## Title keywords (3+ videos, by median views/day)"]
    L += [f"- {k['word']}: {k['videos']} videos, {k['median_views_per_day']:,}/day" for k in r["keywords"][:15]]
    th = r.get("thumbnail_text") or {}
    L += ["", "## Thumbnail text", (f"{th['thumbnails_read']} read · median {th['median_words']} words · no text "
                                    f"{th['no_text_share']:.0%} · common: {', '.join(th['common_words'])}") if th
          else "Not measured (install tesseract-ocr on the VPS to enable)."]
    L += ["", "## Top videos (for reading only)"]
    L += [f"- {v['channel']}: \"{v['title']}\" ({v['views_per_day']:,}/day, {v['seconds'] // 60} min)"
          for v in r["top_videos"][:10]]
    return "\n".join(L) + "\n"


def load_latest(path: Path = Path("reports/competitors/latest.json"), max_age_days: int = 21) -> dict | None:
    try:
        r = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    if (date.today() - date.fromisoformat(r["date"])).days > max_age_days:
        return None
    return r


def potential_score(concept_key: str, report: dict | None) -> tuple[float, str] | None:
    if not report or concept_key not in report.get("concept_scores", {}):
        return None
    t = report["topics"][concept_key]
    return report["concept_scores"][concept_key], (f"competitors: {t['videos']} videos in {report['days']} days, "
                                                   f"median {t['median_views_per_day']:,} views/day")


def _jaccard(a: str, b: str) -> float:
    wa, wb = set(_words(a)), set(_words(b))
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def too_similar(title: str, report: dict | None) -> str | None:
    """The competitor title our title is too close to, if any (never copy their titles)."""
    for t in (report or {}).get("all_titles", []):
        if _jaccard(title, t) >= TITLE_SIMILAR:
            return t
    return None


__all__ = ["run", "analyze", "load_latest", "potential_score", "too_similar", "YouTube", "YouTubeAPIError",
           "render_markdown", "DEFAULT_CHANNELS"]
