"""Turns raw signals into finance-only candidate topics, scores them and ranks them.

Every score is labelled as one of:
  MEASURED    computed from collected data (numbers shown in the report)
  RULE        deterministic rule (e.g. market relevance from the subject)
  ESTIMATE    judgment: rule-based when Claude is unavailable, or Claude when configured
  UNAVAILABLE the data source was not available; the weight is removed and confidence lowered
No score is a prediction that a video will go viral.
"""
from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from .finance_filter import CONCEPTS, Concept, category_of, gate, market_of, match_concepts

# practical value: money saving, debt, credit, taxes, investing basics, banking (rule-based, see PRACTICAL)
WEIGHTS = {"practical": 10, "demand": 20, "potential_views": 20, "competition": 15, "curiosity": 10, "thumbnail": 10,
           "title": 10, "relevance": 8, "monetization": 7}
MAX_FRESHNESS_BONUS = 8.0
# A criterion we CAN measure today but found no data for (for this topic) counts as weak evidence rather than
# being dropped; otherwise topics with little evidence would be scored mostly on estimates. Criteria whose
# source is unavailable for every topic (YouTube) are dropped for all topics equally.
NO_EVIDENCE = 3.0
CLOSE_CALL_POINTS = 3.0

# Sponsor/monetization potential by category: an ESTIMATE from general industry patterns (finance products
# that pay for customer acquisition, e.g. cards, brokerages, banks). Not measured; refine with our own data.
MONETIZATION = {"Credit and Debt": 9, "Investing": 9, "Banking and Money": 8, "Saving and Wealth Building": 8,
                "Personal Finance": 7, "Financial Mistakes and Scams": 6, "Financial Psychology": 6}
REGION_TAGS = {"united-states", "canada", "united-kingdom", "india", "australia", "germany", "france", "netherlands",
               "ireland", "spain", "italy", "singapore", "new-zealand", "south-africa", "switzerland", "eu", "europe",
               "japan", "israel", "sweden", "poland", "belgium", "norway", "denmark", "hong-kong", "brazil"}
# Practical value for viewers (0-10, rule): everyday money decisions score highest.
PRACTICAL = {
    # 10: everyday decisions that save or cost real money
    "credit_card": 10, "credit_score": 10, "budgeting": 10, "emergency_fund": 10, "hysa": 10, "income_tax": 10,
    "debt_payoff": 10, "bank_fees": 10, "retirement_401k": 10, "scams": 10,
    # 9: high practical value
    "credit_report": 9, "debt_collection": 9, "student_loan": 9, "ira_roth": 9, "rrsp": 9, "tfsa": 9, "fhsa": 9,
    "index_funds": 9, "compound": 9, "identity_theft": 9, "paycheck": 9, "fees_expense": 9, "money_mistakes": 9,
    "hsa": 9, "bnpl": 9, "cd_gic": 9,
    # 8: practical for many viewers
    "mortgage": 8, "auto_loan": 8, "personal_loan": 8, "bank_account": 8, "deposit_insurance": 8, "rent_vs_buy": 8,
    "retirement_planning": 8, "insurance": 8, "money_transfer": 8, "debit_prepaid": 8, "capital_gains": 8,
    "education_saving": 8, "stocks": 8, "bonds": 7, "robo": 7, "net_worth": 7, "inflation_personal": 7,
    "cost_of_living": 7, "spending_psych": 7, "money_relationships": 7, "estate": 7, "bankruptcy": 7,
    # lower: niche or speculative for a general audience
    "fire": 6, "real_estate_inv": 6, "gold": 5, "crypto": 5, "options": 4, "currency_exchange": 5, "check_cashing": 6,
}
QUESTION_RE = re.compile(r"^(why|how|should|is|are|can|what|does|do|when|which|will|would|could)\b|\?$", re.I)


