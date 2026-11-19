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
    # sources of what the video says (research evidence such as search-suggestion links stays in the review)
    sources = [f"- {f.source}: {f.url}" for f in b.facts if f.url and f.source != "Google search suggestions"]
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
    block = "\n".join(lines) if lines else ""
    if "{CHAPTERS}" not in description and block:  # e.g. a hand-written description: chapters after paragraph 1
        head, _, rest = description.partition("\n\n")
        description = f"{head}\n\n{{CHAPTERS}}{rest}" if rest else f"{head}\n\n{{CHAPTERS}}"
    return description.replace("{CHAPTERS}", block).replace("\n\n\n", "\n\n").rstrip() + "\n"


FORMAT_TITLES = {
    "myth_vs_fact": ["{t}: 3 Myths That Cost You Money", "Myth or Fact? {t}, Tested"],
    "case_study": ["One Household, Two Choices: {t}", "What Would You Do? A {t} Case Study"],
    "viewer_question": ["{q}", "You Asked: {q}"],
    "comparison": ["{t}: Which Option Costs Less?", "Side by Side: {t}"],
    "news_breakdown": ["{n}: What It Means for You", "What Just Changed With {t}"],
    "explainer": ["{t}, Explained Simply", "How {t} Really Works"],
}


SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "with"}


def title_case(text: str) -> str:
    words = text.split()
    out = []
    for i, w in enumerate(words):
        if w.isupper() and len(w) > 1 or any(ch.isdigit() for ch in w):  # APR, 401(k), 2027
            out.append(w)
        elif i and w.lower() in SMALL:
            out.append(w.lower())
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def title_options(b: Brief, script: Script) -> list[str]:
    """The chosen title plus two honest alternatives (for YouTube Studio), all under 100 characters."""
    t = b.topic.split(",")[0].strip()
    q = (b.viewer_questions[0]["title"] if b.viewer_questions else f"Is {t} Worth It?").rstrip("?") + "?"
    n = (b.news[0]["title"].split(",")[0] if getattr(b, "news", None) else t)
    style = (script.style or "explainer")
    pool = [script.title]
    if script.format == "long":
        pool += [x.format(t=t, q=q, n=n) for x in FORMAT_TITLES.get(style, FORMAT_TITLES["explainer"])]
        pool += [titles_for(b)[0], titles_for(b, "the mistake")[0]]
    else:
        base = script.title.replace(" #Shorts", "")
        pool += [f"{q}", f"{t} in 60 Seconds", f"The {t} Rule Nobody Explains", base]
    out = []
    for x in pool:
        x = title_case(x.strip())[:100]
        if x and x.lower() not in {o.lower() for o in out}:
            out.append(x)
    return out[:3]


def add_affiliate_disclosure(description: str, text: str) -> str:
    if not text or text in description:
        return description
    return description.rstrip() + "\n\n" + text + "\n"
