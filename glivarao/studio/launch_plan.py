"""The first 16 long videos: the creator's launch list, in publishing order (timely ones first).

Every number comes from an official source, checked on 19 Nov 2026 (see `verified`) and re-checked on the VPS
before the video is made (`python -m glivarao verify-facts`): the `verify` phrase must still appear on the
official page, otherwise the fact is dropped from the video and the announcement says so.

Style for every video: "big economic story -> what it means for YOUR money" (see LAUNCH_STYLE).
The launch list overrides the automatic pillar/news rules; the 60% debt-and-credit rule starts after it.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field

log = logging.getLogger(__name__)
CHECKED = "2026-11-19"

LAUNCH_STYLE = ("Open with the big economic story in two or three sentences (what changed nationally, with the "
                "official number), then pivot fast: 'here's what that means for YOUR money'. Spend most of the "
                "video on concrete steps for a 25-45-year-old who is stretched thin. Free options first.")


@dataclass
class LaunchFact:
    text: str
    source: str
    url: str
    verify: str = ""          # phrase that must appear on the page (empty = rule/explanation, no number)


@dataclass
class LaunchVideo:
    n: int
    slug: str
    topic: str
    key: str                  # research concept (pillar, series, family)
    news: bool                # news-driven (counts toward the 1-in-4 news limit after launch)
    angle: str
    facts: list[LaunchFact] = field(default_factory=list)
    publish_by: str = ""      # latest sensible publish date (deadline-driven topics)
    format: str = ""          # preferred format ("" = rotation)

    def card(self) -> dict:
        from ..research.finance_filter import CONCEPTS

        con = next((c for c in CONCEPTS if c.key == self.key), None)
        return {"key": self.key, "topic": self.topic, "category": con.category if con else "Personal Finance",
                "market": "US", "score": 100.0, "confidence": "high", "launch": self.n, "news": self.news,
                "why": [f"Launch list video {self.n} of 16 (your list)", self.angle],
                "angle": f"{self.angle} {LAUNCH_STYLE}", "viewer_questions": [], "documented_problems": [],
                "launch_facts": [asdict(f) for f in self.facts], "sources": ["Launch list (official sources)"]}


IRS_401K = "https://www.irs.gov/newsroom/401k-limit-increases-to-25500-for-2027-ira-limit-remains-7500"
IRS_TY2027 = ("https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2027-taxpayers-"
              "continue-to-benefit-from-the-working-families-tax-cuts")
IRS_TY2026 = "https://www.irs.gov/node/151941"
IRS_CHARITY = ("https://www.irs.gov/newsroom/irs-reminder-permanent-charitable-contribution-deduction-begins-for-"
               "returns-filed-next-year-for-taxpayers-who-do-not-itemize")
IRS_GET_READY = "https://www.irs.gov/newsroom/irs-reminder-take-steps-now-to-make-tax-filing-in-2027-easier"
IRS_SCAMS = "https://www.irs.gov/help/tax-scams/recognize-tax-scams-and-fraud"
IRS_REALLY = ("https://www.irs.gov/newsroom/how-to-know-its-really-the-irs-calling-or-knocking-on-your-door-"
              "collection")
HC_DATES = "https://www.healthcare.gov/quick-guide/dates-and-deadlines/"
HC_FPL = "https://www.healthcare.gov/glossary/federal-poverty-level-fpl/"
FPL = "https://aspe.hhs.gov/topics/poverty-economic-mobility/poverty-guidelines"
G19 = "https://www.federalreserve.gov/releases/g19/current/default.htm"
SAVE_FAQ = "https://studentaid.gov/articles/save/"
ED_SAVE = ("https://www.ed.gov/about/news/press-release/us-department-of-education-announces-next-steps-borrowers-"
           "enrolled-unlawful-save-plan")
CFPB_BNPL = ("https://www.consumerfinance.gov/archive/newsroom/cfpb-research-reveals-heavy-buy-now-pay-later-use-"
             "among-borrowers-with-high-credit-balances-and-multiple-pay-in-four-loans/")
FTC_2025 = ("https://www.ftc.gov/news-events/news/press-releases/2026/06/ftc-data-show-people-reported-losing-3-point-"
            "5-billion-imposter-scams-2025")
CFPB_SCORES = "https://www.consumerfinance.gov/consumer-tools/credit-reports-and-scores/"
ACR = "https://www.annualcreditreport.com/index.action"

F = LaunchFact
CARD_RATE = F("The average interest rate on credit card accounts that are charged interest was 22.36% "
              "(Federal Reserve G.19, released November 6, 2026).", "Federal Reserve G.19", G19, "22.36")
ACA_DATES = [F("HealthCare.gov Open Enrollment for 2027 runs November 1, 2026 to January 15, 2027.",
               "HealthCare.gov", HC_DATES, "January 15"),
             F("Enroll by December 15 for coverage that starts January 1.", "HealthCare.gov", HC_DATES,
               "December 15")]
ACA_CLIFF = [F("With income between 100% and 400% of the federal poverty level you qualify for the premium tax "
               "credit; above 400% you don't (the extra subsidies of 2021-2025 have expired).", "HealthCare.gov",
               HC_FPL, "between 100% and 400%"),
             F("The 2026 federal poverty guideline is $15,960 for one person and $33,000 for a family of four "
               "(48 states and DC), so 400% is $63,840 for a single person and $132,000 for a family of four.",
               "HHS poverty guidelines", FPL, "15,960")]

LAUNCH: list[LaunchVideo] = [
    LaunchVideo(1, "aca-2027-cliff", "ACA 2027: the subsidy cliff is back", "aca_marketplace", True,
                "Big story: the extra ACA subsidies ended, and the 400% income cliff returned for 2027. What it "
                "means for your premium, and how to check if you're near the cliff.", ACA_CLIFF + ACA_DATES[:1],
                publish_by="2026-12-10", format="explainer"),
    LaunchVideo(2, "holiday-scams", "Holiday scams that empty your account", "scams", True,
                "Big story: Americans reported record fraud losses in 2025. What the top holiday scams look like "
                "and the free steps that stop them.",
                [F("People reported losing $3.5 billion to imposter scams in 2025, the most-reported fraud for the "
                   "ninth year in a row.", "FTC", FTC_2025, "3.5 billion"),
                 F("Total reported fraud losses in 2025 were about $16 billion, the highest on record.", "FTC",
                   FTC_2025, "")], publish_by="2026-12-05"),
    LaunchVideo(3, "bnpl-trap", "The Buy Now, Pay Later trap", "bnpl", False,
                "Big story: pay-in-four loans exploded, and most borrowers stack several at once. How the trap "
                "works at checkout and how to use BNPL without getting caught.",
                [F("In 2022, about 63% of BNPL borrowers had multiple loans at the same time at some point in the "
                   "year, and 33% borrowed from more than one BNPL company.", "CFPB", CFPB_BNPL, "63"),
                 CARD_RATE], publish_by="2026-12-12", format="myth_vs_fact"),
    LaunchVideo(4, "aca-dec-15", "ACA deadline: what to do before December 15", "aca_marketplace", True,
                "Big story: millions face higher 2027 premiums. A step-by-step checklist before the December 15 "
                "deadline so coverage starts January 1.", ACA_DATES + ACA_CLIFF[1:], publish_by="2026-12-13"),
    LaunchVideo(5, "minimum-payment-trap", "The minimum payment trap", "credit_card", False,
                "Big story: card rates near record highs. Exactly what paying only the minimum costs you, with "
                "the real math, and the escape plan.", [CARD_RATE,
                F("Revolving consumer credit outstanding was $1,368.5 billion (Federal Reserve G.19).",
                  "Federal Reserve G.19", G19, "1,368.5")]),
    LaunchVideo(6, "401k-2027", "401(k) limit 2027: what it means for you", "retirement_401k", True,
                "Big story: the IRS raised the 2027 401(k) limit. What it means if you can only save a little.",
                [F("The 2027 401(k) limit is $25,500, up from $24,500 for 2026.", "IRS (IR-2026-136)", IRS_401K,
                   "25,500"),
                 F("The 2027 catch-up for ages 50 and over is $8,500, so they can contribute up to $34,000.",
                   "IRS (IR-2026-136)", IRS_401K, "34,000"),
                 F("For ages 60 to 63 the 2027 catch-up is $11,750.", "IRS (IR-2026-136)", IRS_401K, "11,750"),
                 F("The IRA limit stays at $7,500 for 2027; the IRA catch-up for 50 and over stays at $1,100.",
                   "IRS (IR-2026-136)", IRS_401K, "1,100")]),
    LaunchVideo(7, "save-ended", "SAVE is over: your student loan options now", "student_loan", True,
                "Big story: a court order ended the SAVE plan. What happens to your payment and how to pick the "
                "right plan before your deadline.",
                [F("A court order ended the SAVE plan in March 2026; if you don't choose another plan you'll be "
                   "enrolled in a fixed payment plan.", "Federal Student Aid", SAVE_FAQ, "ended the SAVE Plan in "
                   "March 2026"),
                 F("Servicers started sending notices to SAVE borrowers on July 1, 2026.", "Federal Student Aid",
                   SAVE_FAQ, "July 1, 2026"),
                 F("Servicers notify SAVE borrowers in groups; you get 90 days from your servicer's notice to "
                   "choose a new plan, and all SAVE borrowers are notified before the end of 2026.",
                   "Federal Student Aid", SAVE_FAQ, "90 days"),
                 F("The Repayment Assistance Plan (RAP) and the Tiered Standard plan launched July 1, 2026.",
                   "U.S. Department of Education", ED_SAVE, "Repayment Assistance Plan")],
                publish_by="2026-12-20"),
    LaunchVideo(8, "year-end-tax-moves", "Year-end tax moves before December 31", "income_tax", True,
                "Big story: new tax rules hit 2026 returns. The few moves that still count if you act before "
                "December 31.",
                [F("Starting with tax year 2026, people who don't itemize can deduct up to $1,000 of cash gifts to "
                   "qualified charities, or $2,000 for married couples filing jointly.", "IRS (IR-2026-135)",
                   IRS_CHARITY, "$1,000"),
                 F("The 2026 401(k) limit is $24,500.", "IRS (IR-2026-136)", IRS_401K, "24,500"),
                 F("The 2026 standard deduction is $16,100 for single filers and $32,200 for married couples "
                   "filing jointly.", "IRS (tax year 2026 adjustments)", IRS_TY2026, "16,100")],
                publish_by="2026-12-28"),
    LaunchVideo(9, "subscriptions", "The subscription leak in your budget", "cost_of_living", False,
                "Big story: everyday prices keep climbing, and small monthly charges add up quietly. Find and "
                "cancel the leaks in one evening.", [], format="explainer"),
    LaunchVideo(10, "aca-jan-15", "ACA: last chance before January 15", "aca_marketplace", True,
                "Big story: open enrollment ends January 15. Who should still act, how the cliff works, and "
                "how to avoid paying back subsidies at tax time.", ACA_DATES + ACA_CLIFF,
                publish_by="2027-01-12"),
    LaunchVideo(11, "fake-irs-calls", "Fake IRS calls: how to spot them", "scams", False,
                "Big story: tax season is scam season. How real IRS contact works and the red flags of a fake.",
                [F("The IRS usually contacts people first by mail, and never demands immediate payment by gift "
                   "card, wire or payment app.", "IRS", IRS_REALLY, ""),
                 F("IRS list of current tax scams.", "IRS", IRS_SCAMS, "")]),
    LaunchVideo(12, "holiday-debt-90-days", "Holiday debt: your 90-day payoff plan", "debt_payoff", False,
                "Big story: Americans carry over a trillion dollars in revolving debt, and January is when the "
                "bill lands. A 90-day plan with the real math.", [CARD_RATE,
                F("Revolving consumer credit outstanding was $1,368.5 billion (Federal Reserve G.19).",
                  "Federal Reserve G.19", G19, "1,368.5")]),
    LaunchVideo(13, "50-30-20", "The 50/30/20 budget, done honestly", "budgeting", False,
                "Big story: costs are up and paychecks are stretched. Does 50/30/20 still work, and how to adapt "
                "it to your real numbers.", [], format="explainer"),
    LaunchVideo(14, "credit-score-myths", "Credit score myths that cost you money", "credit_score", False,
                "Big story: your score sets the rate you pay on almost everything. The myths that keep it low.",
                [F("Checking your own credit report or score does not hurt your score.", "CFPB", CFPB_SCORES, ""),
                 F("You can get free credit reports from all three bureaus at AnnualCreditReport.com.",
                   "AnnualCreditReport.com", ACR, "")], format="myth_vs_fact"),
    LaunchVideo(15, "roth-vs-401k", "Roth IRA vs 401(k): where your next dollar goes", "ira_roth", False,
                "Big story: the 2027 limits are set. A simple order for where your next dollar should go.",
                [F("The 2027 401(k) limit is $25,500.", "IRS (IR-2026-136)", IRS_401K, "25,500"),
                 F("The IRA limit stays at $7,500 for 2027.", "IRS (IR-2026-136)", IRS_401K, "7,500")],
                format="comparison"),
    LaunchVideo(16, "tax-season-2027", "Tax season 2027: what's different this year", "tax_filing", True,
                "Big story: the first filing season under the new tax law. What changes on your 2026 return and "
                "how to get your refund faster.",
                [F("For 2026 returns (filed in 2027) the standard deduction is $16,100 single and $32,200 married "
                   "filing jointly.", "IRS (tax year 2026 adjustments)", IRS_TY2026, "16,100"),
                 F("Non-itemizers can deduct up to $1,000 of cash gifts to qualified charities ($2,000 married "
                   "filing jointly) starting with 2026 returns.", "IRS (IR-2026-135)", IRS_CHARITY, "$2,000"),
                 F("The IRS encourages taxpayers to get ready now for the 2027 filing season.", "IRS (IR-2026-140)",
                   IRS_GET_READY, "")]),
]


# ------------------------------------------------------------------------------------------------ state
def done(store) -> list[int]:
    return json.loads(store.kv_get("launch_done", "[]"))


def next_video(store) -> LaunchVideo | None:
    d = set(done(store))
    return next((v for v in LAUNCH if v.n not in d), None)


def mark_done(store, n: int) -> None:
    store.kv_set("launch_done", json.dumps(sorted(set(done(store)) | {n})))


def remaining(store) -> int:
    return len([v for v in LAUNCH if v.n not in set(done(store))])


# ------------------------------------------------------------------------------------------ verification
def _page_text(url: str, session) -> str:
    import html

    r = session.get(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) GLIVARAO fact check"},
                    timeout=30)
    r.raise_for_status()
    t = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", "", r.text)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))


def verify_facts(video: LaunchVideo, session=None) -> tuple[list[LaunchFact], list[tuple[LaunchFact, str]]]:
    """(kept, notes). A fact with a `verify` phrase is DROPPED if the page opens and the phrase is gone (the number
    probably changed). If the page can't be opened (some agencies block automated readers), the fact is kept as
    checked on CHECKED and noted, so you can confirm it in the review. Facts without a phrase are kept."""
    import requests

    session = session or requests.Session()
    cache: dict[str, str | Exception] = {}
    kept, dropped = [], []
    for f in video.facts:
        if not f.verify:
            kept.append(f)
            continue
        if f.url not in cache:
            try:
                cache[f.url] = _page_text(f.url, session)
            except Exception as exc:  # noqa: BLE001
                cache[f.url] = exc
        page = cache[f.url]
        if isinstance(page, Exception):
            kept.append(f)
            dropped.append((f, f"kept as checked on {CHECKED}; could not re-open the page ({type(page).__name__}) "
                               "- confirm it in the review"))
        elif f.verify.lower() in page.lower():
            kept.append(f)
        else:
            dropped.append((f, f"DROPPED: '{f.verify}' is no longer on the page (the number may have changed)"))
    return kept, dropped


__all__ = ["LAUNCH", "LaunchVideo", "LaunchFact", "next_video", "mark_done", "done", "remaining", "verify_facts",
           "LAUNCH_STYLE"]
