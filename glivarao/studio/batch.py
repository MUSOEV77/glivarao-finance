"""BATCH TESTING (replaces series mode and the launch-list order while a batch is active).

* A batch = 5 topics. Each topic = 3 long videos (Part 1 how it works, Part 2 the biggest mistakes, Part 3 a
  step-by-step plan) + 3-5 Shorts, each Short ONE single idea. Every part leads with a different official fact,
  so its hook and thumbnail number differ from the other parts.
* Never two parts of one topic back-to-back; deadline topics (ACA: before December 15) go first.
* A topic's Shorts are made on its long-video days (same fact sheet); the other daily Short slots stay
  research-driven and are not counted in the batch.
* After the batch (every part made and the last one published for 7 days): a Telegram report ranks the 5 topics by
  views, CTR, average view % and subscribers gained (Shorts count for views and subscribers), names the winner and
  proposes the next 5 topics close to it, for your approval (nothing is planned from it until you tap approve).
* Batch videos are an episode series per topic ("Part 2 of 3"), so later parts link to earlier ones.
Never uploads, publishes or schedules anything.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from .launch_plan import (CARD_RATE, FED_GOALS, FED_RANGE, HH_DELINQ, HH_TOTAL, LAUNCH, MORT_BAL, MORTGAGE, NEW_HOME,
                          REVOLVING, LaunchFact)
from .fact_library import ACA

PARTS = {1: ("How it works", "explainer",
             "PART 1 of 3, HOW IT WORKS: explain the mechanism from zero with real numbers, so the viewer finally "
             "understands it."),
         2: ("The biggest mistakes", "myth_vs_fact",
             "PART 2 of 3, THE BIGGEST MISTAKES: the costly mistakes and myths, each with what it costs and the fix."),
         3: ("Your step-by-step plan", "case_study",
             "PART 3 of 3, YOUR STEP-BY-STEP PLAN: a concrete plan the viewer can follow this week, step by step, "
             "with a worked example built from the fact sheet.")}


@dataclass
class ShortIdea:
    idea: str
    fact: LaunchFact


@dataclass
class BatchTopic:
    slug: str
    title: str
    key: str
    series: str
    facts: list[LaunchFact]
    lead: dict[int, int]                       # part -> index of its lead fact (hook + thumbnail number)
    shorts: list[ShortIdea] = field(default_factory=list)
    done_parts: tuple[int, ...] = ()           # parts already made before the batch started
    publish_by: str = ""                       # every part and Short published before this date
    affiliate: str = "budgeting app"


SCORES = [LAUNCH[2].facts[2], LAUNCH[2].facts[0], LAUNCH[2].facts[1]]      # 4.9% collections, checking, free reports

BATCH1 = [
    BatchTopic("get-out-of-card-debt", "How to get out of credit card debt", "credit_card", "Card Debt Escape",
               [CARD_RATE, HH_DELINQ, REVOLVING, HH_TOTAL], {1: 0, 2: 1, 3: 2},
               [ShortIdea("What a 22.36% card rate really means for one balance", CARD_RATE),
                ShortIdea("How big US card debt is: $1,368.5 billion owed", REVOLVING),
                ShortIdea("One missed payment: 5.0% of household debt is already behind", HH_DELINQ),
                ShortIdea("Why paying only the minimum keeps the balance alive", CARD_RATE)],
               done_parts=(1,), affiliate="debt payoff"),
    BatchTopic("aca-dec-15", "ACA Open Enrollment: the December 15 deadline", "aca_marketplace", "ACA 2027 Checklist",
               list(ACA), {1: 2, 2: 3, 3: 0},
               [ShortIdea("December 15: the date for coverage that starts January 1 (new enrollees)", ACA[3]),
                ShortIdea("Open Enrollment for 2027 runs until January 15", ACA[3]),
                ShortIdea("The 100%-400% income range for the premium tax credit", ACA[2]),
                ShortIdea("$15,960: the 2026 poverty guideline for one person", ACA[0])],
               publish_by="2026-12-13", affiliate="insurance"),
    BatchTopic("how-credit-scores-work", "How credit scores really work", "credit_score", "Credit Score Basics",
               SCORES, {1: 0, 2: 1, 3: 2},
               [ShortIdea("Checking your own score does not hurt it", SCORES[1]),
                ShortIdea("Your free credit reports from all three bureaus", SCORES[2]),
                ShortIdea("4.9% of US consumers have a collection on their report", SCORES[0])],
               affiliate="credit monitoring"),
    BatchTopic("how-the-fed-affects-you", "How the Fed affects your money", "fed_rates", "The Fed and You",
               [FED_GOALS, FED_RANGE, CARD_RATE, MORTGAGE], {1: 0, 2: 2, 3: 1},
               [ShortIdea("The Fed's two jobs, set by Congress", FED_GOALS),
                ShortIdea("The Fed's rate today: 3-3/4 to 4 percent", FED_RANGE),
                ShortIdea("From the Fed's rate to your 22.36% card rate", CARD_RATE)],
               affiliate="high-yield savings"),
    BatchTopic("why-houses-expensive", "Why houses got so expensive", "us_housing", "Housing Explained",
               [NEW_HOME, MORT_BAL, MORTGAGE], {1: 0, 2: 1, 3: 2},
               [ShortIdea("$400,400: the median price of a new US house", NEW_HOME),
                ShortIdea("7.28% vs 6.26% a year earlier: the mortgage rate", MORTGAGE),
                ShortIdea("$13.4 trillion in mortgage balances", MORT_BAL)],
               affiliate="high-yield savings"),
]
VERSION = "batch1-2026-11-23"
START = date(2026, 11, 25)       # first planned publish date (production runs 2-3 days ahead)
LONG_EVERY_DAYS = 2              # 14 long videos over 4 weeks ~ the 16-a-month pace


def topics(store) -> list[BatchTopic]:
    """The active batch, with the parts you made by hand (batch-mark-done) counted as done: they leave the plan,
    so the next part takes their slot. A topic's planned Shorts shrink so manual + planned stays at most 5."""
    from dataclasses import replace as _replace

    nxt = json.loads(store.kv_get("batch_custom", "null") or "null")
    base = [_topic_from(d) for d in nxt["topics"]] if nxt else BATCH1
    manual = _state(store).get("manual", {})
    out = []
    for t in base:
        m = manual.get(t.slug, {})
        parts = tuple(sorted(set(t.done_parts) | {int(p) for p in m.get("parts", {})}))
        keep = max(0, 5 - len(m.get("shorts", [])))
        out.append(_replace(t, done_parts=parts, shorts=t.shorts[:keep]))
    return out


