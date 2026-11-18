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
    "invest": {"index_funds", "stocks", "bonds", "fees_expense", "robo", "crypto", "gold", "capital_gains",
               "options", "real_estate_inv"},
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
    b = Brief(today.isoformat(), key, card["topic"], card["category"], card["market"], fam, card["score"],
              card["confidence"], card["why"], angle, card.get("viewer_questions", [])[:4], problems[:3])
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


def pick_card(report: dict, used_recently: set[str], free_writer: bool = True,
              recent_categories: list[str] | None = None, max_per_category: int = 2) -> dict | None:
    """Highest-ranked card with at least medium confidence that wasn't used in the last 90 days.

    With the free writer, only topics it has reviewed explanations for are eligible (raw forum tags such as a
    software name can rank in research but can't be written well without the Claude writer)."""
    recent_categories = recent_categories or []

    def writable(card):
        if recent_categories.count(card["category"]) >= max_per_category:  # rotate categories (7-day window)
            return False
        return not free_writer or family_of(card["key"]) != "generic"

    for card in report["ranked"]:
        if card["confidence"] in ("high", "medium") and card["key"] not in used_recently and writable(card):
            return card
    return next((c for c in report["ranked"] if c["key"] not in used_recently and writable(c)), None)