@dataclass
class Candidate:
    key: str
    label: str
    concept: Concept | None = None
    se: list = field(default_factory=list)
    cfpb: list = field(default_factory=list)
    wiki_top: list = field(default_factory=list)
    wiki_series: list | None = None
    news: list = field(default_factory=list)       # official releases (Fed, CFPB, IRS) with URLs
    trends: list = field(default_factory=list)     # Google Trends daily trending searches (US/CA)
    searches: list = field(default_factory=list)   # Google search suggestions (questions people type)
    metrics: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)     # criterion -> (value 0-10 or None, label, note)
    category: str = "Personal Finance"
    market: str = "both"
    total: float = 0.0
    freshness: float = 0.0
    confidence: str = "low"
    kind: str = "evergreen"
    why: list = field(default_factory=list)

    @property
    def sources(self) -> list[str]:
        out = []
        if self.se:
            out.append("Stack Exchange")
        if self.cfpb:
            out.append("CFPB")
        if self.wiki_series or self.wiki_top:
            out.append("Wikipedia")
        if self.news:
            out.append("Official news")
        if self.trends:
            out.append("Google Trends")
        if self.searches:
            out.append("Google searches")
        return out


@dataclass
class Rejection:
    source: str
    text: str
    reason: str


def _humanize_tag(tag: str) -> str:
    return tag.replace("-", " ").strip().capitalize()


_TREASURY_DEPT = re.compile(r"\b(?:U\.S\. )?(?:Department of the )?Treasury\b(?!\s+(?:bills?|bonds?|notes?|yields?|"
                            r"securities|inflation|direct|i bonds?))", re.I)
_SHARES_VERB = re.compile(r"\b(?:IRS|CFPB|Fed|Federal Reserve|agency|Board)\s+shares\b", re.I)


def _news_text(title: str) -> str:
    """Neutralise words that name an agency or an action, not a product ('Treasury, IRS issue...', 'IRS shares')."""
    return _SHARES_VERB.sub("agency publishes", _TREASURY_DEPT.sub("government", title))


def build_candidates(se_items, cfpb_items, wiki_items, news_items=None, trend_items=None
                     ) -> tuple[dict[str, Candidate], list[Rejection]]:
    cands: dict[str, Candidate] = {}
    rejected: list[Rejection] = []

    def get(key: str, label: str, concept: Concept | None = None) -> Candidate:
        if key not in cands:
            cands[key] = Candidate(key, label, concept)
        return cands[key]

    for q in se_items:
        text = f"{q['title']} {' '.join(q['tags'])}"
        ok, why = gate(text, finance_source=True)  # a personal-finance Q&A site: only off-topic checks apply
        if not ok:
            rejected.append(Rejection("Stack Exchange", q["title"], why))
            continue
        if any(t in REGION_TAGS and t not in ("united-states", "canada") for t in q["tags"]):
            rejected.append(Rejection("Stack Exchange", q["title"], "not US/Canada (region tag)"))
            continue
        concepts = match_concepts(text)
        if concepts:
            for c in concepts[:2]:  # a question can support at most two concepts
                get(c.key, c.label, c).se.append(q)
        else:
            topical = [t for t in q["tags"] if t not in REGION_TAGS]
            if topical:
                get(f"tag:{topical[0]}", _humanize_tag(topical[0])).se.append(q)

    for it in cfpb_items:
        text = f"{it['product']} {it['issue']}"
        ok, why = gate(text, finance_source=True)  # every CFPB record concerns a consumer financial product
        if not ok:
            rejected.append(Rejection("CFPB", it["issue"], why))
            continue
        concepts = match_concepts(text)
        # sub-issues are long descriptions that mention many things; use them only to spot fraud/identity theft
        fraud = [c for c in match_concepts(it["top_sub_issue"]) if c.key in ("identity_theft", "scams")]
        concepts += [c for c in fraud if c not in concepts]
        if concepts:
            for c in concepts[:2]:
                get(c.key, c.label, c).cfpb.append(it)
        else:
            get(f"cfpb:{it['issue']}", f"{it['issue']} ({it['product']})").cfpb.append(it)

    skip = re.compile(r"^(Main_Page|Special:|Wikipedia:|Portal:|File:|Help:|Template:|Category:|Talk:|User:|-)")
    for a in wiki_items:
        art = a["article"]
        if skip.match(art):
            continue
        title = art.replace("_", " ")
        concepts = match_concepts(title)
        has_fin = bool(concepts) or bool(re.search(r"\b(bank|credit|loan|debt|tax|invest|stock|fund|money|"
                                                   r"retire|pension|mortgage|crypto|bitcoin|scam|fraud)", title, re.I))
        if not has_fin:
            continue  # ordinary non-finance trending page: not logged individually (thousands per day)
        ok, why = gate(title)
        if not ok:
            rejected.append(Rejection("Wikipedia trending", title, why))
            continue
        if concepts:
            for c in concepts[:1]:
                get(c.key, c.label, c).wiki_top.append(a)
        else:
            get(f"wiki:{art}", title).wiki_top.append(a)

    for n in news_items or []:  # official releases: only kept when they clearly concern a finance concept
        text = _news_text(n["title"])  # headline only: summaries mention agencies and boilerplate
        ok, why = gate(n["title"])
        if not ok:
            rejected.append(Rejection(n["source"], n["title"], why))
            continue
        for c in match_concepts(text)[:2]:
            get(c.key, c.label, c).news.append(n)

    for t in trend_items or []:  # trending searches: most are sports/celebrities and are silently ignored
        text = t["query"] + " " + " ".join(x["title"] for x in t.get("news", []))
        concepts = match_concepts(t["query"]) or match_concepts(text)
        if not concepts:
            continue
        ok, why = gate(text)
        if not ok:
            rejected.append(Rejection("Google Trends", t["query"], why))
            continue
        for c in concepts[:1]:
            get(c.key, c.label, c).trends.append(t)
    return cands, rejected