def version(store) -> str:
    nxt = json.loads(store.kv_get("batch_custom", "null") or "null")
    return nxt["version"] if nxt else VERSION


def _f(d: dict) -> LaunchFact:
    return LaunchFact(**d)


def _topic_from(d: dict) -> BatchTopic:
    return BatchTopic(d["slug"], d["title"], d["key"], d["series"], [_f(x) for x in d["facts"]],
                      {int(k): v for k, v in d["lead"].items()},
                      [ShortIdea(s["idea"], _f(s["fact"])) for s in d["shorts"]], tuple(d.get("done_parts", ())),
                      d.get("publish_by", ""), d.get("affiliate", "budgeting app"))


# ----------------------------------------------------------------------------------------------------- the plan
def plan(batch: list[BatchTopic], start: date = START) -> list[dict]:
    """Long-video order + planned publish dates, and each topic's Shorts on its long days.
    Rules: deadline topics first; never two parts of one topic back-to-back; parts in order 1 -> 2 -> 3."""
    queue = {t.slug: [p for p in (1, 2, 3) if p not in t.done_parts] for t in batch}
    order: list[tuple[str, int]] = []
    last = None
    total = sum(len(v) for v in queue.values())
    while len(order) < total:
        def urgency(t):
            return (0 if t.publish_by else 1, -len(queue[t.slug]), [x.slug for x in batch].index(t.slug))
        ready = sorted((t for t in batch if queue[t.slug] and t.slug != last), key=urgency)
        if not ready:                       # only one topic left: it can't avoid itself (never happens in batch 1)
            ready = [t for t in batch if queue[t.slug]]
        t = ready[0]
        order.append((t.slug, queue[t.slug].pop(0)))
        last = t.slug
    by = {t.slug: t for t in batch}
    entries, day = [], start
    for slug, part in order:
        t = by[slug]
        todo = [p for p in (1, 2, 3) if p not in t.done_parts]
        ideas = _split(t.shorts, len(todo))[todo.index(part)]
        entries.append({"id": f"{slug}:p{part}", "topic": slug, "part": part, "title": t.title,
                        "label": PARTS[part][0], "lead": t.facts[t.lead[part]].text, "publish": day.isoformat(),
                        "shorts": [s.idea for s in ideas], "publish_by": t.publish_by})
        day += timedelta(days=LONG_EVERY_DAYS)
    return entries


