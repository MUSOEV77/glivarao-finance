"""R1: daily research run that produces a ranked, evidence-backed topic report. Report only: it never
writes scripts, renders videos, or touches YouTube."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from ..storage import JobStore
from .engine import Candidate, build_candidates, compute_metrics, eligible, score_all
from .finance_filter import CATEGORIES
from .sources import Http, cfpb, stackexchange, wiki_series, wiki_top, youtube_unavailable

log = logging.getLogger(__name__)
TOP_N = 15


def run_research(today: date, out_dir: Path, store: JobStore | None = None, session=None) -> dict:
    stamp = today.isoformat()
    raw = out_dir / "raw" / stamp
    http = Http(raw_dir=raw, session=session)
    from .signals import evergreen_signals, google_trends, official_news, search_questions

    results = [stackexchange(http, today), cfpb(http, today), wiki_top(http, today),
               youtube_unavailable("not configured: no YouTube Data API key")]
    se, cf, wt = (r.items if r.ok else [] for r in results[:3])
    news_r, trends_r = official_news(http, today), google_trends(http)
    results += [news_r, trends_r]
    cands, rejected = build_candidates(se, cf, wt, news_r.items, trends_r.items)

    # common questions people search for: concept topics that already have some evidence
    concept_cands = [c for c in cands.values() if c.concept is not None][:40]
    sq = search_questions(http, {c.key: c.label for c in concept_cands})
    results.append(sq)
    for key, qs in (sq.items[0] if sq.items else {}).items():
        cands[key].searches = qs

    # demand history from Wikipedia for candidates that have at least one other signal
    fetched = 0
    for c in cands.values():
        art = c.concept.wiki if c.concept and c.concept.wiki else (c.key[5:] if c.key.startswith("wiki:") else "")
        if art and (c.se or c.cfpb or c.wiki_top) and fetched < 80:
            c.wiki_series = wiki_series(http, art, today)
            fetched += 1
    results.append(type(results[0])("Wikipedia pageview history", fetched > 0,
                                    f"{fetched} articles, 400 days of daily views", [], http.calls))

    # long-term demand (evergreen rule): Google Trends 12-month/5-year stability + YouTube search suggestions
    ev = evergreen_signals(http, {c.key: c.label for c in concept_cands[:30]}, cache_path=out_dir / "trends_cache.json",
                           today=today)
    results.append(ev)
    for key, d in (ev.items[0] if ev.items else {}).items():
        cands[key].evergreen = d

    for c in cands.values():
        compute_metrics(c, today)
    pool = list(cands.values())
    score_all(pool)
    ranked, excluded = [], []
    for c in pool:
        ok, why = eligible(c)
        (ranked if ok else excluded).append(c if ok else (c, why))
    ranked.sort(key=lambda c: -c.total)

    report = {
        "date": stamp, "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sources": [{"name": r.name, "ok": r.ok, "detail": r.detail} for r in results],
        "api_calls": http.calls,
        "ranked": [_card(c, i + 1) for i, c in enumerate(ranked)],
        "recommended": next((c.key for c in ranked if c.confidence in ("high", "medium")), None),
        "excluded": [{"label": c.label, "reason": why} for c, why in excluded],
        "rejected_off_topic": [{"source": r.source, "text": r.text, "reason": r.reason} for r in rejected],
        "category_coverage": {cat: sum(1 for c in ranked if c.category == cat) for cat in CATEGORIES},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{stamp}.json").write_text(json.dumps(report, indent=2, default=str))
    (out_dir / f"{stamp}.md").write_text(render_markdown(report))
    if store is not None:
        store.kv_set(f"research:{stamp}", json.dumps([r["key"] for r in report["ranked"][:TOP_N]]))
    return report


def _card(c: Candidate, rank: int) -> dict:
    top_q = sorted(c.se, key=lambda q: -q["views"])[:5]
    top_issues = sorted(c.cfpb, key=lambda i: -i["count"])[:3]
    return {
        "rank": rank, "key": c.key, "topic": c.label, "category": c.category, "market": c.market,
        "score": c.total, "freshness_bonus": c.freshness, "confidence": c.confidence, "type": c.kind,
        "sources": c.sources, "why": c.why,
        "scores": {k: {"value": v[0], "basis": v[1], "note": v[2]} for k, v in c.scores.items()},
        "metrics": c.metrics,
        "viewer_questions": [{"title": q["title"], "views": q["views"], "link": q["link"]} for q in top_q],
        "documented_problems": [{"issue": i["issue"], "product": i["product"], "complaints_90d": i["count"],
                                 "year_ago": i["year_ago"], "top_sub_issue": i["top_sub_issue"], "link": i["link"]}
                                for i in top_issues],
        "specific_angles": _angles(c),
        "official_news": sorted(c.news, key=lambda n: n.get("date", ""), reverse=True)[:5],
        "trending_searches": [{"query": t["query"], "traffic": t["traffic"], "geo": t["geo"], "url": t["url"],
                               "news": t.get("news", [])[:2]} for t in c.trends[:3]],
        "search_questions": c.searches[:10],
        "wikipedia": (f"https://en.wikipedia.org/wiki/{c.concept.wiki}" if c.concept and c.concept.wiki else
                      (f"https://en.wikipedia.org/wiki/{c.key[5:]}" if c.key.startswith("wiki:") else None)),
    }


def _angles(c: Candidate) -> list[str]:
    """Concrete video angles found in the data (not invented): fastest-growing documented problems and the
    questions that pull the most views per day."""
    out = []
    growing = sorted((i for i in c.cfpb if i["year_ago"] >= 200),
                     key=lambda i: -(i["count"] / i["year_ago"]))[:2]
    for i in growing:
        out.append(f"Documented problem, {i['count'] / i['year_ago'] - 1:+.0%} year over year: "
                   f"\"{i['issue']}\" (most often: {i['top_sub_issue'] or 'n/a'})")
    for q in sorted(c.se, key=lambda q: -q["views"])[:2]:
        out.append(f"Real viewer question: \"{q['title']}\"")
    return out


def render_markdown(r: dict) -> str:
    L = [f"# GLIVARAO daily finance topic research: {r['date']}", "",
         "_Report only. No video was produced and nothing was uploaded. Scores are opportunity estimates, "
         "not predictions that a video will go viral._", "",
         "## Data sources used today", "", "| Source | Status | Detail |", "|---|---|---|"]
    for s in r["sources"]:
        L.append(f"| {s['name']} | {'✅ measured' if s['ok'] else '⚠️ unavailable'} | {s['detail']} |")
    L += ["", "**Score labels:** **MEASURED** = computed from the data above · **RULE** = fixed rule · "
          "**ESTIMATE** = judgment (rule-based today, because Claude isn't configured) · **UNAVAILABLE** = data "
          "missing, so its weight is removed and confidence lowered. Because YouTube data is unavailable, "
          "*potential views* and *competition* aren't scored yet, and no topic can reach high confidence.", "",
          f"## Top {TOP_N} opportunities", "",
          "| # | Topic | Category | Market | Score | Confidence | Type | Evidence |", "|---|---|---|---|---|---|---|---|"]
    for t in r["ranked"][:TOP_N]:
        L.append(f"| {t['rank']} | {t['topic']} | {t['category']} | {t['market']} | **{t['score']}** | "
                 f"{t['confidence']} | {t['type']} | {', '.join(t['sources'])} |")
    rec = next((t for t in r["ranked"] if t["key"] == r.get("recommended")), None)
    if rec:
        close = [t["topic"] for t in r["ranked"][:6] if t is not rec and abs(t["score"] - rec["score"]) <= 3]
        L += ["", f"**Recommended pick today:** {rec['topic']} ({rec['score']}/100, {rec['confidence']} "
              "confidence). This is the highest score with at least medium confidence."]
        if close:
            L.append(f"_Close call: within 3 points ({', '.join(close)}). Differences this small are within the "
                     "noise of the signals._")
    L += ["", "## Why the top 5 were ranked (evidence)", ""]
    for t in r["ranked"][:5]:
        L += [f"### {t['rank']}. {t['topic']}  ({t['score']}/100, {t['confidence']} confidence)", "",
              f"*{t['category']} · {t['market']} · {t['type']}*", ""]
        L += [f"- {w}" for w in t["why"]]
        if t["specific_angles"]:
            L += ["", "**Specific angles found in the data:**"] + [f"- {a}" for a in t["specific_angles"]]
        L += ["", "| Criterion | Score | Basis | How |", "|---|---|---|---|"]
        for k, v in t["scores"].items():
            L.append(f"| {k.replace('_', ' ')} | {v['value'] if v['value'] is not None else '—'} | {v['basis']} | {v['note']} |")
        if t["freshness_bonus"]:
            L.append(f"| freshness bonus | +{t['freshness_bonus']} | MEASURED | momentum percentile "
                     f"{t['metrics'].get('momentum_percentile')} |")
        if t["viewer_questions"]:
            L += ["", "**What people actually ask (most-viewed, last 12 months):**"]
            L += [f"- [{q['title']}]({q['link']}): {q['views']:,} views" for q in t["viewer_questions"][:4]]
        if t["documented_problems"]:
            L += ["", "**Documented consumer problems (CFPB, last 90 days):**"]
            for p in t["documented_problems"]:
                yo = f", year ago {p['year_ago']:,}" if p["year_ago"] else ""
                L.append(f"- [{p['issue']}]({p['link']}) ({p['product']}): {p['complaints_90d']:,} complaints{yo}; "
                         f"most common: {p['top_sub_issue'] or 'n/a'}")
        if t["wikipedia"]:
            L.append(f"\nDemand reference: {t['wikipedia']}")
        L.append("")
    L += ["## Category coverage in today's ranking", ""]
    L += [f"- {k}: {v}" for k, v in r["category_coverage"].items()]
    rej = r["rejected_off_topic"]
    L += ["", f"## Rejected as not finance / off-topic ({len(rej)})", ""]
    by_reason: dict[str, list[str]] = {}
    for x in rej:
        by_reason.setdefault(x["reason"].split(" (")[0], []).append(f"{x['source']}: {x['text']}")
    for reason, items in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        L.append(f"- **{reason}** ({len(items)}), e.g. " + "; ".join(i[:80] for i in items[:3]))
    L += ["", f"Excluded for weak evidence or non-US/CA relevance: {len(r['excluded'])} candidates.",
          "", "## Caveats", "",
          "- Measured signals are proxies for demand. They are not YouTube search volume. YouTube competition and "
          "view potential will be added when an API key is configured.",
          "- CFPB complaint volume (US only) is dominated by credit-reporting complaints, part of which are filed "
          "in bulk by third parties. It is log-scaled so it can't swamp other signals.",
          "- Wikipedia pageviews are global English readers, not only US/Canada.",
          "- Stack Exchange reflects people who ask online. It skews toward detailed, technical questions.",
          f"- API calls this run: {r['api_calls']}. Raw responses are saved for audit."]
    return "\n".join(L) + "\n"
