"""Titles, descriptions (with chapters and sources), tags and thumbnail text, generated from the brief.

Titles create curiosity but must stay accurate. Every number used comes from the brief's calculations or data.
"""
from __future__ import annotations

import re

from ..models import Script
from .brief import Brief

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
        return f"{t}: The Red Flags That Are Easy to Miss", "Don't Pay That."
    if b.family == "credit_file":
        if variant == "the mistake":
            return "The Credit Report Mistake to Check For", "Check It."
        return f"{t}: Errors Are More Common Than You Think", "Check This Now."
    if b.family == "bank":
        if variant == "the mistake":
            return "The Banking Mistake That's Hard to Undo", "Double-Check."
        return f"{t}: The Fees and Risks That Are Easy to Miss", "Stop Paying This."
    return f"{t}: What's Easy to Get Wrong", "Read This First."


def make_metadata(b: Brief, script: Script, variant: str = "") -> dict:
    title, thumb = titles_for(b, variant)
    if script.format == "short" and "#shorts" not in title.lower():
        title = f"{title} #Shorts"
    # sources of what the video says (research evidence such as search-suggestion links stays in the review)
    sources = [f"- {f.source}: {f.url}" for f in b.facts if f.url and f.source != "Google search suggestions"]
    calcs = [f"- {f.text}" for f in b.facts if f.kind == "CALCULATION"]
    desc = [f"{b.topic}, explained in plain English with original hand-drawn animation: everyday "
            "US personal finance, no jargon.", "", "{CHAPTERS}"]
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
                               "finance for beginners", "usa", "budgeting", "GLIVARAO Finance"] + concept_words))[:20]
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
        x = short_title(title_case(x.strip()))
        if x and x.lower() not in {o.lower() for o in out}:
            out.append(x)
    return out[:3]


TITLE_MAX = 60
_TSTOP = set("a an the and or of to in on for with your my our at by from is are vs".split())


def short_title(t: str, limit: int = TITLE_MAX) -> str:
    """A title of at most `limit` characters: drop a trailing clause after ':', ' - ' or '(' first, else cut at a
    word boundary and never end on a small word. ' #Shorts' is kept."""
    tag = " #Shorts" if t.endswith("#Shorts") else ""
    body = t[: -len(tag)].strip() if tag else t.strip()
    room = limit - len(tag)
    for sep in (" (", ": ", " - ", " — "):
        if len(body) > room and sep in body:
            body = body.split(sep)[0].strip()
    if len(body) > room:
        ws = body[:room + 1].split()
        if len(" ".join(ws)) > room:
            ws = ws[:-1]
        while len(ws) > 1 and ws[-1].lower().strip(",.;:") in _TSTOP:
            ws.pop()
        body = " ".join(ws).rstrip(",;:")
    return body + tag


RESEARCH_ONLY = re.compile(r"stackexchange\.com|stackoverflow\.com|reddit\.com|quora\.com", re.I)
_MY_TAKE = ' The "My take" section is the channel host\'s own view.'


def _plain_inputs(m: "re.Match") -> str:
    import ast

    try:
        d = ast.literal_eval(m.group(1))
    except (ValueError, SyntaxError):
        return ""
    parts = [f"{str(k).replace('_', ' ')} {v}" for k, v in d.items() if v not in (0, 0.0, None, "", [])]
    return ("for " + ", ".join(parts)) if parts else ""


def clean_description(desc: str, has_take: bool, disclosure: str = "", keep_disclosure: bool = False) -> str:
    """The description that goes to YouTube: research-only links (Stack Exchange, Reddit...) are not sources, no
    Python dicts (one plain sentence per example), no [AFFILIATE: ...] placeholders and no affiliate disclosure
    until real links exist, and no 'My take' sentence when the video has none."""
    lines = []
    for ln in desc.split("\n"):
        if RESEARCH_ONLY.search(ln) or re.search(r"\[AFFILIATE:[^\]]*\]", ln):
            continue
        ln = re.sub(r"\(?inputs:\s*(\{[^}]*\})\s*;?\s*", lambda m: _plain_inputs(m) + "; ", ln)
        ln = re.sub(r";\s*\)", ")", ln).replace("(; ", "(").replace("()", "").rstrip("; ")
        lines.append(ln)
    out = "\n".join(lines)
    if disclosure and not keep_disclosure:
        out = out.replace(disclosure, "")
    if not has_take:
        out = out.replace(_MY_TAKE, "")
    out = re.sub(r"\n{3,}", "\n\n", out).strip() + "\n"
    out = re.sub(r"(?m)^Sources:\s*\n(?=\n|\Z)", "", out)        # an empty Sources block goes too
    return out


def add_affiliate_disclosure(description: str, text: str) -> str:
    if not text or text in description:
        return description
    return description.rstrip() + "\n\n" + text + "\n"