def _split(items: list, n: int) -> list[list]:
    out, k = [], 0
    for i in range(n):
        m = math.ceil((len(items) - k) / (n - i))
        out.append(items[k:k + m])
        k += m
    return out


def plan_issues(batch: list[BatchTopic], entries: list[dict]) -> list[str]:
    out = []
    for a, b in zip(entries, entries[1:]):
        if a["topic"] == b["topic"]:
            out.append(f"two parts of {a['topic']} back-to-back ({a['publish']}, {b['publish']})")
    for e in entries:
        if e["publish_by"] and e["publish"] > e["publish_by"]:
            out.append(f"{e['id']} planned {e['publish']}, after its deadline {e['publish_by']}")
    for t in batch:
        leads = [t.lead[p] for p in (1, 2, 3)]
        if len(set(leads)) < 3:
            out.append(f"{t.slug}: parts share a lead fact (hook/thumbnail number must differ)")
        if not 3 <= len(t.shorts) <= 5:
            out.append(f"{t.slug}: {len(t.shorts)} Shorts (needs 3-5)")
        if len({s.idea for s in t.shorts}) != len(t.shorts):
            out.append(f"{t.slug}: two Shorts share an idea")
    return out


def plan_text(store, start: date = START) -> str:
    batch = topics(store)
    entries = plan(batch, start)
    lines = [f"📅 GLIVARAO batch test ({version(store)}): 5 topics x 3 long parts + 3-5 Shorts each",
             "Publish dates are suggestions for YouTube Studio (I never upload). Never two parts of one topic in a row."]
    week = None
    for e in entries:
        d = date.fromisoformat(e["publish"])
        w = (d - start).days // 7 + 1
        if w != week:
            week = w
            lines.append(f"\nWEEK {w}")
        lines.append(f"{d:%a %b %d}  LONG  {e['title']}: Part {e['part']} {e['label']}"
                     + (f"  (deadline {e['publish_by']})" if e["publish_by"] else ""))
        lines.append(f"            lead fact: {e['lead'][:95]}")
        for s in e["shorts"]:
            lines.append(f"            SHORT {s}")
    manual = _state(store).get("manual", {})
    done = [f"{t.title}: Part {p} (already made" +
            (f", {manual[t.slug]['parts'][str(p)]})" if str(p) in manual.get(t.slug, {}).get("parts", {}) else ")")
            for t in batch for p in t.done_parts]
    done += [f"{t.title}: Short {j} (made by you)" for t in batch for j in manual.get(t.slug, {}).get("shorts", [])]
    if done:
        lines.append("\nAlready made: " + "; ".join(done))
    issues = plan_issues(batch, entries)
    lines.append("\nChecks: " + ("all rules OK" if not issues else "; ".join(issues)))
    lines.append("Other daily Short slots (to keep 3 a day) stay research-picked and are not counted in the batch.")
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------------------- state
def _state(store) -> dict:
    return json.loads(store.kv_get("batch_state", "{}") or "{}")


def _save(store, st: dict) -> None:
    store.kv_set("batch_state", json.dumps(st))


def active(store) -> bool:
    st = _state(store)
    return st.get("version", version(store)) == version(store) and not st.get("finished") and \
        store.kv_get("batch_mode", "on") == "on"


def next_long(store) -> dict | None:
    """The next long video to make: the first planned entry not yet planned/made."""
    st = _state(store)
    made = st.get("planned", {})
    for e in plan(topics(store)):
        if e["id"] not in made:
            return e
    return None


def topic(store, slug: str) -> BatchTopic:
    return next(t for t in topics(store) if t.slug == slug)


