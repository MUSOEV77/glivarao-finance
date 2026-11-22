"""Fact check: every sentence that states a number is listed with where that number comes from.

Status per claim:
  source      - research data with a public URL (e.g. the CFPB complaint database, a forum question)
  calculation - computed by GLIVARAO's exact calculators from stated, hypothetical inputs
  reference   - a reviewed rule or limit from the library, with the official URL
  creator     - from your own input; please confirm it's accurate
  UNSOURCED   - no source found: fix it or confirm it before approving

The list goes into the Telegram review message; all URLs go into the YouTube description.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..art.editorial_style import SPELLED_RE, words_to_number
from ..models import Script

# Reviewed figures that appear in the library text, with their official sources.
REFERENCES = [
    (r"\bsixty days\b|\b60 days\b", "US Fair Credit Billing Act dispute window (FTC)",
     "https://consumer.ftc.gov/articles/using-credit-cards-and-disputing-charges"),
    (r"two hundred fifty thousand|\$?250,000", "FDIC deposit insurance limit",
     "https://www.fdic.gov/resources/deposit-insurance"),
    (r"one hundred thousand dollars|\$?100,000 per", "CDIC deposit insurance limit",
     "https://www.cdic.ca/your-coverage/"),
    (r"annualcreditreport", "Free US credit reports (official site)", "https://www.annualcreditreport.com"),
    (r"report fraud dot f t c", "FTC fraud reporting", "https://reportfraud.ftc.gov"),
    (r"canadian anti-fraud centre", "Canadian Anti-Fraud Centre", "https://antifraudcentre-centreantifraude.ca"),
]
# Official pages that explain (or reproduce) the method behind each family's calculations.
METHOD = {
    "card": ("Method: CFPB, minimum payments on a credit card",
             "https://www.consumerfinance.gov/ask-cfpb/what-is-a-minimum-payment-on-a-credit-card-en-1953/"),
    "loan": ("Method: CFPB, how amortization works",
             "https://www.consumerfinance.gov/ask-cfpb/what-is-amortization-and-how-could-it-affect-my-auto-loan-en-873/"),
    "grow": ("Method: Investor.gov compound interest calculator (SEC)",
             "https://www.investor.gov/financial-tools-calculators/calculators/compound-interest-calculator"),
    "invest": ("Method: Investor.gov compound interest calculator (SEC)",
               "https://www.investor.gov/financial-tools-calculators/calculators/compound-interest-calculator"),
}
FEES_METHOD = ("Method: Investor.gov, expense ratios (SEC)",
               "https://www.investor.gov/introduction-investing/investing-basics/glossary/expense-ratio")
DIGITS = re.compile(r"(?<![\w(])\$?\d[\d,]*(?:\.\d+)?(?:\s?%)?(?![\w(])")
# account names, years and numbered labels ("myth number 2", "step 3", "option 2") are not claims
NOT_A_CLAIM = re.compile(r"\b[A-Z]\.\d+\b|\bQ[1-4]\b|401\(k\)|403\(b\)|\bW-?[249]\b|\b1099(?:-[A-Z]+)?\b|\b1040\b|\b529 plan|\b(?:19|20)\d\d\b|\b(?:myth|step|option|tip|mistake|chapter|part|number)"
                         r"\s+(?:number\s+)?\d+\b", re.I)


@dataclass
class Claim:
    scene: int
    text: str
    values: list[float]
    status: str
    source: str = ""
    url: str = ""

    def line(self, i: int) -> str:
        icon = {"source": "🔗", "calculation": "🧮", "reference": "📘", "creator": "🗣", "UNSOURCED": "⚠️"}[self.status]
        where = f"{self.source} {self.url}".strip()
        return f"{i}. {icon} \"{self.text}\" → {where or 'NO SOURCE: check before approving'}"


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.replace("*", "")) if s.strip()]


def numbers_in(text: str) -> list[float]:
    t = NOT_A_CLAIM.sub(" ", text)
    vals = []
    for m in DIGITS.finditer(t):
        raw = m.group(0).replace("$", "").replace("%", "").replace(",", "").strip()
        try:
            vals.append(float(raw))
        except ValueError:
            pass
    for m in SPELLED_RE.finditer(t):
        v = words_to_number(m.group(1).strip())
        if v:
            vals.append(v)
    return vals


def _method(brief, key: str = "") -> tuple[str, str]:
    if key == "fees":
        return FEES_METHOD
    return METHOD.get(brief.family, ("Method: GLIVARAO calculation (inputs in the description)", ""))


def _index(brief) -> list[tuple[float, str, str, str]]:
    """(value, status, source label, url) for every number the brief can vouch for."""
    idx = []
    for f in brief.facts:
        status = {"DATA": "source", "CALCULATION": "calculation"}.get(f.kind, "reference")
        label, url = (f.source or f.kind.title(), f.url)
        if status == "calculation" and not url:
            label, url = _method(brief)
        for v in numbers_in(f.text):
            idx.append((v, status, label, url))
    for p in brief.problems:
        if p.get("year_ago"):
            growth = (p["complaints_90d"] / p["year_ago"] - 1) * 100
            for v in (p["complaints_90d"], p["year_ago"], round(growth)):
                idx.append((float(v), "source", "CFPB Consumer Complaint Database", p.get("link", "")))
    for name, c in (brief.calcs or {}).items():
        label, url = _method(brief, name)
        for d in (getattr(c, "inputs", {}), getattr(c, "results", {})):
            for v in d.values():
                vs = v if isinstance(v, (list, tuple)) else [v]       # e.g. the yearly balance path of a payoff
                for w in vs:
                    if isinstance(w, (int, float)) and not isinstance(w, bool):
                        for x in {float(w), float(w) * 100, float(w) * 12}:
                            idx.append((x, "calculation", label, url))
    return idx


def _rounding_unit(s: float) -> float:
    """The rounding GLIVARAO uses when it speaks a number (calculators.spoken_money)."""
    a = abs(s)
    return 100_000 if a >= 1_000_000 else 1_000 if a >= 10_000 else 100 if a >= 1_000 else 1


def _match(v: float, idx) -> tuple | None:
    for s, status, label, url in idx:
        if abs(v - s) <= max(0.51, 0.015 * abs(s), _rounding_unit(s) / 2 + 1e-9):
            return status, label, url
    return None


EXAMPLE_RE = re.compile(r"\b(?:example|illustrat\w*|hypothetical|calculat\w*|for instance|imagine|say you|let'?s say|"
                        r"say,|suppose|made[- ]up|picture this|if you (?:owe|have|borrow|carry|pay|put|save|invest)\w*)"
                        r"\b", re.I)
CONSTS = (12.0, 52.0, 100.0, 365.0)   # months, weeks, percent, days
HYPO_MAX = 100_000.0     # a hypothetical example amount is personal-scale; bigger numbers must be sourced


def _rates(brief, idx) -> list[tuple[float, str, str]]:
    """Sourced percentages (APR, yields) that a worked example may use as its rate: (rate, label, url)."""
    out = []
    for f in brief.facts:
        if f.url and f.kind == "DATA":
            for m in re.finditer(r"(\d+(?:\.\d+)?)\s?(?:%|percent)", f.text):
                out.append((float(m.group(1)) / 100, f.source or "Source", f.url))
    return out


def _example_results(principal: float, apr: float, payments: list[float], years: list[int]) -> list[float]:
    """Results GLIVARAO's calculators give for THIS example's stated inputs only: simple interest, paying the
    minimum, paying each stated monthly amount, and a loan over each stated number of years."""
    from ..content import calculators as calc

    vals = [principal * apr, principal * apr / 12]
    c = calc.minimum_payment_payoff(principal, apr)
    vals += [c.results["total_interest"], c.results["total_paid"], c.results["months"], c.results["years"]]
    for pay in payments:
        if pay > principal * apr / 12:
            f = calc.fixed_payment_payoff(principal, apr, pay)
            vals += [f.results.get(k, 0) for k in ("total_interest", "total_paid", "months", "years")]
    for yrs in years:
        lo = calc.amortized_loan(principal, apr, yrs)
        vals += [lo.results.get(k, 0) for k in ("monthly_payment", "total_interest", "total_paid")]
    return [float(v) for v in vals if isinstance(v, (int, float)) and v]


def worked_example(text: str, values: list[float], brief, idx) -> tuple[str, str] | None:
    """(label, url) if `text` is a clearly labeled worked example whose rate is a sourced fact and whose results
    are reproduced by GLIVARAO's calculators from the stated inputs (balance, monthly payment, years); else None.
    Real-world statistics never pass here (they need their own source)."""
    if not EXAMPLE_RE.search(text):
        return None
    stated = numbers_in(text)
    nums = [v for v in (values or stated) if v]
    pays = [float(m.group(1).replace(",", "")) for m in
            re.finditer(r"\$([\d,]+(?:\.\d+)?)\s*(?:a|per|each|every)\s*month", text, re.I)]
    yrs = [int(m.group(1)) for m in re.finditer(r"\b(\d{1,2})[- ]years?\b", text, re.I)]
    low = text.lower()
    for rate, label, url in _rates(brief, idx):
        rate_pct = rate * 100
        if not (any(abs(v - rate_pct) <= 0.01 for v in stated) or "example" in low or "illustrat" in low):
            continue
        amounts = [v for v in stated if v >= 100 and abs(v - rate_pct) > 0.01 and v not in pays]
        for principal in amounts:
            inputs = {principal, rate_pct, *pays, *map(float, yrs)}
            results = _example_results(principal, rate, pays, yrs)
            outputs = [v for v in nums if not any(abs(v - x) <= 0.01 for x in inputs)]
            if outputs and all(any(abs(v - r) <= max(0.51, 0.015 * abs(r), _rounding_unit(r) / 2 + 1e-9)
                                   for r in results) for v in outputs):
                return (f"Worked example (hypothetical ${principal:,.0f}; rate {rate_pct:g}% from {label}; math "
                        "checked by GLIVARAO's calculators)", url)
    return None


def _close(a: float, b: float) -> bool:
    """Arithmetic results must match closely (0.3%), not just within a rounding band."""
    return abs(a - b) <= max(0.51, 0.003 * abs(b))


class _Pool:
    """What arithmetic may start from. `scene`: numbers this scene states (sourced or labeled example), which may be
    combined in pairs; `sourced`: fact-sheet numbers the scene doesn't state, which may only be scaled by a time
    constant (12, 52, 365, 100) or by a percentage that is itself on the fact sheet (e.g. 400% x $15,960)."""

    def __init__(self, sourced: list[tuple[float, str]], pcts: list[float] | None = None):
        self.sourced, self.scene, self.pcts = list(sourced), [], list(pcts or [])

    def add(self, v: float, url: str = "") -> None:
        self.scene.append((v, url))

    def derive(self, v: float) -> tuple[bool, str]:
        for a, ua in self.scene + self.sourced:
            if _close(v, a):
                return True, ua
        consts = [(c, "") for c in CONSTS]
        for n, (a, ua) in enumerate(self.scene):
            for m, (b, ub) in enumerate(self.scene + consts):
                if m == n:
                    continue          # never a number with itself (x + x, x - x)
                for r in (a * b, a + b, a - b, b - a) + ((a / b,) if b else ()) + ((b / a,) if a else ()):
                    if r > 0 and _close(v, r):
                        return True, ua or ub
        for a, ua in self.sourced:
            for c in (12.0, 100.0):         # unstated fact-sheet numbers: per month / per year, percent only
                if _close(v, a * c) or _close(v, a / c):
                    return True, ua
            for p_ in self.pcts:
                if _close(v, a * p_ / 100):
                    return True, ua
        return False, ""


def _percents(text: str) -> set[float]:
    return {float(m.group(1).replace(",", "")) for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s?(?:%|percent)", text, re.I)}


def check_claims(script: Script, brief, creator_text: str = "") -> list[Claim]:
    idx = _index(brief)
    # arithmetic may only start from fact-sheet numbers (official sources), not from every calculator variant
    sourced = [(v, f.url) for f in brief.facts if f.kind == "DATA" and f.url for v in numbers_in(f.text)]
    fact_pcts = sorted({p for f in brief.facts if f.kind == "DATA" and f.url for p in _percents(f.text)})
    creator_nums = set(numbers_in(creator_text or ""))
    claims = []
    for i, scene in enumerate(script.scenes):
        pool = _Pool(sourced, fact_pcts)   # per scene: what this scene states + scaled fact-sheet numbers
        example_ctx = False
        for sent in _sentences(scene.narration):
            ref = next(((lab, url) for pat, lab, url in REFERENCES if re.search(pat, sent, re.I)), None)
            vals = numbers_in(sent)
            labeled = bool(EXAMPLE_RE.search(sent))
            example_ctx = example_ctx or labeled
            if not vals and not ref:
                continue
            if scene.beat == "creator":
                claims.append(Claim(i, sent, vals, "creator", "Your own input: confirm it's accurate"))
                continue
            if ref:
                claims.append(Claim(i, sent, vals, "reference", ref[0], ref[1]))
                continue
            hits = [_match(v, idx) for v in vals]
            if all(hits):
                status, label, url = next((h for h in hits if h[0] == "source"), hits[0])
                claims.append(Claim(i, sent, vals, status, label, url))
                for v in vals:
                    pool.add(v, url)
                continue
            ex = worked_example(sent, vals, brief, idx)
            if ex:
                claims.append(Claim(i, sent, vals, "calculation", ex[0], ex[1]))
                for v in vals:
                    pool.add(v, ex[1])
                continue
            # simple arithmetic on sourced numbers (anywhere) and on labeled example inputs (in an example)
            pct = _percents(sent)
            ok, urls, hypo = True, [], []
            for v in vals:
                good, u = (False, "") if v in pct else pool.derive(v)   # a percentage must be sourced directly
                if good:
                    urls.append(u)
                elif labeled and not hypo and v <= HYPO_MAX and v not in pct:
                    hypo.append(v)          # ONE personal-scale hypothetical input per labeled example sentence
                    pool.add(v, "")         # ... and results in the same sentence may be computed from it
                else:
                    ok = False
                    break
            if ok and (example_ctx or not hypo):
                for v in vals:
                    pool.add(v, next((u for u in urls if u), ""))
                url = next((u for u in urls if u), "")
                what = (f"hypothetical input {', '.join(f'{h:,.0f}' for h in hypo)}; " if hypo else "")
                claims.append(Claim(i, sent, vals, "calculation",
                                    f"Worked example ({what}arithmetic checked by GLIVARAO)", url))
            elif any(v in creator_nums for v in vals):
                claims.append(Claim(i, sent, vals, "creator", "Your own input: confirm it's accurate"))
            else:
                claims.append(Claim(i, sent, vals, "UNSOURCED"))
        if scene.chart.kind != "none" and scene.chart.kind != "compound_growth" and scene.chart.values:
            claims.append(_chart_claim(i, scene, brief, idx, pool))
        if scene.chart.kind == "compound_growth":
            src, url = _method(brief) if brief.family in ("grow", "invest") else METHOD["grow"]
            claims.append(Claim(i, f"Chart: {scene.chart.title}", [], "calculation", src, url))
    return claims


def _chart_claim(i: int, scene, brief, idx, pool: _Pool) -> Claim:
    """A chart passes only if every value is a fact-sheet number, one arithmetic step from fact-sheet numbers or the
    scene's example numbers, or a worked example our calculators reproduce."""
    c = scene.chart
    vals = [float(v) for v in c.values if v]
    title = f"Chart: {c.title}"
    hits = [_match(v, idx) for v in vals]
    if vals and all(hits):
        h = next((x for x in hits if x[0] == "source"), hits[0])
        if h[2]:
            return Claim(i, title, vals, h[0], h[1], h[2])
    ex = worked_example(" ".join([c.title, c.source, " ".join(c.labels), scene.narration]), vals, brief, idx)
    if ex:
        return Claim(i, title, vals, "calculation", ex[0], ex[1])
    derived = [pool.derive(v) for v in vals]
    if vals and all(d[0] for d in derived):
        url = next((d[1] for d in derived if d[1]), "")
        return Claim(i, title, vals, "calculation", "Worked example (from fact-sheet numbers; arithmetic checked by "
                     "GLIVARAO)", url)
    return Claim(i, title, vals, "UNSOURCED")