# ------------------------------------------------------------------ metrics
def _age_days(ts: int, today: date) -> float:
    return max(1.0, (datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc).timestamp() - ts) / 86400)


def compute_metrics(c: Candidate, today: date) -> None:
    m: dict = {}
    if c.se:
        m["se_questions_365d"] = len(c.se)
        m["se_questions_30d"] = sum(1 for q in c.se if _age_days(q["created"], today) <= 30)
        m["se_views_per_day"] = round(sum(q["views"] / _age_days(q["created"], today) for q in c.se), 1)
        m["se_avg_views"] = round(statistics.mean(q["views"] for q in c.se), 1)
        m["se_question_share"] = round(sum(bool(QUESTION_RE.search(q["title"].strip())) for q in c.se) / len(c.se), 2)
        regions = [t for q in c.se for t in q["tags"] if t in REGION_TAGS]
        m["se_region_tags"] = {r: regions.count(r) for r in sorted(set(regions))}
    if c.cfpb:
        m["cfpb_complaints_90d"] = sum(i["count"] for i in c.cfpb)
        prev = sum(i["year_ago"] for i in c.cfpb)
        m["cfpb_complaints_year_ago"] = prev
        m["cfpb_yoy_change"] = round(m["cfpb_complaints_90d"] / prev - 1, 3) if prev else None
    s = c.wiki_series
    if s and len(s) >= 60:
        last30, prev30 = sum(s[-30:]), sum(s[-60:-30])
        m["wiki_views_per_day_30d"] = round(last30 / 30)
        m["wiki_change_vs_prev_30d"] = round(last30 / prev30 - 1, 3) if prev30 else None
        if len(s) >= 395:
            ya = sum(s[-395:-365])
            m["wiki_change_vs_year_ago"] = round(last30 / ya - 1, 3) if ya else None
        months = [sum(s[i:i + 30]) for i in range(len(s) - 360, len(s), 30)] if len(s) >= 360 else []
        if months and statistics.mean(months) > 0:
            m["wiki_monthly_variation"] = round(statistics.pstdev(months) / statistics.mean(months), 2)
    if c.wiki_top:
        m["wiki_trending_views_7d"] = sum(a["views_7d"] for a in c.wiki_top)
    if c.news:
        dated = [n for n in c.news if n.get("date")]
        m["official_news_30d"] = len(c.news)
        m["official_news_14d"] = sum(1 for n in dated if (today - date.fromisoformat(n["date"])).days <= 14)
    if c.trends:
        m["trends_searches"] = len(c.trends)
        m["trends_traffic"] = sum(t["traffic"] for t in c.trends)
    if c.searches:
        m["search_suggestions"] = len(c.searches)
        m["search_question_share"] = round(sum(bool(QUESTION_RE.search(q)) or q.split()[0] in
                                               ("how", "should", "is", "can", "what", "which", "who", "why")
                                               for q in c.searches) / len(c.searches), 2)
    c.metrics = m


