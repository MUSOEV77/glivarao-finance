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
DIGITS = re.compile(r"(?<![\w(])\$?\d[\d,]*(?:\.\d+)?(?:\s?%)?(?![\w(])")
# account names, years and numbered labels ("myth number 2", "step 3", "option 2") are not claims
NOT_A_CLAIM = re.compile(r"401\(k\)|\b(?:19|20)\d\d\b|\b(?:myth|step|option|tip|mistake|chapter|part|number)"
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


def _index(brief) -> list[tuple[float, str, str, str]]:
    """(value, status, source label, url) for every number the brief can vouch for."""
    idx = []
    for f in brief.facts:
        status = {"DATA": "source", "CALCULATION": "calculation"}.get(f.kind, "reference")
        for v in numbers_in(f.text):
            idx.append((v, status, f.source or f.kind.title(), f.url))
    for p in brief.problems:
        if p.get("year_ago"):
            growth = (p["complaints_90d"] / p["year_ago"] - 1) * 100
            for v in (p["complaints_90d"], p["year_ago"], round(growth)):
                idx.append((float(v), "source", "CFPB Consumer Complaint Database", p.get("link", "")))
    for c in (brief.calcs or {}).values():
        for d in (getattr(c, "inputs", {}), getattr(c, "results", {})):
            for v in d.values():
                if isinstance(v, (int, float)):
                    for x in {float(v), float(v) * 100, float(v) * 12}:
                        idx.append((x, "calculation", "GLIVARAO calculation (hypothetical inputs)", ""))
    return idx


def _match(v: float, idx) -> tuple | None:
    for s, status, label, url in idx:
        if abs(v - s) <= max(0.51, 0.015 * abs(s)):
            return status, label, url
    return None


def check_claims(script: Script, brief, creator_text: str = "") -> list[Claim]:
    idx = _index(brief)
    creator_nums = set(numbers_in(creator_text or ""))
    claims = []
    for i, scene in enumerate(script.scenes):
        for sent in _sentences(scene.narration):
            ref = next(((lab, url) for pat, lab, url in REFERENCES if re.search(pat, sent, re.I)), None)
            vals = numbers_in(sent)
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
            elif any(v in creator_nums for v in vals):
                claims.append(Claim(i, sent, vals, "creator", "Your own input: confirm it's accurate"))
            else:
                claims.append(Claim(i, sent, vals, "UNSOURCED"))
        if scene.chart.kind != "none" and scene.chart.kind != "compound_growth" and scene.chart.values:
            src = scene.chart.source
            url = next((f.url for f in brief.facts if f.url and f.source and f.source in src), "")
            status = "calculation" if "calculat" in src.lower() else ("source" if url else "reference")
            claims.append(Claim(i, f"Chart: {scene.chart.title}", list(scene.chart.values), status, src, url))
    return claims


def report(claims: list[Claim], limit: int = 40) -> str:
    n_bad = sum(c.status == "UNSOURCED" for c in claims)
    n_creator = sum(c.status == "creator" for c in claims)
    head = (f"FACT CHECK: {len(claims)} numbers/claims. "
            + (f"⚠️ {n_bad} have NO SOURCE. " if n_bad else "All have a source or calculation. ")
            + (f"🗣 {n_creator} come from your input; please confirm." if n_creator else ""))
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


__all__ = ["check_claims", "report", "source_urls", "add_sources_to_description", "Claim", "numbers_in"]
