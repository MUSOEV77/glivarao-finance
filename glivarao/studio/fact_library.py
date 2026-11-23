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

# Emergency fund (Federal Reserve SHED 2025, published May 2026; CFPB). Checked 2026-11-23.
SHED = "https://www.federalreserve.gov/publications/2026-economic-well-being-of-us-households-in-2025-savings-investments.htm"
SHED_SUM = ("https://www.federalreserve.gov/publications/2026-economic-well-being-of-us-households-in-2025-executive-"
            "summary.htm")
SHED_SRC = "Federal Reserve, Economic Well-Being of U.S. Households in 2025 (May 2026)"
CFPB_EF = "https://www.consumerfinance.gov/an-essential-guide-to-building-an-emergency-fund/"
EF_3MONTHS = F("In 2025, 55 percent of US adults said they had set aside money for three months of expenses in an "
               "emergency savings or rainy day fund.", SHED_SRC, SHED, "55 percent of adults said they had set aside "
               "money for three months of expenses")
EF_400 = F("In 2025, 63 percent of US adults said they would cover a hypothetical $400 emergency expense using cash, "
           "savings, or a credit card paid off at the next statement.", SHED_SRC, SHED, "63 percent of all adults "
           "said they would have covered it exclusively using cash")
EF_CANT = F("In 2025, 12 percent of US adults said they would not be able to pay an unexpected $400 expense right now.",
            SHED_SRC, SHED, "Would not be able to pay for the expense right now 12")
EF_SURPRISE = F("In 2025, 59 percent of US adults had at least one major, unexpected expense in the prior 12 months; the "
                "most common was a major vehicle repair or replacement (30 percent of adults).", SHED_SRC, SHED_SUM,
                "Fifty-nine percent of adults had at least one type of major, unexpected expense")
EF_WHAT = F("An emergency fund is a cash reserve that is specifically set aside for unplanned expenses or financial "
            "emergencies (CFPB).", "CFPB", CFPB_EF, "specifically set aside for unplanned expenses or financial "
            "emergencies")
EMERGENCY = [EF_3MONTHS, EF_400, EF_CANT, EF_SURPRISE, EF_WHAT]

# Roth IRA vs 401(k) (IRS IR-2026 2027 limits; IRS Roth IRAs page; Federal Reserve SHED 2025). Checked 2026-11-23.
IRS_2027 = "https://www.irs.gov/newsroom/401k-limit-increases-to-25500-for-2027-ira-limit-remains-7500"
IRS_ROTH = "https://www.irs.gov/retirement-plans/roth-iras"
R_401K = F("For 2027, you can contribute up to $25,500 to a 401(k) plan, up from $24,500 for 2026.", "IRS", IRS_2027,
           "has increased to $25,500, up from $24,500 for 2026")
R_IRA = F("For 2027, the IRA contribution limit remains $7,500.", "IRS", IRS_2027, "IRA limit remains $7,500")
R_PHASE = F("For 2027, the income phase-out range for contributing to a Roth IRA is $158,000 to $173,000 for singles "
            "and heads of household, and $250,000 to $260,000 for married couples filing jointly.", "IRS", IRS_2027,
            "between $158,000 and $173,000 for singles and heads of household")
R_TAX = F("You cannot deduct contributions to a Roth IRA; if you satisfy the requirements, qualified distributions are "
          "tax-free (IRS).", "IRS", IRS_ROTH, "qualified distributions are tax-free")
R_CATCHUP = F("For 2027, workers 50 and older can generally put up to $34,000 a year into most 401(k) plans ($25,500 plus "
              "an $8,500 catch-up).", "IRS", IRS_2027, "can contribute up to $34,000 each year")
R_HAVE = F("In 2025, 61 percent of US adults had a tax-preferred retirement account such as a 401(k), an IRA or a "
           "Roth IRA.", SHED_SRC, SHED, "61 percent of adults who had a tax-preferred retirement account")
ROTH = [R_401K, R_IRA, R_PHASE, R_TAX, R_CATCHUP, R_HAVE]

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
    "emergency_fund": EMERGENCY,
    "ira_roth": ROTH,
    "retirement_401k": [R_401K, R_CATCHUP, R_HAVE],
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
