"""Titles, descriptions (with chapters and sources), tags and thumbnail text, generated from the brief.

Titles create curiosity but must stay accurate. Every number used comes from the brief's calculations or data.
"""
from __future__ import annotations

from ..models import Script
from .brief import Brief, topic_phrase

DISCLAIMER = "This video is for education only and isn't financial advice."


def _calc_numbers(b: Brief) -> dict:
    c, out = b.calcs, {}
    if "minimum" in c:
        out["card_years"] = round(c["minimum"].results["years"])
        out["card_interest"] = c["minimum"].results["total_interest"]
    if "loan" in c:
        out["loan_first_interest_share"] = c["loan"].results["first_payment_interest"] / c["loan"].results["monthly_payment"]
    if "growth" in c:
        out["growth_final"] = c["growth"].results["final"]
    if "fees" in c:
        out["fee_gap"] = c["fees"].results["difference"]
    return out


def titles_for(b: Brief, variant: str = "") -> tuple[str, str]:
    """(title, thumbnail_text)"""
    n = _calc_numbers(b)
    t = b.topic
    if b.family == "card":
        if variant == "the mistake":
            return "The Credit Card Mistake That Keeps You in Debt", "Not The Minimum."
        yrs = b.calcs["minimum"].results["years"]
        lead = "Nearly " if yrs < n["card_years"] else ""
        return (f"Why Paying the Minimum Could Take {lead}{n['card_years']} Years (Credit Card Math)",
                f"{lead}{n['card_years']} Years.")
    if b.family == "loan":
        noun = {"mortgage": "Mortgage", "student_loan": "Student Loan", "auto_loan": "Car Loan",
                "rent_vs_buy": "Mortgage"}.get(b.topic_key, "Loan")
        if variant == "the mistake":
            return f"The {noun} Mistake That Costs the Most", "Check The Total."
        return f"Where Your {noun} Payment Really Goes", "Mostly Interest."
    if b.family == "grow":
        if variant == "the mistake":
            return "The Saving Mistake That Costs You the Most", "Don't Wait."
        return f"How $150 a Month Can Grow Past ${n['growth_final'] / 1000:,.0f}K", f"${n['growth_final'] / 1000:,.0f}K?"
    if b.family == "invest":
        if variant == "the mistake":
            return "The Investing Mistake That Quietly Costs a Fortune", "Watch The Fees."
        return f"How a 1% Investment Fee Can Cost ${n['fee_gap'] / 1000:,.0f}K", f"1% = ${n['fee_gap'] / 1000:,.0f}K."
    if b.family == "scam":
        if variant == "the mistake":
            return "The Mistake Scammers Count On", "Hang Up."
        return f"{t}: The Red Flags Most People Miss", "Don't Pay That."
    if b.family == "credit_file":
        if variant == "the mistake":
            return "The Credit Report Mistake Most People Make", "Check It."
        return f"{t}: Errors Are More Common Than You Think", "Check This Now."
    if b.family == "bank":
        if variant == "the mistake":
            return "The Banking Mistake That's Hard to Undo", "Double-Check."
        return f"{t}: The Fees and Risks Most People Miss", "Stop Paying This."
    return f"{t}: What Most People Get Wrong", "Read This First."


def make_metadata(b: Brief, script: Script, variant: str = "") -> dict:
    title, thumb = titles_for(b, variant)
    if script.format == "short" and "#shorts" not in title.lower():
        title = f"{title} #Shorts"
    sources = [f"- {f.source}: {f.url}" for f in b.facts if f.url]
    calcs = [f"- {f.text}" for f in b.facts if f.kind == "CALCULATION"]
    desc = [f"{b.topic}, explained in plain English with original hand-drawn animation, for viewers in the US "
            "and Canada.", "", "{CHAPTERS}"]
    if sources:
        desc += ["Sources:"] + sources + [""]
    if calcs:
        desc += ["How the examples were calculated:"] + calcs + [""]
    desc += [DISCLAIMER, "Examples use hypothetical numbers unless a source is cited. Rates and rules change; "
             "check current terms with your provider."]
    if script.format == "short":
        desc += ["", "#Shorts #personalfinance #money"]
    concept_words = [w for w in b.topic.lower().replace(",", "").split() if len(w) > 3]
    tags = list(dict.fromkeys([b.topic.lower(), b.category.lower(), "personal finance", "money tips",
                               "finance for beginners", "usa", "canada", "GLIVARAO Finance"] + concept_words))[:20]
    return {"title": title[:100], "description": "\n".join(desc), "tags": tags, "thumbnail_text": thumb}


def finalize_description(description: str, scene_headings: list[str], scene_starts: list[float],
                         long_form: bool) -> str:
    """Insert YouTube chapters (long videos need >= 3 chapters starting at 0:00, each >= 10 s)."""
    lines = []
    if long_form and len(scene_starts) >= 3:
        last = -99.0
        for h, t in zip(scene_headings, scene_starts):
            if t == 0 or t - last >= 10:
                lines.append(f"{int(t // 60)}:{int(t % 60):02d} {h}")
                last = t
        if len(lines) >= 3:
            lines = ["Chapters:"] + lines + [""]
        else:
            lines = []
    return description.replace("{CHAPTERS}", "\n".join(lines) if lines else "").replace("\n\n\n", "\n\n")
