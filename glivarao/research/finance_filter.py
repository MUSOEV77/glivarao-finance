"""Finance-only gate, category and market tagging.

The CONCEPTS vocabulary is a *classifier and merger*, not a topic list: candidates are discovered from
the data sources, and any finance-related candidate that matches no concept is still kept on its own.

Gate rules (both must pass):
  1. the text contains finance vocabulary (FINANCE_TERMS or a concept synonym), and
  2. it contains none of the off-topic markers (politics, geopolitics, general economics, news, etc.).
Everything rejected is logged with the reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CATEGORIES = [
    "Personal Finance", "Financial Psychology", "Investing", "Credit and Debt",
    "Saving and Wealth Building", "Banking and Money", "Financial Mistakes and Scams",
]


@dataclass(frozen=True)
class Concept:
    key: str
    label: str
    patterns: tuple[str, ...]
    category: str
    market: str = "both"          # US | CA | both
    numeric_hook: bool = False     # exact math can illustrate it (strong chart/thumbnail number)
    wiki: str = ""                 # English Wikipedia article for pageview demand


def C(key, label, pats, cat, market="both", num=False, wiki=""):
    return Concept(key, label, tuple(pats), cat, market, num, wiki)


CONCEPTS = [
    # Credit and Debt
    C("credit_report", "Credit reports and credit report errors", [r"credit report", r"credit-report", r"consumer report",
      r"credit bureau", r"equifax", r"experian", r"transunion", r"information on your report", r"\breport\b.*\bincorrect"],
      "Credit and Debt", wiki="Credit_report"),
    C("credit_score", "Credit scores", [r"credit score", r"credit-score", r"\bfico\b", r"vantagescore"], "Credit and Debt",
      wiki="Credit_score"),
    C("credit_card", "Credit cards, interest and fees", [r"credit card", r"credit-card", r"\bapr\b", r"balance transfer",
      r"minimum payment", r"cash advance"], "Credit and Debt", num=True, wiki="Credit_card"),
    C("debt_collection", "Debt collection", [r"debt collect", r"collection agenc", r"debt-collection", r"debt not owed",
      r"collections?\b"], "Credit and Debt", wiki="Debt_collection"),
    C("student_loan", "Student loans", [r"student loan", r"student-loan", r"federal student aid", r"\bfafsa\b",
      r"\bosap\b"], "Credit and Debt", num=True, wiki="Student_loan"),
    C("mortgage", "Mortgages", [r"mortgage", r"refinanc", r"\bheloc\b", r"home equity", r"amortization"],
      "Credit and Debt", num=True, wiki="Mortgage_loan"),
    C("auto_loan", "Car loans and vehicle financing", [r"auto loan", r"car loan", r"vehicle loan", r"car financ",
      r"auto-loan", r"vehicle lease", r"car lease"], "Credit and Debt", num=True, wiki="Car_finance"),
    C("personal_loan", "Personal loans and payday loans", [r"personal loan", r"payday", r"title loan", r"installment loan"],
      "Credit and Debt", num=True, wiki="Payday_loan"),
    C("bnpl", "Buy now, pay later", [r"buy now,? pay later", r"\bbnpl\b", r"\bklarna\b", r"\bafterpay\b", r"\baffirm\b"],
      "Credit and Debt", wiki="Buy_now,_pay_later"),
    C("debt_payoff", "Paying off debt", [r"pay ?off debt", r"debt payoff", r"debt snowball", r"debt avalanche",
      r"debt consolidat", r"debt relief", r"debt settlement"], "Credit and Debt", num=True, wiki="Debt_consolidation"),
    C("bankruptcy", "Bankruptcy", [r"bankrupt", r"consumer proposal"], "Credit and Debt", wiki="Bankruptcy"),
    # Banking and Money
    C("bank_account", "Checking and savings accounts", [r"checking account", r"savings account", r"bank account",
      r"checking or savings", r"overdraft", r"\bnsf\b", r"account (?:closed|frozen)"], "Banking and Money",
      wiki="Transaction_account"),
    C("money_transfer", "Money transfers and payment apps", [r"money transfer", r"wire transfer", r"\bzelle\b",
      r"\bvenmo\b", r"\bpaypal\b", r"cash app", r"interac", r"e-transfer", r"remittance", r"money service"],
      "Banking and Money", wiki="Electronic_funds_transfer"),
    C("debit_prepaid", "Debit and prepaid cards", [r"debit card", r"prepaid card", r"prepaid visa", r"gift card"],
      "Banking and Money", wiki="Debit_card"),
    C("bank_fees", "Bank fees", [r"bank fee", r"maintenance fee", r"atm fee", r"foreign transaction fee"],
      "Banking and Money", num=True, wiki="Bank_charge"),
    C("deposit_insurance", "Deposit insurance and bank safety", [r"\bfdic\b", r"\bcdic\b", r"deposit insurance",
      r"bank fail"], "Banking and Money", wiki="Deposit_insurance"),
    C("currency_exchange", "Currency exchange for travelers", [r"currency exchange", r"exchange rate", r"forex fee",
      r"foreign currency"], "Banking and Money", wiki="Foreign_exchange_market"),
    C("check_cashing", "Checks and check deposits", [r"\bcheque\b", r"\bcheck deposit", r"mobile deposit",
      r"cashier'?s check", r"bounced check"], "Banking and Money", wiki="Cheque"),
    # Saving and Wealth Building
    C("emergency_fund", "Emergency funds", [r"emergency fund", r"rainy day"], "Saving and Wealth Building", num=True,
      wiki="Emergency_fund"),
    C("hysa", "High-yield savings accounts and interest on savings", [r"high[- ]yield", r"\bhysa\b", r"savings rate",
      r"interest on savings", r"money market"], "Saving and Wealth Building", num=True, wiki="High-yield_savings_account"),
    C("cd_gic", "CDs and GICs", [r"certificate of deposit", r"\bcds?\b", r"\bgics?\b"], "Saving and Wealth Building",
      num=True, wiki="Certificate_of_deposit"),
    C("retirement_401k", "401(k) plans and employer matching", [r"401\(?k\)?", r"\b403\(?b\)?", r"employer match",
      r"\btsp\b"], "Saving and Wealth Building", "US", True, "401(k)"),
    C("ira_roth", "IRAs and Roth IRAs", [r"\bira\b", r"roth", r"traditional ira", r"backdoor roth", r"roth-ira"],
      "Saving and Wealth Building", "US", True, "Individual_retirement_account"),
    C("rrsp", "RRSPs", [r"\brrsp\b", r"\brrif\b"], "Saving and Wealth Building", "CA", True,
      "Registered_retirement_savings_plan"),
    C("tfsa", "TFSAs", [r"\btfsa\b", r"tax[- ]free savings account"], "Saving and Wealth Building", "CA", True,
      "Tax-free_savings_account_(Canada)"),
    C("fhsa", "First Home Savings Accounts (FHSA)", [r"\bfhsa\b", r"first home savings"], "Saving and Wealth Building",
      "CA", True, "First_Home_Savings_Account"),
    C("hsa", "Health savings accounts (HSA)", [r"\bhsa\b", r"health savings account"], "Saving and Wealth Building", "US",
      True, "Health_savings_account"),
    C("education_saving", "Saving for education (529, RESP)", [r"\b529\b", r"\bresp\b"], "Saving and Wealth Building",
      "both", True, "529_plan"),
    C("retirement_planning", "Retirement planning", [r"retire", r"pension", r"social security", r"\bcpp\b", r"\boas\b",
      r"annuit"], "Saving and Wealth Building", num=True, wiki="Retirement_planning"),
    C("fire", "Financial independence and early retirement", [r"\bfire\b movement", r"financial independence",
      r"early retirement", r"4% rule", r"safe withdrawal"], "Saving and Wealth Building", num=True,
      wiki="FIRE_movement"),
    C("compound", "Compound interest", [r"compound interest", r"compounding"], "Saving and Wealth Building", num=True,
      wiki="Compound_interest"),
    C("net_worth", "Net worth and wealth building", [r"net worth", r"wealth build", r"millionaire"],
      "Saving and Wealth Building", num=True, wiki="Net_worth"),
    # Investing
    C("index_funds", "Index funds and ETFs", [r"index fund", r"\betfs?\b", r"\bvoo\b", r"\bvti\b", r"s&p 500",
      r"total market"], "Investing", num=True, wiki="Index_fund"),
    C("stocks", "Investing in stocks", [r"\bstocks?\b", r"\bshares?\b", r"brokerage", r"\bipo\b", r"dividend",
      r"stock market"], "Investing", num=True, wiki="Stock"),
    C("bonds", "Bonds, Treasuries and TIPS", [r"\bbonds?\b", r"treasury bill", r"t-bill", r"\btips\b", r"i bond"],
      "Investing", num=True, wiki="Bond_(finance)"),
    C("options", "Options trading", [r"\boptions? trad", r"call option", r"put option", r"covered call"], "Investing",
      wiki="Option_(finance)"),
    C("crypto", "Cryptocurrency", [r"crypto", r"bitcoin", r"ethereum", r"stablecoin", r"virtual currency"], "Investing",
      wiki="Cryptocurrency"),
    C("gold", "Gold and precious metals", [r"\bgold\b", r"\bsilver\b", r"precious metal"], "Investing",
      wiki="Gold_as_an_investment"),
    C("real_estate_inv", "Real estate investing", [r"rental property", r"real estate invest", r"\breit"], "Investing",
      num=True, wiki="Real_estate_investing"),
    C("capital_gains", "Capital gains and investment taxes", [r"capital gain", r"wash sale", r"cost basis",
      r"tax[- ]loss harvest"], "Investing", num=True, wiki="Capital_gains_tax"),
    C("fees_expense", "Investment fees and expense ratios", [r"expense ratio", r"advisor fee", r"management fee",
      r"\bmer\b"], "Investing", num=True, wiki="Expense_ratio"),
    C("robo", "Robo-advisors and investing apps", [r"robo[- ]advis", r"\brobinhood\b", r"wealthsimple",
      r"investing app"], "Investing", wiki="Robo-advisor"),
    # Personal Finance
    C("budgeting", "Budgeting", [r"budget", r"50/30/20", r"envelope method", r"zero-based"], "Personal Finance",
      num=True, wiki="Budget"),
    C("income_tax", "Personal income taxes and refunds", [r"income tax", r"tax return", r"tax refund", r"\bw-?2\b",
      r"\b1099\b", r"\bt4\b", r"tax bracket", r"deduction", r"\birs\b", r"\bcra\b", r"withholding", r"\btaxes\b"],
      "Personal Finance", num=True, wiki="Income_tax_in_the_United_States"),
    C("insurance", "Insurance for individuals", [r"insurance", r"premium", r"deductible"], "Personal Finance",
      wiki="Insurance"),
    C("rent_vs_buy", "Renting vs buying a home", [r"rent vs\.? buy", r"renting or buying", r"buy a house",
      r"first[- ]time (?:home ?)?buyer", r"down payment"], "Personal Finance", num=True, wiki="Home_ownership"),
    C("paycheck", "Paychecks, salary and side income", [r"paycheck", r"salary", r"side hustle", r"raise",
      r"\bwages?\b", r"self-employ", r"freelanc"], "Personal Finance", num=True, wiki="Salary"),
    C("estate", "Wills, inheritance and estates", [r"inherit", r"\bestate\b", r"\bwill\b.*\b(?:testament|probate)",
      r"probate", r"beneficiar", r"\btrust fund"], "Personal Finance", wiki="Inheritance"),
    C("cost_of_living", "Cost of living and household spending", [r"cost of living", r"grocer", r"household spending",
      r"subscription"], "Personal Finance", num=True, wiki="Cost_of_living"),
    C("inflation_personal", "Inflation and your money", [r"inflation"], "Personal Finance", num=True,
      wiki="Inflation"),
    # Financial Psychology
    C("spending_psych", "Spending habits and money psychology", [r"impulse (?:buy|spend)", r"lifestyle creep",
      r"emotional spending", r"money anxiety", r"financial stress", r"\bfomo\b", r"frugal", r"spending habit",
      r"behavioral finance", r"money mindset"], "Financial Psychology", wiki="Behavioral_economics"),
    C("money_relationships", "Money and relationships", [r"\bspouse\b", r"married", r"joint account", r"partner'?s debt",
      r"\bdivorce\b", r"prenup", r"lend(?:ing)? money to (?:family|friend)"], "Financial Psychology",
      wiki="Personal_finance"),
    # Financial Mistakes and Scams
    C("identity_theft", "Identity theft", [r"identity theft", r"stolen identity", r"information belongs to someone else",
      r"fraud alert", r"credit freeze", r"security freeze"], "Financial Mistakes and Scams", wiki="Identity_theft"),
    C("scams", "Scams and fraud", [r"\bscam", r"\bfraud", r"phishing", r"impersonat", r"pig butchering", r"romance scam",
      r"fake (?:check|cheque|job)", r"unauthorized (?:transaction|charge)", r"ponzi", r"pyramid scheme"],
      "Financial Mistakes and Scams", wiki="Confidence_trick"),
    C("money_mistakes", "Common money mistakes", [r"\bmistake", r"regret", r"wrong account", r"late fee",
      r"missed payment"], "Financial Mistakes and Scams", wiki="Personal_finance"),
]

FINANCE_TERMS = re.compile(
    r"\b(money|financ\w*|bank|banking|loans?|debts?|credit|invest\w*|savings?|saving|retire\w*|rebate|"
    r"retirement|tax|taxes|budget|mortgage|stock|fund|interest|apr|apy|dividend|broker|brokerage|account|payment|"
    r"cash|income|salary|paycheck|insurance|fee|fees|scam|fraud|wealth|net worth|crypto|bitcoin|pension|annuity|"
    r"portfolio|asset|equity|bond|refund|deposit|withdraw|currency|dollar|price|spend|spending|afford)\b", re.I)

# Off-topic markers: if present, the candidate is rejected even if it mentions money.
OFF_TOPIC = [
    (r"\b(election|electoral|senate|congress|parliament|prime minister|president|presidential|democrat|republican|"
     r"liberal party|conservative party|campaign|politic|ballot|governor|mayor|white house|supreme court)", "politics"),
    (r"\b(war|military|invasion|sanction|nato|geopolit|terror|ceasefire|missile|army)\b", "geopolitics / conflict"),
    (r"\b(gdp|recession|tariffs?|trade war|central bank|federal reserve|monetary policy|fiscal policy|"
     r"national debt|sovereign debt|bond market selloff|unemployment rate|jobs report)\b", "general economics"),
    (r"\b(celebrity|actor|actress|singer|rapper|album|movie|film|tv series|season \d|episode|nfl|nba|mlb|nhl|"
     r"world cup|olympic|super bowl)\b", "entertainment / sports"),
    # ("died"/"death" are deliberately NOT here: inheritance and estate topics are finance)
    (r"\b(shooting|murder|arrest|lawsuit against|indicted|scandal|obituary)\b", "general news"),
]
OFF_TOPIC_RE = [(re.compile(p, re.I), why) for p, why in OFF_TOPIC]
_CONCEPT_RE = [(c, [re.compile(p, re.I) for p in c.patterns]) for c in CONCEPTS]

US_MARKERS = re.compile(r"\b(united-states|usa|u\.s\.|\birs\b|401\(?k|roth|ira\b|fdic|social security|w-?2|1099|"
                        r"fafsa|hsa\b|\b529\b|zelle|venmo|cfpb)", re.I)
CA_MARKERS = re.compile(r"\b(canada|canadian|\bcra\b|rrsp|tfsa|fhsa|resp\b|rrif|cpp\b|oas\b|cdic|interac|"
                        r"e-transfer|gic|ontario|quebec|british columbia|alberta)", re.I)
OTHER_REGION = re.compile(r"\b(united-kingdom|\buk\b|india|australia|germany|france|netherlands|ireland|spain|"
                          r"italy|singapore|new-zealand|south-africa|pakistan|nigeria|philippines|eu\b)", re.I)


def match_concepts(text: str) -> list[Concept]:
    return [c for c, pats in _CONCEPT_RE if any(p.search(text) for p in pats)]


def gate(text: str, finance_source: bool = False) -> tuple[bool, str]:
    """Finance-only gate. Returns (accepted, reason).

    finance_source=True for sources whose every item is about money by definition (a personal-finance Q&A
    site, the CFPB complaint database): only the off-topic markers apply. General sources (e.g. Wikipedia's
    most-read list) must also contain finance vocabulary."""
    for rx, why in OFF_TOPIC_RE:
        m = rx.search(text)
        if m:
            return False, f"off-topic: {why} ('{m.group(0)}')"
    if finance_source or match_concepts(text) or FINANCE_TERMS.search(text):
        return True, "finance"
    return False, "not finance-related"


def market_of(text: str, concepts: list[Concept]) -> str:
    """A concept's market is a property of the subject (credit cards matter in both countries), so it wins
    over incidental mentions. Text markers decide only for candidates without a concept."""
    if concepts:
        markets = {c.market for c in concepts}
        return markets.pop() if len(markets) == 1 else "both"
    us, ca = bool(US_MARKERS.search(text)), bool(CA_MARKERS.search(text))
    for c in concepts:
        us |= c.market == "US"
        ca |= c.market == "CA"
    if us and not ca:
        return "US"
    if ca and not us:
        return "CA"
    if OTHER_REGION.search(text) and not (us or ca):
        return "other"
    return "both"


def category_of(concepts: list[Concept], text: str = "") -> str:
    if not concepts:
        return "Personal Finance"
    counts: dict[str, int] = {}
    for c in concepts:
        counts[c.category] = counts.get(c.category, 0) + 1
    return max(counts, key=lambda k: (counts[k], -CATEGORIES.index(k)))
