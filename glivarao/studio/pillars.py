"""Channel focus: everyday US personal finance for people 25-45 who struggle with money.

US-ONLY: the audience is ordinary Americans; every video is about a US problem and its effect on a US household's
money. 6 content pillars (the 5 personal-finance pillars plus "The US economy and your money" for the Fed, housing,
the stock market, the national debt, banks and recession signals). Anything else (crypto, single stocks, options,
gold, Canada or other countries, general news) is rejected before it can become a video.

Also defines:
* rotation rules (never the same pillar twice in a row; at most 2 of the last 5 videos per pillar, so a week of
  ~4 long videos covers 3-4 different pillars), with taxes favoured December-April (tax season);
* recurring series inside each pillar (e.g. "Money Traps", "Tax Season 2027");
* affiliate program SUGGESTIONS per pillar. These are only names to look into: nothing is signed up for, and no
  affiliate link appears in a description until you add your own link with /affiliate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Pillar:
    key: str
    name: str
    short: str
    concepts: frozenset[str]
    affiliate_ideas: tuple[str, ...]
    avoid: str = ""


PILLARS: dict[str, Pillar] = {p.key: p for p in [
    Pillar("debt", "Debt and credit", "credit cards, loans, credit score", frozenset({
        "credit_card", "credit_report", "credit_score", "debt_collection", "student_loan", "mortgage", "auto_loan",
        "personal_loan", "bnpl", "debt_payoff", "bankruptcy", "household_debt", "medical_debt"}),
        ("Rocket Money", "Monarch Money"),
        avoid="No payday lenders, debt-settlement companies or high-APR cards: this audience is already struggling."),
    Pillar("budget", "Budgeting and saving", "budgets, subscriptions, saving money", frozenset({
        "aca_marketplace", "budgeting", "cost_of_living", "spending_psych", "money_relationships", "paycheck",
        "bank_account", "bank_fees", "debit_prepaid", "emergency_fund", "hysa", "cd_gic"}),
        ("Rocket Money", "Monarch Money", "YNAB (later)"),
        avoid="Only FDIC-insured savings products; never \"get rich\" apps."),
    Pillar("taxes", "Taxes", "filing, IRS changes, refunds", frozenset({
        "income_tax", "capital_gains", "tax_refund", "tax_credits", "tax_filing", "tax_withholding", "side_income_tax"}),
           ("FreeTaxUSA", "TurboTax"),
           avoid="Always mention IRS Free File / Direct File where it applies, before any paid software."),
    Pillar("retire", "Retirement and investing basics", "401(k), IRA, index funds", frozenset({
        "retirement_401k", "ira_roth", "retirement_planning", "hsa", "education_saving", "index_funds", "compound",
        "fees_expense", "bonds", "robo", "fire", "net_worth"}),
        ("Rocket Dollar",),
        avoid="No single-stock picks, trading apps, options or crypto."),
    Pillar("scams", "Scams and consumer protection", "scams, identity theft, your rights", frozenset({
        "scams", "identity_theft", "money_transfer", "money_mistakes"}),
        ("Wise (only for money-transfer topics)",),
        avoid="Always give the free steps first (credit freeze, IdentityTheft.gov, ReportFraud.ftc.gov)."),
    Pillar("economy", "The US economy and your money", "the Fed, housing, stock market, national debt, banks, "
           "recession signals", frozenset({"fed_rates", "us_housing", "us_stock_market", "national_debt",
                                            "treasury_market", "us_banks", "recession", "deposit_insurance",
                                            "rent_vs_buy", "inflation_personal"}),
           ("high-yield savings", "budgeting app"),
           avoid="No predictions, no panic, no political sides: explain the official number, then what a US "
                 "household can do."),
]}
ORDER = list(PILLARS)
OUT_OF_FOCUS = {"crypto": "crypto", "stocks": "single stocks", "options": "options trading", "gold": "gold/metals",
                "real_estate_inv": "real estate investing", "rrsp": "Canada-only", "tfsa": "Canada-only",
                "fhsa": "Canada-only", "insurance": "insurance", "estate": "estates/wills",
                "currency_exchange": "travel money", "check_cashing": "check cashing"}

TAX_SEASON_MONTHS = {12, 1, 2, 3, 4}
RECENT_WINDOW = 5         # at most MAX_IN_WINDOW videos per pillar in the last RECENT_WINDOW
MAX_IN_WINDOW = 2
TAX_SEASON_MAX = 3        # taxes may take 3 of the last 5 in tax season (still never twice in a row)
# Main focus for the first 12 months: debt and credit. Long videos: at least 3 of every 5 are debt/credit (60%).
FOCUS_PILLAR = "debt"
FOCUS_MIN_IN_5 = 3
OTHER_MAX_IN_5 = 1        # each other pillar at most once in 5 long videos (taxes: 2 in tax season)
NEWS_EVERY = 4            # long videos: at most 1 news-driven video in 4
EVERGREEN_BONUS = 5.0


def pillar_of(topic_key: str) -> Pillar | None:
    return next((p for p in PILLARS.values() if topic_key in p.concepts), None)


def rejection(card: dict) -> str | None:
    """Why a research topic is outside the channel focus, or None if it fits a pillar."""
    key = card.get("key", "")
    if key in OUT_OF_FOCUS:
        return f"outside the 5 pillars ({OUT_OF_FOCUS[key]})"
    if card.get("market") in ("CA", "other"):
        return "not a US household topic (US-only channel)"
    if pillar_of(key) is None:
        return "outside the 5 pillars (no clear pillar)"
    return None


def tax_season(today: date) -> bool:
    return today.month in TAX_SEASON_MONTHS


def filing_year(today: date) -> int:
    """The filing season a date belongs to: Dec 2026 - Apr 2027 is "Tax Season 2027"."""
    return today.year + 1 if today.month == 12 else today.year


def needs_focus(recent_pillars: list[str]) -> bool:
    """True when the next long video must be debt/credit to keep >= 60% (3 of every 5)."""
    return recent_pillars[-(5 - 1):].count(FOCUS_PILLAR) < FOCUS_MIN_IN_5


def is_news(card: dict) -> bool:
    return bool(card.get("news")) or card.get("type") == "timely"


def rotation_block(pillar: Pillar, recent_pillars: list[str], today: date, focus: bool = False) -> str | None:
    """Hard rotation rules. recent_pillars: oldest first.
    focus=True (long videos): debt/credit may repeat; every other pillar at most once in 5 (taxes: twice in tax
    season) and never twice in a row. focus=False (Shorts days): plain rotation."""
    if focus:
        if pillar.key == FOCUS_PILLAR:
            return None
        if recent_pillars and recent_pillars[-1] == pillar.key:
            return "same pillar as the previous video"
        cap = 2 if (pillar.key == "taxes" and tax_season(today)) else OTHER_MAX_IN_5
        if recent_pillars[-RECENT_WINDOW:].count(pillar.key) >= cap:
            return f"pillar already used {cap}× in the last {RECENT_WINDOW} videos"
        return None
    if recent_pillars and recent_pillars[-1] == pillar.key:
        return "same pillar as the previous video"
    window = recent_pillars[-RECENT_WINDOW:]
    cap = TAX_SEASON_MAX if (pillar.key == "taxes" and tax_season(today)) else MAX_IN_WINDOW
    if window.count(pillar.key) >= cap:
        return f"pillar already used {cap}× in the last {RECENT_WINDOW} videos"
    return None


def priority_bonus(pillar: Pillar, recent_pillars: list[str], today: date) -> tuple[float, str]:
    """Soft preference added to the research score: pillars not seen for a while come first, taxes get a boost
    December-April and a small penalty the rest of the year."""
    gap = next((i for i, k in enumerate(reversed(recent_pillars), 1) if k == pillar.key), None)
    bonus = 20.0 if gap is None else min(20.0, 5.0 * (gap - 1))
    note = "not covered recently" if gap is None else f"last covered {gap} video(s) ago"
    if pillar.key == "taxes":
        if tax_season(today):
            bonus += 15
            note += f"; tax season ({filing_year(today)} filing) boost"
        else:
            bonus -= 10
            note += "; outside tax season"
    return bonus, note


# --------------------------------------------------------------------------------------------- recurring series
@dataclass(frozen=True)
class Series:
    name: str
    pillar: str
    concepts: frozenset[str] = field(default_factory=frozenset)
    pitch: str = ""


SERIES = [
    Series("Money Traps", "debt", frozenset({"credit_card", "bnpl", "personal_loan", "auto_loan"}),
           "the costly traps lenders and stores count on"),
    Series("Credit Score Fixes", "debt", frozenset({"credit_report", "credit_score"}),
           "step-by-step fixes for your credit"),
    Series("Debt Escape Plan", "debt", frozenset({"debt_payoff", "student_loan", "debt_collection", "bankruptcy",
                                                  "mortgage"}), "getting out of debt, one plan at a time"),
    Series("Money Traps", "budget", frozenset({"bank_fees", "cost_of_living", "debit_prepaid"}),
           "the costly traps lenders and stores count on"),
    Series("Health Costs", "budget", frozenset({"aca_marketplace"}), "what health coverage really costs you"),
    Series("Savings That Work", "budget", frozenset({"emergency_fund", "hysa", "cd_gic", "bank_account"}),
           "where to keep money so it actually grows"),
    Series("Budget Reset", "budget", frozenset({"budgeting", "spending_psych", "paycheck", "money_relationships",
                                                "inflation_personal"}), "budgets that survive real life"),
    Series("Tax Smart", "taxes", frozenset(), "taxes made simple, all year"),
    Series("Retirement Basics", "retire", frozenset({"retirement_401k", "ira_roth", "retirement_planning", "hsa",
                                                     "fire"}), "retirement accounts explained from zero"),
    Series("Investing 101", "retire", frozenset({"index_funds", "compound", "fees_expense", "bonds", "robo",
                                                 "net_worth", "education_saving"}), "simple, boring investing that works"),
    Series("Scam Alert", "scams", frozenset({"scams", "identity_theft", "money_transfer"}),
           "how today's scams work and how to shut them down"),
    Series("Know Your Rights", "scams", frozenset({"deposit_insurance", "money_mistakes"}),
           "the protections the law already gives you"),
]


def series_for(topic_key: str, today: date) -> str | None:
    p = pillar_of(topic_key)
    if p is None:
        return None
    if p.key == "taxes":
        return f"Tax Season {filing_year(today)}" if tax_season(today) else "Tax Smart"
    for s in SERIES:
        if s.pillar == p.key and topic_key in s.concepts:
            return s.name
    return next((s.name for s in SERIES if s.pillar == p.key), None)


def all_series_names(today: date) -> list[str]:
    names = [s.name for s in SERIES if s.pillar != "taxes"] + ["Tax Smart", f"Tax Season {filing_year(today)}"]
    return list(dict.fromkeys(names))


__all__ = ["PILLARS", "ORDER", "Pillar", "pillar_of", "rejection", "rotation_block", "priority_bonus",
           "tax_season", "filing_year", "series_for", "all_series_names", "SERIES"]