def card_for(store, e: dict) -> dict:
    """A planning card for one batch part (like a launch-list card): the part's lead fact first on the fact sheet,
    so the hook and thumbnail number differ from the other parts."""
    from ..research.finance_filter import CONCEPTS

    t = topic(store, e["topic"])
    lead = t.facts[t.lead[e["part"]]]
    facts = [lead] + [f for f in t.facts if f is not lead]
    con = next((c for c in CONCEPTS if c.key == t.key), None)
    label, _, how = PARTS[e["part"]]
    earlier = [o for o in _state(store).get("openings", {}).get(t.slug, []) if o]
    angle = (f"{how} Topic: {t.title}. Open with this fact (the hook and the thumbnail number): {lead.text} Use "
             "different facts and examples than the other parts." +
             (" Earlier parts opened with: " + " | ".join(f'"{o[:100]}"' for o in earlier) +
              ". Use a different hook." if earlier else "") +
             f" Product category for the 'What to do' section: {t.affiliate} (category only, no brand names).")
    return {"key": t.key, "topic": f"{t.title} (Part {e['part']}: {label})",
            "category": con.category if con else "Personal Finance", "market": "US", "score": 100.0,
            "confidence": "high", "news": bool(t.publish_by),
            "why": [f"Batch test {version(store)}: {t.title}, Part {e['part']} of 3 ({label})",
                    f"Lead fact: {lead.text[:120]}"],
            "angle": angle, "affiliate_category": t.affiliate, "viewer_questions": [], "documented_problems": [],
            "launch_facts": [asdict(f) for f in facts], "sources": ["Batch test (official US sources)"],
            "batch": {"entry": e["id"], "topic": t.slug, "part": e["part"], "series": t.series,
                      "format": PARTS[e["part"]][1]}}


def short_angles(store, card: dict) -> list[str]:
    """The Shorts for this batch part: one single idea each, with the fact to use."""
    b = card.get("batch") or {}
    if not b:
        return []
    t = topic(store, b["topic"])
    e = next((x for x in plan(topics(store)) if x["id"] == b["entry"]), None)
    ideas = [s for s in t.shorts if e and s.idea in e["shorts"]]
    return [f"ONE single idea only: {s.idea}. Build it on this fact: {s.fact.text} Its own hook in the first two "
            "seconds. Not a cut-down of the long video." for s in ideas]


def mark_planned(store, entry_id: str) -> None:
    st = _state(store)
    st.setdefault("version", version(store))
    st.setdefault("planned", {})[entry_id] = date.today().isoformat()
    _save(store, st)


def record_jobs(store, card: dict, jobs: list[tuple], out_dir=None) -> None:
    """After production: remember which videos belong to which topic (and the part's opening line)."""
    b = card.get("batch") or {}
    if not b:
        return
    st = _state(store)
    lst = st.setdefault("jobs", {}).setdefault(b["topic"], [])
    for j in jobs:
        if j[2] in ("rendered", "pending_approval", "held") and j[0] not in [x["job"] for x in lst]:
            lst.append({"job": j[0], "format": j[1], "part": b["part"]})
            if j[1] == "long" and out_dir is not None:
                try:
                    fp = json.loads((out_dir / j[0] / "variety.json").read_text())["fingerprint"]
                    st.setdefault("openings", {}).setdefault(b["topic"], []).append(fp.get("opening", ""))
                except (OSError, ValueError, KeyError):
                    pass
    _save(store, st)


