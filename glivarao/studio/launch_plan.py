"""The first 16 long videos: the US-only launch list, in publishing order (deadline-driven ones first).

US-ONLY: every video is about a US problem and its effect on a US household's money (macro: housing, the stock
market, the Fed, the national debt, banks, recession signals; credit: cards, FICO, BNPL, student loans, auto
loans, mortgages, medical debt). Sponsor-friendly, no political sides, and every video ends with a practical
"What to do" section where one product category fits (its [AFFILIATE: category] placeholder goes in the
description; no real links yet).

Every number comes from an official US source, checked on 22 Nov 2026 (CHECKED) and re-checked on the VPS before
the video is made: the `verify` phrase must still appear on the official page, otherwise the fact is dropped from
the video and the announcement says so. Weekly numbers (mortgage rates) are re-checked the same way.

The list needs your approval in Telegram (python -m glivarao launch-list --send). Until you approve it, no launch
video is planned. Approving the list does NOT resume production; only `python -m glivarao resume` does.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field

log = logging.getLogger(__name__)
CHECKED = "2026-11-22"
VERSION = "us-2026-11-22"

LAUNCH_STYLE = ("US-only: open with the big US story in two or three sentences (what changed nationally, with the "
                "official number from the fact sheet), then pivot fast: 'here's what that means for YOUR household's "
                "money'. Calm and factual, no panic, no political sides. Spend most of the video on concrete steps "
                "for a US household that is stretched thin, free options first, and end with a 'What to do' section "
                "in which the product category given below fits naturally.")


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
    affiliate: str = "budgeting app"   # product category for the "What to do" section and [AFFILIATE: ...]

    def card(self) -> dict:
        from ..research.finance_filter import CONCEPTS

        con = next((c for c in CONCEPTS if c.key == self.key), None)
        return {"key": self.key, "topic": self.topic, "category": con.category if con else "Personal Finance",
                "market": "US", "score": 100.0, "confidence": "high", "launch": self.n, "news": self.news,
                "why": [f"Launch list video {self.n} of 16 (US-only list approved by you)", self.angle],
                "angle": (f"{self.angle} {LAUNCH_STYLE} Product category for the 'What to do' section: "
                          f"{self.affiliate} (category only, no brand names)."),
                "affiliate_category": self.affiliate, "viewer_questions": [], "documented_problems": [],
                "launch_facts": [asdict(f) for f in self.facts], "sources": ["Launch list (official US sources)"]}


# Official US sources (all checked 2026-11-22)
NYFED_HHDC = "https://www.newyorkfed.org/medialibrary/interactives/householdcredit/data/pdf/HHDC_2026Q3.pdf"
G19 = "https://www.federalreserve.gov/releases/g19/current/default.htm"
FOMC_OCT = "https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm"
FOMC_CAL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
PMMS = "https://www.freddiemac.com/pmms"
CENSUS_NRS = "https://www.census.gov/construction/nrs/current/index.html"
DEBT_PENNY = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/"
TIC = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table5.html"
FDIC = "https://www.fdic.gov/resources/deposit-insurance/understanding-deposit-insurance"
CFPB_BNPL = ("https://www.consumerfinance.gov/archive/newsroom/cfpb-research-reveals-heavy-buy-now-pay-later-use-"
             "among-borrowers-with-high-credit-balances-and-multiple-pay-in-four-loans/")
CFPB_MEDICAL = ("https://www.consumerfinance.gov/ask-cfpb/what-should-i-do-if-i-get-a-medical-bill-i-cant-afford-"
                "en-2125/")
CFPB_SCORES = "https://www.consumerfinance.gov/consumer-tools/credit-reports-and-scores/"
ACR = "https://www.annualcreditreport.com/index.action"
SAVE_FAQ = "https://studentaid.gov/articles/save/"
HC_DATES = "https://www.healthcare.gov/quick-guide/dates-and-deadlines/"
HC_FPL = "https://www.healthcare.gov/glossary/federal-poverty-level-fpl/"
IRS_401K = "https://www.irs.gov/newsroom/401k-limit-increases-to-25500-for-2027-ira-limit-remains-7500"
IRS_TY2026 = "https://www.irs.gov/node/151941"
IRS_CHARITY = ("https://www.irs.gov/newsroom/irs-reminder-permanent-charitable-contribution-deduction-begins-for-"
               "returns-filed-next-year-for-taxpayers-who-do-not-itemize")
IRS_GET_READY = "https://www.irs.gov/newsroom/irs-reminder-take-steps-now-to-make-tax-filing-in-2027-easier"

F = LaunchFact
CARD_RATE = F("The average interest rate on credit card accounts that are charged interest was 22.36% "
              "(Federal Reserve G.19, November 2026).", "Federal Reserve G.19", G19, "22.36")
REVOLVING = F("Revolving consumer credit outstanding was $1,368.5 billion (Federal Reserve G.19).",
              "Federal Reserve G.19", G19, "1,368.5")
HH_TOTAL = F("US household debt rose by $334 billion in the third quarter of 2026 to $19.1 trillion, up $5 trillion "
             "since the end of 2019.", "New York Fed Household Debt and Credit Report, 2026 Q3", NYFED_HHDC,
             "19.1 trillion")
HH_DELINQ = F("At the end of September 2026, 5.0% of outstanding US household debt was in some stage of delinquency, "
              "up 0.3 percentage points from the previous quarter.", "New York Fed Household Debt and Credit Report, "
              "2026 Q3", NYFED_HHDC, "5.0%")
FED_RANGE = F("On October 28, 2026 the Federal Reserve kept the federal funds target range at 3-3/4 to 4 percent; "
              "its statement says inflation remains elevated.", "Federal Reserve (FOMC statement)", FOMC_OCT,
              "3-3/4 to 4 percent")
FED_DEC = F("The Fed's next policy meeting is December 8-9, 2026.", "Federal Reserve (FOMC calendar)", FOMC_CAL,
            "December 8-9")
MORTGAGE = F("The 30-year fixed mortgage rate averaged 7.28% as of November 19, 2026, up from 6.26% a year earlier.",
             "Freddie Mac Primary Mortgage Market Survey", PMMS, "7.28%")
NEW_HOME = F("The median sales price of new houses sold in September 2026 was $400,400.", "US Census Bureau (New "
             "Residential Sales)", CENSUS_NRS, "400,400")
HELOC = F("Home equity line of credit balances rose by $23 billion in 2026 Q3 to $481 billion, the 18th quarterly "
          "increase in a row.", "New York Fed Household Debt and Credit Report, 2026 Q3", NYFED_HHDC, "481 billion")
STUDENT = F("US student loan debt stood at $1.66 trillion in 2026 Q3, and 10.9% of balances were 90+ days past due, "
            "up from 10.6% in Q2.", "New York Fed Household Debt and Credit Report, 2026 Q3", NYFED_HHDC, "10.9%")
FDIC_LIMIT = F("FDIC deposit insurance covers $250,000 per depositor, per FDIC-insured bank, for each account "
               "ownership category.", "FDIC", FDIC, "250,000")
ACA_DATES = [F("HealthCare.gov Open Enrollment for 2027 runs November 1, 2026 to January 15, 2027.",
               "HealthCare.gov", HC_DATES, "January 15"),
             F("Enroll by December 15 for coverage that starts January 1.", "HealthCare.gov", HC_DATES,
               "December 15")]

LAUNCH: list[LaunchVideo] = [
    LaunchVideo(1, "fed-december-your-money", "The Fed meets December 8-9: what it means for your card and savings",
                "fed_rates", True,
                "Big US story: the Fed holds rates at 3.75-4% and meets again December 8-9. Explain neutrally what a "
                "hold, cut or hike would change for a household's credit card APR, savings yield and loan offers, "
                "with no prediction.", [FED_RANGE, FED_DEC, CARD_RATE], publish_by="2026-12-07",
                format="explainer", affiliate="high-yield savings"),
    LaunchVideo(2, "holiday-bnpl", "Holiday Buy Now, Pay Later: the pay-in-four trap", "bnpl", False,
                "Big US story: most BNPL borrowers stack several loans at once, right when card rates are near "
                "22%. How the trap works at holiday checkout and a simple way to track every payment.",
                [F("About 63 percent of BNPL borrowers had multiple loans at the same time at some point during the "
                   "year (CFPB research).", "CFPB", CFPB_BNPL, "63 percent"), CARD_RATE],
                publish_by="2026-12-10", format="myth_vs_fact", affiliate="budgeting app"),
    LaunchVideo(3, "aca-dec-15", "ACA deadline December 15: check your 2027 premium", "aca_marketplace", True,
                "Big US story: 2027 premiums are set and the deadline for January 1 coverage is December 15. A "
                "neutral checklist (no politics): compare plans, update income, avoid a gap in coverage.",
                ACA_DATES + [F("With income between 100% and 400% of the federal poverty level you may qualify for "
                               "the premium tax credit.", "HealthCare.gov", HC_FPL, "between 100% and 400%")],
                publish_by="2026-12-13", affiliate="insurance"),
    LaunchVideo(4, "household-debt-19t", "$19.1 trillion: America's household debt and your family", "household_debt",
                True, "Big US story: household debt hit $19.1 trillion and 5% of it is late. Where your household "
                "stands, the warning signs, and a payoff order that works.", [HH_TOTAL, HH_DELINQ, CARD_RATE],
                affiliate="debt payoff"),
    LaunchVideo(5, "mortgage-rates-7", "Mortgage rates back above 7%: what it means for buyers and owners",
                "us_housing", True,
                "Big US story: the 30-year rate is 7.28%, a full point above last year, while the median new home "
                "costs about $400,000. What that does to a monthly payment and the moves that still help buyers "
                "and owners.", [MORTGAGE, NEW_HOME, HELOC], affiliate="high-yield savings"),
    LaunchVideo(6, "minimum-payment-trap", "The minimum payment trap on a 22% credit card", "credit_card", False,
                "Big US story: Americans owe $1.37 trillion in revolving credit at about 22%. The real math of "
                "paying only the minimum and the escape plan.", [CARD_RATE, REVOLVING], affiliate="debt payoff"),
    LaunchVideo(7, "student-loans-after-save", "Student loans after SAVE: 1 in 10 dollars is seriously late",
                "student_loan", True,
                "Big US story: $1.66 trillion in student debt and rising delinquencies after SAVE ended. How to pick "
                "a plan before your servicer's deadline and protect your credit.",
                [STUDENT,
                 F("A court order ended the SAVE plan in March 2026; borrowers who don't choose another plan are moved "
                   "to a fixed payment plan.", "Federal Student Aid", SAVE_FAQ, "ended the SAVE Plan in March 2026"),
                 F("SAVE borrowers get 90 days from their servicer's notice to choose a new plan.",
                   "Federal Student Aid", SAVE_FAQ, "90 days")],
                publish_by="2026-12-20", affiliate="debt payoff"),
    LaunchVideo(8, "fico-myths", "FICO score myths that cost you money", "credit_score", False,
                "Big US story: your score sets the rate on your card, car and mortgage. The myths that keep scores "
                "low and the free checks that fix errors.",
                [F("Checking your own credit report or score does not hurt your score.", "CFPB", CFPB_SCORES, ""),
                 F("You can get free credit reports from all three bureaus at AnnualCreditReport.com.",
                   "AnnualCreditReport.com", ACR, ""), CARD_RATE], format="myth_vs_fact",
                affiliate="credit monitoring"),
    LaunchVideo(9, "medical-bills", "A medical bill you can't pay: your rights before it hits your credit",
                "medical_debt", False,
                "Big US story: medical bills push millions of households into collections. Check the bill, ask for "
                "charity care, use the No Surprises Act, and keep it off your credit.",
                [F("The No Surprises Act, effective January 1, 2022, protects insured patients from certain surprise "
                   "medical bills.", "CFPB", CFPB_MEDICAL, "January 1, 2022"),
                 F("The Affordable Care Act requires nonprofit hospitals to have financial assistance (charity care) "
                   "programs.", "CFPB", CFPB_MEDICAL, "501(c)(3)"),
                 F("4.9% of US consumers had a third-party collection account on their credit report in 2026 Q3.",
                   "New York Fed Household Debt and Credit Report, 2026 Q3", NYFED_HHDC, "4.9%")],
                affiliate="credit monitoring"),
    LaunchVideo(10, "auto-loans", "Car payments are climbing: how not to get stuck in your auto loan", "auto_loan",
                False, "Big US story: Americans took out $208 billion in new auto loans in one quarter and early "
                "auto delinquencies are ticking up. The real cost of a long loan and how to cut your payment.",
                [F("There were $208 billion in new auto loans on credit reports in 2026 Q3, and auto loan balances "
                   "rose by $21 billion.", "New York Fed Household Debt and Credit Report, 2026 Q3", NYFED_HHDC,
                   "208 billion"), HH_DELINQ], affiliate="budgeting app"),
    LaunchVideo(11, "national-debt-40t", "The US national debt passed $40 trillion: what it means for your rates",
                "national_debt", True,
                "Big US story: the national debt is over $40 trillion. No politics: how government borrowing can "
                "keep loan rates higher for households and what to do with your savings and debt.",
                [F("Total US public debt outstanding was over $40.7 trillion on November 19, 2026.",
                   "US Treasury (Debt to the Penny)", DEBT_PENNY, ""), MORTGAGE], affiliate="high-yield savings"),
    LaunchVideo(12, "japan-treasuries", "Japan is selling US Treasuries: why your mortgage rate cares",
                "treasury_market", True,
                "Big US story: Japan, the largest foreign holder, cut its US Treasury holdings by about $147 billion "
                "since April. How foreign selling can lift US yields and your mortgage and card rates.",
                [F("Japan held $1,063.1 billion of US Treasury securities at the end of September 2026, down from "
                   "$1,209.9 billion at the end of April 2026.", "US Treasury (TIC, major foreign holders)", TIC,
                   "1063.1"), MORTGAGE], affiliate="high-yield savings"),
    LaunchVideo(13, "is-your-bank-safe", "Is your money safe in a US bank? The $250,000 rule explained", "us_banks",
                False, "Big US story: bank worries come back every time rates move. How FDIC insurance really works, "
                "how to check your bank, and where to keep an emergency fund.", [FDIC_LIMIT],
                format="explainer", affiliate="high-yield savings"),
    LaunchVideo(14, "recession-signals", "Recession signals: how to recession-proof your household", "recession",
                False, "Big US story: delinquencies and foreclosures are inching up while the Fed says inflation is "
                "still elevated. Calm, no predictions: the signals to watch and a household checklist.",
                [HH_DELINQ, F("About 62,000 people had new foreclosures on their credit reports in 2026 Q3, up from the "
                              "previous quarter.", "New York Fed Household Debt and Credit Report, 2026 Q3",
                              NYFED_HHDC, "62,000"), FED_RANGE], affiliate="high-yield savings"),
    LaunchVideo(15, "stock-market-401k", "Stock market swings and your 401(k): the 2027 limits", "us_stock_market",
                True, "Big US story: market swings worry savers. What a drop means for a 401(k), why the emergency "
                "fund comes first, and the new 2027 limits.",
                [F("The 2027 401(k) limit is $25,500, up from $24,500 for 2026.", "IRS (IR-2026-136)", IRS_401K,
                   "25,500"),
                 F("The IRA limit stays at $7,500 for 2027.", "IRS (IR-2026-136)", IRS_401K, "7,500")],
                affiliate="high-yield savings"),
    LaunchVideo(16, "tax-season-2027", "Tax season 2027: what changes on your return", "tax_filing", True,
                "Big US story: the first filing season under the new rules. What changes on your 2026 return and "
                "how to get your refund faster (IRS Free File first).",
                [F("For 2026 returns (filed in 2027) the standard deduction is $16,100 single and $32,200 married "
                   "filing jointly.", "IRS (tax year 2026 adjustments)", IRS_TY2026, "16,100"),
                 F("Non-itemizers can deduct up to $1,000 of cash gifts to qualified charities ($2,000 married filing "
                   "jointly) starting with 2026 returns.", "IRS (IR-2026-135)", IRS_CHARITY, "$2,000"),
                 F("The IRS encourages taxpayers to get ready now for the 2027 filing season.", "IRS (IR-2026-140)",
                   IRS_GET_READY, "")], affiliate="tax software"),
]


# ------------------------------------------------------------------------------------------------ state
def done(store) -> list[int]:
    return json.loads(store.kv_get("launch_done", "[]"))


def approved(store) -> bool:
    return store.kv_get("launch_approved", "") == VERSION


def approve(store) -> None:
    """Your approval of THIS list: it starts from video 1 (videos made from the old list are kept as they are)."""
    if not approved(store):
        store.kv_set("launch_done", "[]")
    store.kv_set("launch_approved", VERSION)


def awaiting_approval(store) -> bool:
    """True while the current list is waiting for your approval and still has videos to make."""
    return not approved(store) and remaining(store) > 0


def next_video(store) -> LaunchVideo | None:
    if not approved(store):
        return None
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
                    timeout=60)
    r.raise_for_status()
    if url.lower().endswith(".pdf") or "pdf" in r.headers.get("content-type", "").lower():
        import io

        from pypdf import PdfReader

        pages = PdfReader(io.BytesIO(r.content)).pages[:6]  # the summary pages hold the headline numbers
        return re.sub(r"\s+", " ", " ".join(p.extract_text() or "" for p in pages))
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


def approval_text() -> str:
    lines = [f"🇺🇸 GLIVARAO launch list (US-only, {len(LAUNCH)} long videos) — please approve",
             "Every video: a US problem → what it means for a US household's money; US data only; sponsor-friendly "
             "(no profanity, no panic, no political sides); ends with \"What to do\" + [AFFILIATE: category] in the "
             f"description (no real links yet). Facts checked on official pages {CHECKED}, re-checked before each "
             "video.", ""]
    for v in LAUNCH:
        due = f" · by {v.publish_by[5:]}" if v.publish_by else ""
        srcs = ", ".join(dict.fromkeys(f.source.split(" (")[0].split(",")[0] for f in v.facts))
        lines.append(f"{v.n}. {v.topic}{due}\n   [{v.affiliate}] {srcs}")
    lines += ["", "Approving the list does NOT restart production: it stays paused until you send resume."]
    return "\n".join(lines)


def send_for_approval(settings, store, client=None) -> dict:
    from ..publish.telegram import _client

    c = _client(settings, client)
    msg = c.call("sendMessage", chat_id=settings.telegram_approver_chat_id, text=approval_text()[:4000],
                 reply_markup={"inline_keyboard": [[{"text": "✅ Approve this list", "callback_data": f"launch:{VERSION}"},
                                                    {"text": "✏️ Request changes", "callback_data": "launchedit:x"}]]})
    store.kv_set("launch_sent", VERSION)
    return msg


__all__ = ["LAUNCH", "LaunchVideo", "LaunchFact", "next_video", "mark_done", "done", "remaining", "verify_facts",
           "LAUNCH_STYLE", "VERSION", "approved", "approve", "awaiting_approval", "approval_text",
           "send_for_approval"]
