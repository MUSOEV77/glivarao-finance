"""Research card -> production brief with a fact sheet.

Fact kinds (shown to the reviewer):
  DATA        measured public data with a link (e.g. CFPB complaint counts)
  CALCULATION exact math with recorded inputs (glivarao.content.calculators)
  EDITORIAL   general explanation from the reviewed GLIVARAO template library (no statistics)
A script may only quote numbers that appear as DATA or CALCULATION facts.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date

from ..research.finance_filter import CONCEPTS
from . import calculators as calc

FAMILY = {
    "card": {"credit_card", "bnpl", "debt_payoff"},
    "loan": {"mortgage", "student_loan", "auto_loan", "personal_loan", "rent_vs_buy"},
    "credit_file": {"credit_report", "credit_score"},
    "scam": {"scams", "identity_theft", "money_mistakes"},
    "grow": {"hysa", "emergency_fund", "compound", "retirement_401k", "ira_roth", "rrsp", "tfsa", "fhsa", "hsa",
             "education_saving", "retirement_planning", "fire", "net_worth", "cd_gic", "budgeting", "paycheck",
             "spending_psych", "cost_of_living", "inflation_personal"},
    "invest": {"index_funds", "stocks", "bonds", "fees_expense", "robo", "crypto", "gold",
               "options", "real_estate_inv"},
    "tax": {"income_tax", "tax_refund", "tax_credits", "tax_filing", "tax_withholding", "side_income_tax",
            "capital_gains"},
    "bank": {"bank_account", "money_transfer", "debit_prepaid", "bank_fees", "deposit_insurance", "check_cashing",
             "currency_exchange"},
}
CONCEPT_BY_KEY = {c.key: c for c in CONCEPTS}


def topic_phrase(label: str) -> str:
    """Lower-case a topic label for use mid-sentence, keeping acronyms (TIPS, ETFs, IRAs, 401(k)) intact."""
    out = []
    for w in label.split():
        caps = sum(ch.isupper() for ch in w)
        out.append(w if caps >= 2 or any(ch.isdigit() for ch in w) else w.lower())
    return " ".join(out)


def family_of(key: str) -> str:
    for fam, keys in FAMILY.items():
        if key in keys:
            return fam
    return "generic"


@dataclass
class Fact:
    kind: str
    text: str
    source: str = ""
    url: str = ""


@dataclass
class Brief:
    date: str
    topic_key: str
    topic: str
    category: str
    market: str
    family: str
    score: float
    confidence: str
    why: list[str]
    angle: str
    viewer_questions: list[dict]
    problems: list[dict]
    facts: list[Fact] = field(default_factory=list)
    calcs: dict = field(default_factory=dict)
    news: list = field(default_factory=list)        # fresh official releases (each with its URL)
    search_questions: list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def fact_sheet_md(self) -> str:
        L = [f"# Fact sheet: {self.topic}", "", f"Category: {self.category} · Market: {self.market} · "
             f"Research score {self.score}/100 ({self.confidence} confidence)", "", "## Why this topic"]
        L += [f"- {w}" for w in self.why] + ["", f"**Angle:** {self.angle}", "", "## Facts used in the script"]
        for f in self.facts:
            src = f" [{f.source}]({f.url})" if f.url else (f" ({f.source})" if f.source else "")
            L.append(f"- **{f.kind}**: {f.text}{src}")
        if self.viewer_questions:
            L += ["", "## Real viewer questions behind this topic"]
            L += [f"- [{q['title']}]({q['link']}): {q['views']:,} views" for q in self.viewer_questions]
        return "\n".join(L) + "\n"


def load_brief(path) -> Brief:
    """Rebuild a Brief saved with Brief.to_json() (facts and exact calculations included)."""
    from pathlib import Path

    d = json.loads(Path(path).read_text())
    d["facts"] = [Fact(**f) for f in d.get("facts", [])]
    d["calcs"] = {k: (calc.Calc(**v) if isinstance(v, dict) else v) for k, v in d.get("calcs", {}).items()}
    return Brief(**d)


def build_brief(card: dict, today: date) -> Brief:
    key = card["key"]
    fam = family_of(key)
    problems = card.get("documented_problems", [])
    growing = sorted([p for p in problems if p.get("year_ago")], key=lambda p: -(p["complaints_90d"] / p["year_ago"]))
    if growing and growing[0]["complaints_90d"] / growing[0]["year_ago"] > 1.15:
        p = growing[0]
        angle = (f"Complaints about \"{p['issue'].lower()}\" are up "
                 f"{p['complaints_90d'] / p['year_ago'] - 1:.0%} year over year. Explain the problem, why it "
                 "happens and exactly what to do.")
    elif card.get("viewer_questions"):
        angle = f"Answer the question people keep asking: \"{card['viewer_questions'][0]['title']}\""
    else:
        angle = f"A clear, practical guide to {card['topic'].lower()}."
    news = [n for n in card.get("official_news", []) if n.get("date") and
            (today - date.fromisoformat(n["date"])).days <= 21]
    if news and not (growing and growing[0]["complaints_90d"] / growing[0]["year_ago"] > 1.15):
        angle = f"Fresh official news: {news[0]['source']} ({news[0]['date']}): \"{news[0]['title']}\". " \
                "Explain what changed, what it means and what to do."
    questions = card.get("viewer_questions", [])[:4]
    if not questions and card.get("search_questions"):  # questions people type into Google
        from ..research.signals import search_url

        questions = [{"title": q[:1].upper() + q[1:] + ("" if q.endswith("?") else "?"), "views": 0,
                      "link": search_url(q), "source": "Google search suggestions"}
                     for q in card["search_questions"][:4]]
    if card.get("angle"):  # launch list / planned videos carry their own angle
        angle = card["angle"]
    b = Brief(today.isoformat(), key, card["topic"], card["category"], card["market"], fam, card["score"],
              card["confidence"], card["why"], angle, questions, problems[:3], news=news[:3],
              search_questions=card.get("search_questions", [])[:10])
    for f in card.get("launch_facts", []):  # official facts checked for the launch list (with source URLs)
        b.facts.append(Fact("DATA", f["text"], f["source"], f["url"]))
    for n in news[:3]:
        b.facts.append(Fact("DATA", f"{n['source']}, {n['date']}: {n['title']}. {n.get('summary', '')}".strip(),
                            n["source"], n["url"]))
    for q in questions:
        if q.get("link"):
            b.facts.append(Fact("DATA", f"Real question people ask: \"{q['title']}\"",
                                q.get("source", "Stack Exchange Personal Finance & Money"), q["link"]))
    for p in problems[:3]:
        if p.get("year_ago"):
            b.facts.append(Fact("DATA", f"{p['complaints_90d']:,} CFPB complaints about \"{p['issue']}\" "
                                f"({p['product']}) in 90 days vs {p['year_ago']:,} in the same period a year "
                                "earlier. Complaints are not a statistical sample of all consumers.",
                                "CFPB Consumer Complaint Database", p["link"]))
    _add_calcs(b)
    return b


def _add_calcs(b: Brief) -> None:
    if b.family == "card":
        mp = calc.minimum_payment_payoff(5000, 0.24)
        fx = calc.fixed_payment_payoff(5000, 0.24, 200)
        b.calcs = {"minimum": mp, "fixed": fx}
        b.facts += [Fact("CALCULATION", mp.fact("years") + f"; total interest {calc.fmt_money(mp.results['total_interest'])}"),
                    Fact("CALCULATION", fx.fact("years") + f"; total interest {calc.fmt_money(fx.results['total_interest'])}"),
                    Fact("EDITORIAL", "Example APR of 24% is hypothetical; check the APR on your own statement.")]
    elif b.family == "loan":
        principal, apr, years = {"mortgage": (400_000, 0.065, 30), "rent_vs_buy": (400_000, 0.065, 30),
                                 "student_loan": (35_000, 0.065, 10), "auto_loan": (35_000, 0.08, 6),
                                 "personal_loan": (10_000, 0.18, 4)}.get(b.topic_key, (35_000, 0.07, 10))
        lo = calc.amortized_loan(principal, apr, years)
        extra = calc.amortized_loan(principal, apr - 0.01, years)
        b.calcs = {"loan": lo, "lower_rate": extra}
        b.facts += [Fact("CALCULATION", lo.fact("monthly_payment") + f"; total interest {calc.fmt_money(lo.results['total_interest'])}"),
                    Fact("CALCULATION", f"One percentage point lower APR: total interest "
                         f"{calc.fmt_money(extra.results['total_interest'])} (inputs: principal {principal}, apr {apr - 0.01:.3f}, years {years})"),
                    Fact("EDITORIAL", "Loan amounts and rates are hypothetical examples, not offers.")]
    elif b.family in ("grow", "invest"):
        g = calc.compound_growth(0, 150, 0.07, 30)
        late = calc.compound_growth(0, 150, 0.07, 20)
        fees = calc.fee_drag(0, 500, 0.07, 0.0005, 0.01, 30)
        b.calcs = {"growth": g, "late": late, "fees": fees}
        b.facts += [Fact("CALCULATION", g.fact("final")), Fact("CALCULATION", late.fact("final")),
                    Fact("CALCULATION", fees.fact("difference")),
                    Fact("EDITORIAL", "7% is a hypothetical rate for illustration; returns are not guaranteed.")]