def mark_done(store, slug: str, part: str, job_id: str, out_dir=None) -> str:
    """A video you made by hand (make-now) counts in the batch. part: 1, 2, 3 (long) or 'short'.
    Returns what changed; raises ValueError for a topic outside the batch, a wrong part or a wrong format."""
    if slug not in [t.slug for t in topics(store)]:
        raise ValueError(f"{slug} is not in the current batch ({', '.join(t.slug for t in topics(store))})")
    try:
        job = store.get(job_id)
    except KeyError:
        raise ValueError(f"no video {job_id}") from None
    fmt = getattr(job.format, "value", str(job.format))
    st = _state(store)
    st.setdefault("version", version(store))
    m = st.setdefault("manual", {}).setdefault(slug, {"parts": {}, "shorts": []})
    lst = st.setdefault("jobs", {}).setdefault(slug, [])
    if part == "short":
        if fmt != "short":
            raise ValueError(f"{job_id} is a {fmt} video, not a Short")
        if job_id not in m["shorts"]:
            m["shorts"].append(job_id)
        if job_id not in [x["job"] for x in lst]:
            lst.append({"job": job_id, "format": "short", "part": None})
        _save(store, st)
        return f"{job_id} counted as a {slug} Short"
    if part not in ("1", "2", "3"):
        raise ValueError("part must be 1, 2, 3 or short")
    if fmt != "long":
        raise ValueError(f"{job_id} is a {fmt} video; parts are long videos")
    m["parts"][part] = job_id
    st.setdefault("planned", {})[f"{slug}:p{part}"] = date.today().isoformat()
    if job_id not in [x["job"] for x in lst]:
        lst.append({"job": job_id, "format": "long", "part": int(part)})
    if out_dir is not None:          # its opening line, so the other parts open differently
        try:
            fp = json.loads((out_dir / job_id / "variety.json").read_text())["fingerprint"]
            st.setdefault("openings", {}).setdefault(slug, []).append(fp.get("opening", ""))
        except (OSError, ValueError, KeyError):
            pass
    _save(store, st)
    return f"{job_id} counted as {slug} Part {part}: it won't be made again; the next part takes its slot"


def topic_jobs(store, slug: str) -> list[dict]:
    """The batch videos of a topic (+ a part made before the batch: matched by the launch-list title)."""
    st = _state(store)
    out = list(st.get("jobs", {}).get(slug, []))
    t = topic(store, slug)
    if t.done_parts:
        lv = next((v for v in LAUNCH if v.slug == slug), None)
        if lv is not None:
            for job in store.list(limit=500):
                if job.topic == lv.topic and job.format == "long" and job.id not in [x["job"] for x in out]:
                    out.append({"job": job.id, "format": "long", "part": t.done_parts[0]})
    return out


# ----------------------------------------------------------------------------------------------------- report
import re as _re  # noqa: E402

_VID = _re.compile(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})")
LONG_METRICS = "views,averageViewPercentage,subscribersGained"
CTR_METRICS = "videoThumbnailImpressions,videoThumbnailImpressionsClickRate"


def video_id(url: str) -> str:
    m = _VID.search(url or "")
    return m.group(1) if m else ""


def _links(store) -> dict[str, str]:
    from . import series as S

    return {e["job"]: e.get("url", "") for e in S.episodes(store) if e.get("url")}


def fetch_metrics(settings, store, analytics=None, start: date | None = None, end: date | None = None) -> dict:
    """{job_id: {views, averageViewPercentage, subscribersGained, impressions, ctr}} for every batch video you
    uploaded (its YouTube link was sent back in Telegram). Raises RuntimeError if YouTube isn't connected."""
    if analytics is None:
        from googleapiclient.discovery import build

        from ..publish.youtube import _credentials

        analytics = build("youtubeAnalytics", "v2", credentials=_credentials(settings), cache_discovery=False)
    end = end or date.today()
    start = start or end - timedelta(days=60)
    links = _links(store)
    out = {}
    for t in topics(store):
        for j in topic_jobs(store, t.slug):
            vid = video_id(links.get(j["job"], ""))
            if not vid:
                try:
                    vid = store.get(j["job"]).youtube_video_id or ""
                except KeyError:
                    vid = ""
            if not vid:
                continue
            row = {}
            for metrics in (LONG_METRICS, CTR_METRICS):
                try:
                    res = analytics.reports().query(ids="channel==MINE", startDate=start.isoformat(),
                                                    endDate=end.isoformat(), metrics=metrics,
                                                    filters=f"video=={vid}").execute()
                except Exception:  # noqa: BLE001  CTR metrics may be unavailable: report without them
                    continue
                names = [h["name"] for h in res.get("columnHeaders", [])]
                vals = (res.get("rows") or [[0] * len(names)])[0]
                row.update(dict(zip(names, vals)))
            out[j["job"]] = {"views": float(row.get("views", 0) or 0),
                             "avp": float(row.get("averageViewPercentage", 0) or 0),
                             "subs": float(row.get("subscribersGained", 0) or 0),
                             "impressions": float(row.get("videoThumbnailImpressions", 0) or 0),
                             "ctr": float(row.get("videoThumbnailImpressionsClickRate", 0) or 0),
                             "format": j["format"], "part": j.get("part")}
    return out