def _pct_rank(values: dict[str, float]) -> dict[str, float]:
    """Percentile rank (0-10) of each candidate's value among candidates that have it."""
    items = sorted(values.items(), key=lambda kv: kv[1])
    n = len(items)
    if n == 1:
        return {items[0][0]: 5.0}
    return {k: round(10 * i / (n - 1), 2) for i, (k, _) in enumerate(items)}


def _log(v: float) -> float:
    return math.log10(1 + max(0.0, v))


def score_all(cands: list[Candidate]) -> None:
    def ranks(metric: str, transform=_log):
        return _pct_rank({c.key: transform(c.metrics[metric]) for c in cands
                          if c.metrics.get(metric) is not None})

    r_se_vpd, r_se_n = ranks("se_views_per_day"), ranks("se_questions_365d")
    r_cfpb = ranks("cfpb_complaints_90d")
    r_wiki = ranks("wiki_views_per_day_30d")
    r_trends, r_search = ranks("trends_traffic"), ranks("search_suggestions", lambda v: v)
    r_se_avg = ranks("se_avg_views")
    ident = lambda v: v  # noqa: E731
    r_mom = {k: ranks(k, ident) for k in ("wiki_change_vs_prev_30d", "wiki_change_vs_year_ago", "cfpb_yoy_change")}

    for c in cands:
        c.category = category_of([c.concept] if c.concept else match_concepts(c.label), c.label)
        text = c.label + " " + " ".join(q["title"] + " " + " ".join(q["tags"]) for q in c.se[:30])
        c.market = market_of(text, [c.concept] if c.concept else [])
        if c.concept is None and c.cfpb and c.market == "both" and not c.se:
            c.market = "US"  # a CFPB-only problem without a concept: Canadian relevance not established
        sc: dict = {}
        dem = [r[c.key] for r in (r_se_vpd, r_se_n, r_cfpb, r_wiki, r_trends, r_search) if c.key in r]
        sc["demand"] = (round(statistics.mean(dem), 1), "MEASURED",
                        f"avg percentile of {len(dem)} demand signal(s)") if dem else \
            (NO_EVIDENCE, "MEASURED", "no demand signal found for this topic")
        sc["potential_views"] = (None, "UNAVAILABLE", "needs YouTube Data API key")
        sc["competition"] = (None, "UNAVAILABLE", "needs YouTube Data API key")
        if c.se:
            cur = 10 * c.metrics["se_question_share"] * 0.5 + r_se_avg.get(c.key, 5) * 0.5
            sc["curiosity"] = (round(cur, 1), "MEASURED", "question-phrasing share + views per question")
        elif c.searches:
            cur = 10 * c.metrics["search_question_share"] * 0.5 + r_search.get(c.key, 5) * 0.5
            sc["curiosity"] = (round(cur, 1), "MEASURED", "questions people type into Google about it")
        else:
            sc["curiosity"] = (NO_EVIDENCE, "MEASURED", "no real viewer questions found for this topic")
        rel = {"both": 10, "US": 7, "CA": 7, "other": 1}[c.market]
        sc["relevance"] = (rel, "RULE", f"market: {c.market}")
        hook = bool(c.concept and c.concept.numeric_hook)
        stakes = c.category in ("Credit and Debt", "Financial Mistakes and Scams")
        has_q = any(QUESTION_RE.search(q["title"]) for q in c.se[:20])
        sc["thumbnail"] = (min(10, 4 + 3 * hook + 2 * stakes + 1 * bool(c.cfpb)), "ESTIMATE",
                           "rule-based (Claude not configured): numeric hook, stakes")
        sc["title"] = (min(10, 4 + 2 * has_q + 2 * hook + 2 * stakes), "ESTIMATE",
                       "rule-based (Claude not configured): real viewer question, numeric hook, stakes")
        sc["monetization"] = (MONETIZATION[c.category], "ESTIMATE", "category sponsor potential (industry pattern)")
        prac = PRACTICAL.get(c.concept.key if c.concept else "", 6)
        sc["practical"] = (prac, "RULE", "practical value for viewers (saving, debt, credit, taxes, investing basics)")
        c.scores = sc

        avail = {k: v for k, v in sc.items() if v[0] is not None}
        wsum = sum(WEIGHTS[k] for k in avail)
        c.total = round(sum(WEIGHTS[k] * v[0] for k, v in avail.items()) / wsum * 10, 1) if wsum else 0.0
        moms = [r[c.key] for r in r_mom.values() if c.key in r]
        if c.metrics.get("official_news_14d"):  # a fresh official release about it counts as momentum
            moms.append(min(10.0, 7.0 + c.metrics["official_news_14d"]))
        if c.trends:  # trending in Google today
            moms.append(9.0)
        mom = statistics.mean(moms) if moms else None
        c.metrics["momentum_percentile"] = round(mom, 1) if mom is not None else None
        c.freshness = round(max(0.0, (mom - 5) / 5) * MAX_FRESHNESS_BONUS, 1) if mom is not None else 0.0
        c.total = round(min(100.0, c.total + c.freshness), 1)
        var = c.metrics.get("wiki_monthly_variation")
        c.kind = "timely" if c.freshness >= 4 else ("evergreen" if var is None or var < 0.35 else "seasonal")
        measured_w = sum(WEIGHTS[k] for k, v in avail.items() if v[1] == "MEASURED")
        share = measured_w / sum(WEIGHTS.values())
        n_src = len(c.sources)
        c.confidence = "high" if share >= 0.5 and n_src >= 2 else ("medium" if share >= 0.25 and n_src >= 2
                                                                   else "low")
        c.why = explain(c)


