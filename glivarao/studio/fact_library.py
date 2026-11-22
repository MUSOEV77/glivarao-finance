"""Reviewed official US facts per topic, added to EVERY video's fact sheet for that topic (launch list or research).

Why: the writer may only use numbers from the fact sheet. When a topic needs a standard number (the poverty
guidelines for ACA subsidies, the average card rate, the FDIC limit, ...), it must already be on the sheet with
its official URL. Each fact has a `verify` phrase that is re-checked on the official page before writing (a fact
whose phrase disappeared is dropped). Checked on 2026-11-22.
"""
from __future__ import annotations

import logging

from .launch_plan import (CARD_RATE, CRISIS_BANKS, DEBT_40T, FDIC_LIMIT, FED_GOALS, FED_RANGE, HH_DELINQ, HH_TOTAL,
                          HHDC, JAPAN, MORT_BAL, MORTGAGE, NEW_HOME, NYFED_HHDC, REVOLVING, STUDENT, LaunchFact)

log = logging.getLogger(__name__)
F = LaunchFact
FPL = "https://aspe.hhs.gov/topics/poverty-economic-mobility/poverty-guidelines"
HC_FPL = "https://www.healthcare.gov/glossary/federal-poverty-level-fpl/"
HC_DATES = "https://www.healthcare.gov/quick-guide/dates-and-deadlines/"
CFPB_BNPL = ("https://www.consumerfinance.gov/archive/newsroom/cfpb-research-reveals-heavy-buy-now-pay-later-use-"
             "among-borrowers-with-high-credit-balances-and-multiple-pay-in-four-loans/")

ACA = [F("The 2026 federal poverty guideline (48 states and DC) is $15,960 for 1 person, $21,640 for 2, $27,320 for "
         "3 and $33,000 for 4.", "HHS poverty guidelines (ASPE)", FPL, "15,960"),
       F("For larger households, add $5,680 for each additional person (2026 guidelines, 48 states and DC).",
         "HHS poverty guidelines (ASPE)", FPL, "5,680"),
       F("With income between 100% and 400% of the federal poverty level you qualify for the premium tax credit that "
         "lowers your monthly Marketplace premium.", "HealthCare.gov", HC_FPL, "between 100% and 400%"),
       F("Enroll by December 15 for Marketplace coverage that starts January 1; Open Enrollment for 2027 runs "
         "November 1, 2026 to January 15, 2027.", "HealthCare.gov", HC_DATES, "December 15")]

LIBRARY: dict[str, list[LaunchFact]] = {
    "aca_marketplace": ACA,
    "insurance": ACA[:3],
    "credit_card": [CARD_RATE, REVOLVING],
    "debt_payoff": [CARD_RATE, REVOLVING, HH_TOTAL],
    "bnpl": [CARD_RATE, F("About 63 percent of BNPL borrowers had multiple loans at the same time at some point "
                          "during the year (CFPB research).", "CFPB", CFPB_BNPL, "63 percent")],
    "household_debt": [HH_TOTAL, HH_DELINQ],
    "credit_score": [F("As of the third quarter of 2026, 4.9% of US consumers had a third-party collection account on "
                       "their credit report.", f"{HHDC}, 2026 Q3", NYFED_HHDC, "4.9%")],
    "student_loan": [STUDENT],
    "mortgage": [MORTGAGE, NEW_HOME, MORT_BAL],
    "us_housing": [MORTGAGE, NEW_HOME, MORT_BAL],
    "rent_vs_buy": [MORTGAGE, NEW_HOME],
    "fed_rates": [FED_GOALS, FED_RANGE, CARD_RATE],
    "recession": [HH_DELINQ, FED_GOALS],
    "national_debt": [DEBT_40T, JAPAN],
    "treasury_market": [JAPAN, MORTGAGE],
    "us_banks": [FDIC_LIMIT, CRISIS_BANKS],
    "deposit_insurance": [FDIC_LIMIT],
    "hysa": [FDIC_LIMIT, FED_RANGE],
    "emergency_fund": [FDIC_LIMIT],
    "financial_crisis": [CRISIS_BANKS],
}


def facts_for(topic_key: str) -> list[LaunchFact]:
    return list(LIBRARY.get(topic_key, []))


def add_to_brief(brief) -> None:
    """Add the topic's reviewed facts (no network; duplicates of facts already on the sheet are skipped)."""
    from ..content.brief import Fact

    have = {f.text for f in brief.facts}
    for f in facts_for(brief.topic_key):
        if f.text not in have:
            brief.facts.append(Fact("DATA", f.text, f.source, f.url))
            have.add(f.text)


def verify_brief(brief, session=None) -> list[str]:
    """Re-check every library fact on the sheet on its official page; drop those whose phrase is gone. Returns
    notes for the review. (Pages that can't be opened keep the fact as checked on CHECKED, flagged.)"""
    from .launch_plan import verify_fact_list

    lib = {f.text: f for f in facts_for(brief.topic_key)}
    mine = [lib[f.text] for f in brief.facts if f.text in lib]
    if not mine:
        return []
    kept, notes = verify_fact_list(mine, session)
    gone = {f.text for f, n in notes if n.startswith("DROPPED")}
    brief.facts = [f for f in brief.facts if f.text not in gone]
    return [f"{f.text[:80]}... {n}" for f, n in notes]


__all__ = ["LIBRARY", "facts_for", "add_to_brief", "verify_brief"]