def rank(store, metrics: dict) -> list[dict]:
    """Per topic: views and subscribers from long videos AND Shorts; CTR (impression-weighted) and average view %
    (view-weighted) from the long videos. Ranked by the average of the four places (1 = best)."""
    rows = []
    for t in topics(store):
        jobs = [metrics[j["job"]] for j in topic_jobs(store, t.slug) if j["job"] in metrics]
        longs = [m for m in jobs if m["format"] == "long"]
        imp = sum(m["impressions"] for m in longs)
        lv = sum(m["views"] for m in longs)
        rows.append({"topic": t.slug, "title": t.title, "videos": len(jobs),
                     "views": sum(m["views"] for m in jobs), "subs": sum(m["subs"] for m in jobs),
                     "ctr": (sum(m["ctr"] * m["impressions"] for m in longs) / imp) if imp else 0.0,
                     "avp": (sum(m["avp"] * m["views"] for m in longs) / lv) if lv else 0.0})
    for k in ("views", "ctr", "avp", "subs"):
        for place, r in enumerate(sorted(rows, key=lambda r: -r[k]), 1):
            r[f"place_{k}"] = place
    for r in rows:
        r["score"] = sum(r[f"place_{k}"] for k in ("views", "ctr", "avp", "subs")) / 4
    return sorted(rows, key=lambda r: (r["score"], -r["views"]))


def propose_next(store, winner_slug: str, n: int = 5) -> list:
    """The next n topics closest to the winner, from the official-fact launch list (same family > same pillar >
    others), never a topic already in a batch."""
    from ..content.brief import family_of
    from .pillars import pillar_of

    win = topic(store, winner_slug)
    used = {t.slug for t in topics(store)} | set(json.loads(store.kv_get("batch_used_topics", "[]")))
    fam, pil = family_of(win.key), getattr(pillar_of(win.key), "key", None)

    def close(v):
        return (0 if family_of(v.key) == fam else 1 if getattr(pillar_of(v.key), "key", None) == pil else 2, v.n)
    ranked = sorted((v for v in LAUNCH if v.slug not in used), key=close)
    return [v for v in ranked if ready(v)][:n]


def ready(v) -> bool:
    """3 parts need 3 different official lead facts (launch facts + the reviewed fact library)."""
    return len(_topic_from_launch(v)["facts"]) >= 3


def waiting_for_facts(store, winner_slug: str) -> list:
    """Close topics that can't be proposed yet: fewer than 3 official facts on file."""
    from ..content.brief import family_of
    from .pillars import pillar_of

    win = topic(store, winner_slug)
    used = {t.slug for t in topics(store)} | set(json.loads(store.kv_get("batch_used_topics", "[]")))
    pil = getattr(pillar_of(win.key), "key", None)
    return [v for v in LAUNCH if v.slug not in used and not ready(v) and
            (family_of(v.key) == family_of(win.key) or getattr(pillar_of(v.key), "key", None) == pil)]


def report_text(store, ranking: list[dict], proposals: list, note: str = "", waiting: list | None = None) -> str:
    lines = [f"📊 GLIVARAO batch report ({version(store)}): 5 topics ranked (views and subscribers include Shorts; "
             "CTR and average view % from the long videos)"]
    for k, r in enumerate(ranking, 1):
        lines.append(f"{k}. {r['title']}: {r['views']:,.0f} views, CTR {r['ctr']:.1f}%, avg view {r['avp']:.0f}%, "
                     f"+{r['subs']:,.0f} subs ({r['videos']} videos; places {r['place_views']}/{r['place_ctr']}/"
                     f"{r['place_avp']}/{r['place_subs']})")
    if ranking:
        lines.append(f"\n🏆 Winner: {ranking[0]['title']}")
    if note:
        lines.append(note)
    lines.append("\nProposed next 5 topics (closest to the winner, official facts on file):")
    for k, v in enumerate(proposals, 1):
        lines.append(f"{k}. {v.topic}")
    if waiting:
        lines.append("Also close to the winner, but each needs 1 more official fact before it can have 3 parts: " +
                     "; ".join(v.topic for v in waiting))
    lines.append("\nApprove to plan them as the next batch (3 parts + 3-5 Shorts each). Nothing is planned before.")
    return "\n".join(lines)