def explain(c: Candidate) -> list[str]:
    m, out = c.metrics, []
    if m.get("se_questions_365d"):
        out.append(f"{m['se_questions_365d']} real questions about it on Stack Exchange in the last year "
                   f"({m['se_questions_30d']} in the last 30 days), drawing {m['se_views_per_day']:,} views/day combined")
    if m.get("cfpb_complaints_90d"):
        yoy = m.get("cfpb_yoy_change")
        trend = f", {yoy:+.0%} vs the same period last year" if yoy is not None else ""
        out.append(f"{m['cfpb_complaints_90d']:,} US consumer complaints to the CFPB in 90 days{trend}")
    if m.get("wiki_views_per_day_30d"):
        ch = m.get("wiki_change_vs_year_ago")
        trend = f" ({ch:+.0%} vs a year ago)" if ch is not None else ""
        out.append(f"Wikipedia article read {m['wiki_views_per_day_30d']:,} times/day{trend}")
    if m.get("wiki_trending_views_7d"):
        out.append(f"In Wikipedia's most-read list this week ({m['wiki_trending_views_7d']:,} views in 7 days)")
    for n in sorted(c.news, key=lambda n: n.get("date", ""), reverse=True)[:2]:
        out.append(f"Official news, {n['source']} {n.get('date', '')}: \"{n['title']}\" {n['url']}")
    for t in c.trends[:1]:
        out.append(f"Trending on Google ({t['geo']}) today: \"{t['query']}\" ({t['traffic']:,}+ searches) {t['url']}")
    if c.searches:
        out.append(f"{len(c.searches)} questions people type into Google, e.g. \"{c.searches[0]}\"")
    if c.freshness >= 4:
        out.append("Interest is rising faster than other candidates (timely)")
    return out


MIN_EVIDENCE = {"se": 4, "cfpb": 300, "wiki": 300}


def eligible(c: Candidate) -> tuple[bool, str]:
    m = c.metrics
    if c.market == "other":
        return False, "not relevant to US/Canada viewers"
    strong = (m.get("se_questions_365d", 0) >= MIN_EVIDENCE["se"] or m.get("cfpb_complaints_90d", 0) >= MIN_EVIDENCE["cfpb"]
              or m.get("wiki_views_per_day_30d", 0) >= MIN_EVIDENCE["wiki"] or m.get("wiki_trending_views_7d", 0) > 0
              or m.get("official_news_14d", 0) > 0 or m.get("trends_searches", 0) > 0)
    return (True, "") if strong else (False, "too little evidence of demand")


__all__ = ["Candidate", "Rejection", "build_candidates", "compute_metrics", "score_all", "eligible", "CONCEPTS"]