def sanitize_charts(script: Script, brief) -> tuple[Script, list[str]]:
    """Charts are built only from fact-sheet data: a chart whose values can't be verified is removed (the scene
    keeps its narration) instead of failing the whole video. Returns (script, removed chart titles)."""
    from ..models import ChartSpec

    bad = {c.scene for c in check_claims(script, brief) if c.text.startswith("Chart:") and c.status == "UNSOURCED"}
    if not bad:
        return script, []
    scenes = list(script.scenes)
    removed = [scenes[k].chart.title for k in sorted(bad)]
    for k in bad:
        scenes[k] = scenes[k].model_copy(update={"chart": ChartSpec()})
    return script.model_copy(update={"scenes": scenes}), removed


def needs_source(claims: list[Claim]) -> list[Claim]:
    """Claims without a source URL (your own personal experience is listed separately, not counted here). A worked
    example whose arithmetic GLIVARAO checked needs no URL of its own."""
    return [c for c in claims if c.status != "creator" and not c.url
            and not (c.status == "calculation" and c.source.startswith("Worked example"))]


def report(claims: list[Claim], limit: int = 40) -> str:
    n_bad = len(needs_source(claims))
    n_creator = sum(c.status == "creator" for c in claims)
    head = (f"FACT CHECK: {len(claims)} numbers/claims. "
            + (f"⚠️ {n_bad} have NO SOURCE URL. " if n_bad else "✅ Every claim has a source URL. ")
            + (f"🗣 {n_creator} come from your own experience; please confirm." if n_creator else ""))
    lines = [c.line(i + 1) for i, c in enumerate(claims[:limit])]
    if len(claims) > limit:
        lines.append(f"... and {len(claims) - limit} more in fact_check.md")
    return head + "\n" + "\n".join(lines)


def source_urls(claims: list[Claim]) -> list[tuple[str, str]]:
    seen, out = set(), []
    for c in claims:
        if c.url and c.url not in seen:
            seen.add(c.url)
            out.append((c.source, c.url))
    return out


def add_sources_to_description(description: str, claims: list[Claim]) -> str:
    """Make sure every source URL used in the script is listed in the description."""
    missing = [(s, u) for s, u in source_urls(claims) if u not in description]
    if not missing:
        return description
    block = "Sources:\n" + "\n".join(f"- {s}: {u}" for s, u in missing)
    if "Sources:" in description:
        return description.replace("Sources:", block, 1)
    return description.rstrip() + "\n\n" + block + "\n"


__all__ = ["sanitize_charts", "check_claims", "report", "needs_source", "source_urls", "add_sources_to_description", "Claim", "numbers_in"]
