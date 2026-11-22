"""The first 16 long videos: the US-only, EVERGREEN-first launch list, in publishing order.

EVERGREEN rule: 14 of the 16 are evergreen (topics people search every month for years; titles and scripts carry
no dates or "this week" wording; current numbers are stated "as of <Month Year>" so they are easy to update).
At most 2 are time-sensitive (date-bound), spaced so there is never more than 1 in a week.

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
VERSION = "us-evergreen-2026-11-22"
MAX_TIMELY = 2

LAUNCH_STYLE = ("US-only: open with the big US picture in two or three sentences (with the official number from the "
                "fact sheet, stated 'as of <Month Year>'), then pivot fast: 'here's what that means for YOUR "
                "household's money'. Teach how it works so the video stays useful for years. Calm and factual, no "
                "panic, no political sides. Spend most of the video on concrete steps for a US household that is "
                "stretched thin, free options first, and end with a 'What to do' section in which the product "
                "category given below fits naturally.")


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
FED_MP = "https://www.federalreserve.gov/aboutthefed/fedexplained/monetary-policy.htm"
PMMS = "https://www.freddiemac.com/pmms"
CENSUS_NRS = "https://www.census.gov/construction/nrs/current/index.html"
DEBT_PENNY = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/"
TIC = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table5.html"
FDIC = "https://www.fdic.gov/resources/deposit-insurance/understanding-deposit-insurance"
FDIC_FAILED = "https://www.fdic.gov/resources/resolutions/bank-failures/failed-bank-list"
FDIC_CRISIS = "https://www.fdic.gov/bank/historical/crisis/overview.pdf"
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
HHDC = "New York Fed Household Debt and Credit Report"
CARD_RATE = F("As of November 2026, the average interest rate on credit card accounts charged interest was 22.36% "
              "(Federal Reserve G.19).", "Federal Reserve G.19", G19, "22.36")
REVOLVING = F("As of November 2026, Americans owed $1,368.5 billion in revolving credit (Federal Reserve G.19).",
              "Federal Reserve G.19", G19, "1,368.5")
HH_TOTAL = F("As of the third quarter of 2026, US household debt was $19.1 trillion, up $5 trillion since the end of "
             "2019.", f"{HHDC}, 2026 Q3", NYFED_HHDC, "19.1 trillion")
HH_DELINQ = F("As of September 2026, 5.0% of outstanding US household debt was in some stage of delinquency.",
              f"{HHDC}, 2026 Q3", NYFED_HHDC, "5.0%")
FORECLOSE = F("About 62,000 people had a new foreclosure on their credit report in the third quarter of 2026.",
              f"{HHDC}, 2026 Q3", NYFED_HHDC, "62,000")
FED_GOALS = F("The Fed's two goals, set by Congress, are maximum employment and stable prices; it pursues them by "
              "influencing short-term interest rates.", "Federal Reserve (monetary policy explainer)", FED_MP,
              "maximum employment")
FED_RANGE = F("As of October 28, 2026, the Fed's target range for the federal funds rate was 3-3/4 to 4 percent.",
              "Federal Reserve (FOMC statement)", FOMC_OCT, "3-3/4 to 4 percent")
MORTGAGE = F("As of November 19, 2026, the 30-year fixed mortgage rate averaged 7.28%, up from 6.26% a year earlier.",
             "Freddie Mac Primary Mortgage Market Survey", PMMS, "7.28%")
NEW_HOME = F("As of September 2026, the median sales price of a new house in the US was $400,400.",
             "US Census Bureau (New Residential Sales)", CENSUS_NRS, "400,400")
MORT_BAL = F("As of September 2026, mortgage balances on US credit reports totaled $13.4 trillion.",
             f"{HHDC}, 2026 Q3", NYFED_HHDC, "13.4 trillion")
CRISIS_BANKS = F("From 2008 through 2013 almost 500 US banks failed, costing the FDIC's Deposit Insurance Fund about "
                 "$73 billion.", "FDIC, Crisis and Response: An FDIC History, 2008-2013", FDIC_CRISIS,
                 "almost 500 banks failed")
CRISIS_CAUSE = F("Weakened mortgage lending standards (subprime, Alt-A and hybrid ARM loans) and complex, opaque "
                 "securitization were central to the 2008 crisis.", "FDIC, Crisis and Response: An FDIC History, "
                 "2008-2013", FDIC_CRISIS, "subprime, Alt-A, and hybrid ARM")
INDYMAC = F("IndyMac failed in June 2008 with losses of about $12 billion.", "FDIC, Crisis and Response: An FDIC "
            "History, 2008-2013", FDIC_CRISIS, "IndyMac")
FDIC_LIMIT = F("FDIC deposit insurance covers $250,000 per depositor, per FDIC-insured bank, for each account "
               "ownership category.", "FDIC", FDIC, "250,000")
STUDENT = F("As of the third quarter of 2026, US student loan debt was $1.66 trillion and 10.9% of balances were 90+ "
            "days past due.", f"{HHDC}, 2026 Q3", NYFED_HHDC, "10.9%")
DEBT_40T = F("As of November 19, 2026, total US public debt outstanding was over $40.7 trillion.",
             "US Treasury (Debt to the Penny)", DEBT_PENNY, "")
JAPAN = F("As of September 2026, Japan, the largest foreign holder, owned $1,063.1 billion of US Treasury securities, "
          "down from $1,209.9 billion in April 2026.", "US Treasury (TIC, major foreign holders)", TIC, "1063.1")

LAUNCH: list[LaunchVideo] = [
    LaunchVideo(1, "get-out-of-card-debt", "How to get out of credit card debt (a plan that works)", "credit_card",
                False, "Evergreen: how card interest really piles up, the real math of a balance at 22%, and a "
                "step-by-step way out that works on any income.", [CARD_RATE, REVOLVING], affiliate="debt payoff"),
    LaunchVideo(2, "aca-dec-15", "ACA deadline December 15: check your 2027 premium", "aca_marketplace", True,
                "TIMELY (deadline): coverage that starts January 1 needs enrollment by December 15. A neutral "
                "checklist (no politics): compare plans, update income, avoid a coverage gap.",
                [F("HealthCare.gov Open Enrollment for 2027 runs November 1, 2026 to January 15, 2027.",
                   "HealthCare.gov", HC_DATES, "January 15"),
                 F("Enroll by December 15 for coverage that starts January 1.", "HealthCare.gov", HC_DATES,
                   "December 15"),
                 F("With income between 100% and 400% of the federal poverty level you may qualify for the premium "
                   "tax credit.", "HealthCare.gov", HC_FPL, "between 100% and 400%")],
                publish_by="2026-12-13", affiliate="insurance"),
    LaunchVideo(3, "how-credit-scores-work", "How credit scores really work", "credit_score", False,
                "Evergreen: what actually moves a FICO score, the myths that keep it low, and the free checks that "
                "fix errors.",
                [F("Checking your own credit report or score does not hurt your score.", "CFPB", CFPB_SCORES, ""),
                 F("You can get free credit reports from all three bureaus at AnnualCreditReport.com.",
                   "AnnualCreditReport.com", ACR, ""),
                 F("As of the third quarter of 2026, 4.9% of US consumers had a third-party collection account on "
                   "their credit report.", f"{HHDC}, 2026 Q3", NYFED_HHDC, "4.9%")],
                format="myth_vs_fact", affiliate="credit monitoring"),
    LaunchVideo(4, "how-the-fed-affects-you", "How the Fed affects your money", "fed_rates", False,
                "Evergreen: what the Federal Reserve does, how its rate decisions flow into your card APR, savings "
                "yield, car loan and mortgage, and what a household can do whichever way rates go.",
                [FED_GOALS, FED_RANGE, CARD_RATE], format="explainer", affiliate="high-yield savings"),
    LaunchVideo(5, "snowball-vs-avalanche", "Debt snowball vs debt avalanche: which pays off debt faster",
                "debt_payoff", False, "Evergreen: the two classic payoff methods side by side with the real math, "
                "and how to pick the one you'll actually stick with.", [CARD_RATE, HH_TOTAL], format="comparison",
                affiliate="debt payoff"),
    LaunchVideo(6, "why-houses-expensive", "Why houses got so expensive", "us_housing", False,
                "Evergreen: the forces behind US home prices (prices, rates, supply) explained simply, what that "
                "means for buyers and owners, and the moves that still help.", [NEW_HOME, MORTGAGE, MORT_BAL],
                format="explainer", affiliate="high-yield savings"),
    LaunchVideo(7, "what-caused-2008", "What caused the 2008 financial crisis (and could it happen again?)",
                "financial_crisis", False, "Evergreen: the chain from easy mortgages to frozen credit markets, "
                "explained step by step, and the household lessons that still protect your money.",
                [CRISIS_CAUSE, CRISIS_BANKS, INDYMAC], format="explainer", affiliate="high-yield savings"),
    LaunchVideo(8, "what-happens-in-recession", "What happens in a recession (and how to protect your household)",
                "recession", False, "Evergreen, calm, no predictions: what typically happens to jobs, credit and "
                "savings in a US recession, the signals people watch, and a household checklist.",
                [HH_DELINQ, FORECLOSE, FED_GOALS], affiliate="high-yield savings"),
    LaunchVideo(9, "national-debt-problem", "Is the US national debt a problem? What it means for your money",
                "national_debt", False, "Evergreen, no politics: what the national debt is, who owns it, how heavy "
                "government borrowing can keep loan rates higher for households, and what to do about it.",
                [DEBT_40T, JAPAN, MORTGAGE], format="explainer", affiliate="high-yield savings"),
    LaunchVideo(10, "how-bank-failures-work", "How bank failures work (and how FDIC insurance protects you)",
                "us_banks", False, "Evergreen: what happens when a US bank fails, exactly what FDIC insurance "
                "covers, and how to keep every dollar insured.",
                [FDIC_LIMIT, INDYMAC, CRISIS_BANKS,
                 F("The FDIC keeps a public list of every bank that has failed since October 1, 2000.", "FDIC",
                   FDIC_FAILED, "since October 1, 2000")], format="explainer", affiliate="high-yield savings"),
    LaunchVideo(11, "bnpl-trap", "Buy Now, Pay Later: how the trap works", "bnpl", False,
                "Evergreen: how pay-in-four loans stack up, why most borrowers end up with several at once, and a "
                "simple way to track every payment.",
                [F("About 63 percent of BNPL borrowers had multiple loans at the same time at some point during the "
                   "year (CFPB research).", "CFPB", CFPB_BNPL, "63 percent"), CARD_RATE],
                format="myth_vs_fact", affiliate="budgeting app"),
    LaunchVideo(12, "student-loan-plan", "How to choose a student loan repayment plan", "student_loan", False,
                "Evergreen: how federal repayment plans work, how to compare them, and how to protect your credit "
                "if you fall behind.",
                [STUDENT,
                 F("A court order ended the SAVE plan in March 2026; borrowers who don't choose another plan are moved "
                   "to a fixed payment plan.", "Federal Student Aid", SAVE_FAQ, "ended the SAVE Plan in March 2026"),
                 F("SAVE borrowers get 90 days from their servicer's notice to choose a new plan.",
                   "Federal Student Aid", SAVE_FAQ, "90 days")], affiliate="debt payoff"),
    LaunchVideo(13, "medical-bills-rights", "Medical bills you can't pay: your rights", "medical_debt", False,
                "Evergreen: check the bill, ask for charity care, use the No Surprises Act, and keep medical debt off "
                "your credit.",
                [F("The No Surprises Act, effective January 1, 2022, protects insured patients from certain surprise "
                   "medical bills.", "CFPB", CFPB_MEDICAL, "January 1, 2022"),
                 F("The Affordable Care Act requires nonprofit hospitals to have financial assistance (charity care) "
                   "programs.", "CFPB", CFPB_MEDICAL, "501(c)(3)")], affiliate="credit monitoring"),
    LaunchVideo(14, "auto-loan-trap", "How car loans trap buyers (and how to avoid it)", "auto_loan", False,
                "Evergreen: how long loans, add-ons and rolled-over balances make cars cost far more, and how to cut "
                "the payment.",
                [F("Americans took out $208 billion in new auto loans in the third quarter of 2026.",
                   f"{HHDC}, 2026 Q3", NYFED_HHDC, "208 billion"), HH_DELINQ], affiliate="budgeting app"),
    LaunchVideo(15, "stock-market-401k", "What a stock market drop means for your 401(k)", "us_stock_market", False,
                "Evergreen: why markets rise and fall, what a drop does (and doesn't do) to a 401(k), and why the "
                "emergency fund comes first.",
                [F("For 2027, the 401(k) contribution limit is $25,500.", "IRS (IR-2026-136)", IRS_401K, "25,500"),
                 F("For 2027, the IRA contribution limit is $7,500.", "IRS (IR-2026-136)", IRS_401K, "7,500")],
                affiliate="high-yield savings"),
    LaunchVideo(16, "tax-season-2027", "Tax season 2027: what changes on your return", "tax_filing", True,
                "TIMELY (filing season): what changes on 2026 returns and how to get your refund faster (IRS Free "
                "File first).",
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

        pages = PdfReader(io.BytesIO(r.content)).pages[:20]  # summaries and overviews hold the headline numbers
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
    timely = sum(v.news for v in LAUNCH)
    lines = [f"🇺🇸 GLIVARAO launch list (US-only, {len(LAUNCH)} long videos: {len(LAUNCH) - timely} evergreen, "
             f"{timely} timely) — please approve",
             "Evergreen = searched every month for years; no dates or \"this week\" in titles or scripts; current "
             "numbers as \"as of <Month Year>\". Timely videos: max 1 per week.",
             "Every video: a US problem → what it means for a US household's money; US data only; sponsor-friendly "
             "(no profanity, no panic, no political sides); ends with \"What to do\" + [AFFILIATE: category] in the "
             f"description (no real links yet). Facts checked on official pages {CHECKED}, re-checked before each "
             "video.", ""]
    for v in LAUNCH:
        due = f" · by {v.publish_by[5:]}" if v.publish_by else ""
        srcs = ", ".join(dict.fromkeys(f.source.split(" (")[0].split(",")[0] for f in v.facts))
        kind = "⏰ timely" if v.news else "🌲 evergreen"
        lines.append(f"{v.n}. {v.topic}{due}\n   {kind} · [{v.affiliate}] {srcs}")
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