def send_report(settings, store, client=None, analytics=None, metrics: dict | None = None) -> dict:
    from ..publish.telegram import _client

    note = ""
    if metrics is None:
        try:
            metrics = fetch_metrics(settings, store, analytics)
        except Exception as exc:  # noqa: BLE001
            metrics, note = {}, (f"⚠ YouTube Analytics not available ({type(exc).__name__}): connect it with "
                                 "python -m glivarao youtube-auth (read-only analytics). Ranked without data.")
    if not metrics and not note:
        note = "⚠ No YouTube links yet: reply to each upload pack with the video's link so it can be measured."
    ranking = rank(store, metrics)
    props = propose_next(store, ranking[0]["topic"]) if ranking else []
    pv = f"next-{version(store)}"
    store.kv_set("batch_proposal", json.dumps({"version": pv, "slugs": [v.slug for v in props],
                                               "winner": ranking[0]["topic"] if ranking else ""}))
    text = report_text(store, ranking, props, note, waiting_for_facts(store, ranking[0]["topic"]) if ranking else [])
    c = _client(settings, client)
    c.call("sendMessage", chat_id=settings.telegram_approver_chat_id, text=text[:4000],
           reply_markup={"inline_keyboard": [[{"text": "✅ Approve next 5", "callback_data": f"batchnext:{pv}"},
                                              {"text": "✏️ Change", "callback_data": f"batchedit:{pv}"}]]})
    store.kv_set(f"batch_reported:{version(store)}", date.today().isoformat())
    return {"ranking": ranking, "proposals": [v.slug for v in props], "text": text}


def due_for_report(store, today: date | None = None) -> bool:
    """Every part planned and the last planned publish date at least 7 days ago; reported once."""
    today = today or date.today()
    if store.kv_get(f"batch_reported:{version(store)}") or next_long(store) is not None:
        return False
    last = max(date.fromisoformat(e["publish"]) for e in plan(topics(store)))
    return today >= last + timedelta(days=7)


def _topic_from_launch(v) -> dict:
    from .fact_library import facts_for

    facts = list(v.facts) + [f for f in facts_for(v.key) if f.text not in {x.text for x in v.facts}]
    n = len(facts)
    lead = {1: 0, 2: 1 % n, 3: 2 % n}
    shorts = [{"idea": f"One fact, one idea: {f.text[:80]}", "fact": asdict(f)} for f in facts[:4]]
    while len(shorts) < 3:
        shorts.append({"idea": f"{v.topic}: the one thing to do today ({len(shorts) + 1})", "fact": asdict(facts[0])})
    return {"slug": v.slug, "title": v.topic, "key": v.key, "series": v.topic.split(":")[0][:40],
            "facts": [asdict(f) for f in facts], "lead": lead, "shorts": shorts, "done_parts": [],
            "publish_by": v.publish_by, "affiliate": v.affiliate}


def approve_next(store, pv: str) -> list[str] | None:
    """Your ✅ on the proposal: the next 5 topics become the active batch (parts + Shorts planned from them)."""
    prop = json.loads(store.kv_get("batch_proposal", "{}") or "{}")
    if prop.get("version") != pv:
        return None
    vids = [v for v in LAUNCH if v.slug in prop["slugs"]]
    used = json.loads(store.kv_get("batch_used_topics", "[]")) + [t.slug for t in topics(store)]
    store.kv_set("batch_used_topics", json.dumps(sorted(set(used))))
    nv = f"batch-{date.today().isoformat()}-{prop.get('winner', '')[:20]}"
    store.kv_set("batch_custom", json.dumps({"version": nv, "topics": [_topic_from_launch(v) for v in vids]}))
    store.kv_set("batch_state", json.dumps({"version": nv}))
    return [v.slug for v in vids]


__all__ = ["BATCH1", "PARTS", "plan", "plan_issues", "plan_text", "active", "next_long", "card_for", "short_angles",
           "mark_planned", "record_jobs", "topic_jobs", "topics", "version", "fetch_metrics", "rank", "propose_next",
           "send_report", "due_for_report", "approve_next", "video_id", "mark_done"]
