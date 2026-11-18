"""Script writers: brief -> Script (long video + two Shorts).

* Claude writer: production quality, fully original wording. Runs ONLY when ALLOW_PAID_APIS=true and an
  Anthropic key is configured (owner approval required, since it costs money).
* Free writer (default): assembles the script from research data, exact calculations and the reviewed
  editorial library. Accurate and finance-only, but more formulaic and shorter than the 15-18 minute target.
"""
from __future__ import annotations

import random

from ..config import Settings
from ..models import ChartSpec, Scene, Script
from . import calculators as calc
from .brief import Brief, topic_phrase
from .library import LIB

DISCLAIMER = "This video is for education only and isn't financial advice."


def _s(heading, narration, illustration="coin_stack", set_=None, character="max", chart=None, key_points=None,
       money_fx=None, entrance=None) -> Scene:
    return Scene(heading=heading[:40], narration=narration, character=character, illustration=illustration,
                 set=set_, chart=chart or ChartSpec(), key_points=key_points or [], money_fx=money_fx,
                 entrance=entrance)


def _money(v: float) -> str:
    return calc.spoken_money(v).replace("about ", "")


def _data_hook(b: Brief) -> tuple[str, list[str]] | None:
    """A hook sentence built from a DATA fact (CFPB growth), with on-screen key points."""
    p = next((p for p in b.problems if p.get("year_ago") and p["complaints_90d"] > p["year_ago"]), None)
    if not p:
        return None
    growth = p["complaints_90d"] / p["year_ago"] - 1
    issue = p["issue"]
    issue = ("problems with" + issue[len("Problem with"):]) if issue.startswith("Problem with") else issue.lower()
    issue = issue.replace("your statement", "a statement").replace("your ", "a ")
    return (f"In just the last three months, consumers filed {p['complaints_90d']:,} complaints with the US "
            f"Consumer Financial Protection Bureau in a single category: {issue}. That's up {growth:.0%} from the "
            "same months a year ago.",
            [f"{p['complaints_90d']:,} complaints in 90 days", f"Up {growth:.0%} year over year"])


def _math_scenes(b: Brief) -> list[Scene]:
    c = b.calcs
    if b.family == "card":
        mp, fx = c["minimum"].results, c["fixed"].results
        years = [str(y) for y in range(0, len(mp["yearly_balance"]))]
        return [
            _s("The minimum payment math", f"Let's run the numbers. Say you owe five thousand dollars on a card "
               f"with a twenty-four percent APR, and you pay only the minimum. It would take about "
               f"{mp['years']:.0f} years to pay off, and you'd pay {_money(mp['total_interest'])} in interest. "
               "*More than the original balance.*", "credit_card", "board",
               chart=ChartSpec(kind="line_series", title="$5,000 at 24% APR, minimum payments only", unit="$",
                               labels=years, values=mp["yearly_balance"], source="Calculated example")),
            _s("A fixed payment instead", f"Now pay a fixed two hundred dollars a month instead. The same card is "
               f"paid off in about {fx['years']:.0f} years, with {_money(fx['total_interest'])} in interest. Same debt, "
               "very different outcome.", "scale", "board",
               chart=ChartSpec(kind="bar_compare", title="Total interest on $5,000 at 24% APR", unit="$",
                               labels=["Minimum only", "$200/month"],
                               values=[mp["total_interest"], fx["total_interest"]], source="Calculated example")),
        ]
    if b.family == "loan":
        lo, lr = c["loan"], c["lower_rate"]
        p, apr, yrs = lo.inputs["principal"], lo.inputs["apr"], lo.inputs["years"]
        return [
            _s("Where your payment goes", f"Here's an example. Borrow {_money(p)} at {apr * 100:g} percent for {yrs} "
               f"years, and the monthly payment is about {_money(lo.results['monthly_payment'])}. In the very first "
               f"payment, {_money(lo.results['first_payment_interest'])} is interest, and only "
               f"{_money(lo.results['first_payment_principal'])} actually pays down the loan.", "house", "board",
               chart=ChartSpec(kind="pie_split", title="First payment: interest vs principal", unit="$",
                               labels=["Interest", "Principal"],
                               values=[lo.results["first_payment_interest"], lo.results["first_payment_principal"]],
                               source="Calculated example")),
            _s("One percentage point", f"Over the full term, that loan costs {_money(lo.results['total_interest'])} in "
               f"interest. Get a rate just one percentage point lower, and total interest drops to "
               f"{_money(lr.results['total_interest'])}. *That's why shopping around matters.*", "scale", "board",
               chart=ChartSpec(kind="bar_compare", title=f"Total interest, {_money(p)} over {yrs} years", unit="$",
                               labels=[f"{apr * 100:g}% APR", f"{(apr - 0.01) * 100:g}% APR"],
                               values=[lo.results["total_interest"], lr.results["total_interest"]],
                               source="Calculated example")),
        ]
    if b.family in ("grow", "invest"):
        g, late, fees = c["growth"].results, c["late"].results, c["fees"].results
        first = _s("Small amounts, long time", f"Here's the math. Invest a hundred and fifty dollars a month at a "
                   f"hypothetical seven percent a year. After thirty years, that's {_money(g['final'])}, from "
                   f"{_money(g['contributed'])} of your own money.", "growth_arrow", "board",
                   chart=ChartSpec(kind="compound_growth", title="$150/month at a hypothetical 7% a year",
                                   params={"principal": 0, "rate": 0.07, "years": 30, "monthly": 150}))
        if b.family == "invest":
            second = _s("What fees really cost", f"Now fees. Invest five hundred dollars a month for thirty years. With a "
                        f"tiny fee, you might end with {_money(fees['final_low_fee'])}. With a one percent fee, about "
                        f"{_money(fees['final_high_fee'])}. *That gap is {_money(fees['difference'])}.*", "warning", "board",
                        chart=ChartSpec(kind="bar_compare", title="$500/month for 30 years, hypothetical 7%", unit="$",
                                        labels=["0.05% fee", "1% fee"],
                                        values=[fees["final_low_fee"], fees["final_high_fee"]],
                                        source="Calculated example"))
        else:
            second = _s("The cost of waiting", f"Start ten years later with the same habit, and you'd have about "
                        f"{_money(late['final'])}. *Waiting costs more than most people think.*", "hourglass", "board",
                        chart=ChartSpec(kind="bar_compare", title="$150/month at a hypothetical 7%", unit="$",
                                        labels=["Start now (30 yrs)", "Start later (20 yrs)"],
                                        values=[g["final"], late["final"]], source="Calculated example"))
        return [first, second]
    return []


def _question_scene(b: Brief) -> Scene | None:
    if not b.viewer_questions:
        return None
    q = b.viewer_questions[0]["title"].rstrip("?")
    lib = LIB.get(b.family, LIB["generic"])
    return _s("What people are asking", f"One question keeps coming up online: {q}? The honest answer is that it "
              f"depends on your situation. But the same principles apply: {_lc(lib['actions'][0])}, and "
              f"{_lc(lib['actions'][1])}.", "lightbulb", "studio", character="duo")


def _lc(text: str) -> str:
    """Lower-case the first letter for mid-sentence use, keeping acronyms and names (APR, FICO, US, CFPB)."""
    if not text:
        return text
    first = text.split()[0]
    if len(first) > 1 and first[1:2].isupper():  # acronym-led
        return text
    return text[0].lower() + text[1:]


def write_long_free(b: Brief) -> Script:
    lib = LIB.get(b.family, LIB["generic"])
    rng = random.Random(b.date + b.topic_key)
    scenes: list[Scene] = []
    hook = _data_hook(b)
    if hook:
        scenes.append(_s("A problem that's growing", hook[0] + " So what's going on, and what can you do about it?",
                         "warning", "city", key_points=hook[1], entrance="walk_in"))
    else:
        scenes.append(_s(b.topic[:40], f"Let's talk about {topic_phrase(b.topic)}. It affects more people than you'd "
                         "think, and a few simple moves can save you real money.", "lightbulb", "studio",
                         entrance="walk_in"))
    scenes.append(_s("Meet Max", f"Meet Max. Like a lot of people in the US and Canada, he's busy, he's careful with "
                     f"money, and he's never had anyone explain {topic_phrase(b.topic)} in plain English. Today, Penny and I "
                     "are going to fix that.", "coin_stack", "home", character="duo"))
    for h, n, illo, st in lib["how"]:
        scenes.append(_s(h, n, illo, st))
    if "angle_extra" in lib and any(k in b.angle.lower() for k in lib["angle_extra"]["triggers"]):
        h, n, illo, st = lib["angle_extra"]["scene"]
        scenes.append(_s(h, n, illo, st))
    scenes += _math_scenes(b)
    q = _question_scene(b)
    if q:
        scenes.append(q)
    for h, n, illo, st in lib["mistakes"]:
        scenes.append(_s(h, n, illo, st))
    acts = lib["actions"]
    scenes.append(_s("Your action plan", f"So here's your plan. One: {_lc(acts[0])}. Two: {_lc(acts[1])}. "
                     f"And three: {_lc(acts[2])}.", "target", "studio", key_points=acts))
    scenes.append(_s("Recap", f"That's {topic_phrase(b.topic)}, without the jargon. Small, consistent steps beat perfect "
                     f"plans. Thanks for watching GLIVARAO Finance. {DISCLAIMER}", "lightbulb",
                     rng.choice(["city", "studio"])))
    return _wrap(b, "long", scenes)


def write_shorts_free(b: Brief) -> list[Script]:
    lib = LIB.get(b.family, LIB["generic"])
    shorts = []
    math = _math_scenes(b)
    hook = _data_hook(b)
    if math:
        m = math[0]
        a = [_s("Wait for this number", f"Here's a number about {topic_phrase(b.topic)} that surprises people.",
                "warning", "studio", entrance="walk_in"),
             m.model_copy(update={"heading": "The math"}),
             _s("Why it happens", lib["how"][-1][1].split(". ")[0] + ".", lib["how"][-1][2], "home"),
             _s("What to do", f"The fix? {lib['actions'][0]}. Small changes, big difference. {DISCLAIMER}",
                "target", "studio")]
    elif hook:
        a = [_s("This is growing fast", hook[0], "warning", "city", key_points=hook[1][:1], entrance="walk_in"),
             _s("Why it matters", lib["how"][0][1].split(". ")[0] + ".", lib["how"][0][2], "studio"),
             _s("What to do", f"Here's what to do: {_lc(lib['actions'][0])}, and "
                f"{_lc(lib['actions'][1])}. {DISCLAIMER}", "target", "studio")]
    else:
        a = [_s(b.topic[:40], lib["how"][0][1], lib["how"][0][2], "studio", entrance="walk_in"),
             _s("What to do", f"{lib['actions'][0]}. {DISCLAIMER}", "target", "studio")]
    shorts.append(_wrap(b, "short", _fit_short(a, lib), suffix="the number"))
    mh, mn, mi, ms = lib["mistakes"][0]
    bq = [_s("Avoid this mistake", f"Here's a mistake people make with {topic_phrase(b.topic)}, and it's more common "
             "than you'd think.", "warning", "home", entrance="walk_in"),
          _s(mh.replace("Mistake: ", "").capitalize(), mn, mi, ms),
          _s("Why it matters", lib["how"][0][1].split(". ")[0] + ". " + lib["how"][0][1].split(". ")[1] + ".",
             lib["how"][0][2], "studio"),
          _s("Do this instead", f"Instead, {_lc(lib['actions'][1])}. And {_lc(lib['actions'][2])}. "
             f"{DISCLAIMER}", "target", "studio")]
    shorts.append(_wrap(b, "short", _fit_short(bq, lib, prefer="mistakes"), suffix="the mistake"))
    return shorts


SHORT_MIN_WORDS, SHORT_MAX_WORDS = 95, 150


def _sentences(text: str) -> list[str]:
    import re

    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]


def _fit_short(scenes: list[Scene], lib: dict, prefer: str = "how", avoid: str = "") -> list[Scene]:
    """Bring a Short into the 95-150 word range by adding explanation sentences from the reviewed library
    (never filler), inserted before the final call-to-action scene. `avoid`: text already used by other Shorts."""
    words = sum(len(s.narration.split()) for s in scenes)
    used = " ".join(s.narration for s in scenes) + " " + avoid
    pool = []
    for group in ([prefer, "how", "mistakes"] if prefer != "how" else ["how", "mistakes"]):
        for h, n, illo, st in lib[group]:
            pool += [(h, x, illo, st) for x in _sentences(n) if x not in used]
    extra: dict[str, list] = {}
    for h, sent, illo, st in pool:
        if words >= SHORT_MIN_WORDS:
            break
        if words + len(sent.split()) > SHORT_MAX_WORDS:
            continue
        extra.setdefault(h, [illo, st, []])[2].append(sent)
        words += len(sent.split())
    added = [_s(h.replace("Mistake: ", "").capitalize(), " ".join(sents), illo, st)
             for h, (illo, st, sents) in extra.items()]
    return scenes[:-1] + added + scenes[-1:]


def _wrap(b: Brief, fmt: str, scenes: list[Scene], suffix: str = "") -> Script:
    from .packaging import make_metadata

    script = Script(format=fmt, topic=b.topic, title="(set by packaging)", description="", tags=[],
                    thumbnail_text="", hook=scenes[0].narration.split(".")[0], scenes=scenes)
    meta = make_metadata(b, script, variant=suffix)
    return script.model_copy(update=meta)


# ------------------------------------------------------------------ Claude writer (paid; approval required)
def write_with_claude(b: Brief, fmt: str, settings: Settings, angle: str = "", style: str | None = None,
                      creator_text: str = "", avoid_lines: list[str] | None = None) -> Script:
    """Grounded generation: the model may only use facts from the brief's fact sheet; the format sets the
    structure; the host's own input is woven in as a 'creator' scene; recent openings are off limits."""
    from ..scriptgen.claude import generate_with_claude
    from ..studio.formats import FORMATS

    facts = "\n".join(f"- [{f.kind}] {f.text}" for f in b.facts)
    grounding = (f"{angle or b.angle}\n\nUse ONLY these facts and numbers; do not introduce any other statistic, "
                 f"rate, limit or date:\n{facts}\n\nReal viewer questions to address:\n" +
                 "\n".join(f"- {q['title']}" for q in b.viewer_questions) +
                 f"\nAudience: the United States and Canada. Category: {b.category}. Finance only.")
    if style and style in FORMATS:
        grounding += f"\n\nFORMAT: {FORMATS[style].label}. {FORMATS[style].claude_structure}"
    if creator_text.strip():
        grounding += ("\n\nTHE HOST'S OWN INPUT (their real opinion or experience, in their words):\n\"\"\""
                      f"{creator_text.strip()}\"\"\"\nInclude exactly one scene with beat 'creator' that presents this "
                      "faithfully in first person ('In my experience...'). You may tidy grammar, never add facts, "
                      "numbers or claims to it. Let the rest of the script connect to it naturally.")
    if avoid_lines:
        grounding += "\n\nDo NOT open or close with any of these lines used in recent videos:\n" + \
                     "\n".join(f"- {x}" for x in avoid_lines[:20])
    script = generate_with_claude(b.topic, fmt, settings, angle=grounding)
    return with_house_description(b, script).model_copy(update={"style": style})


def with_house_description(b: Brief, script: Script) -> Script:
    """Keep Claude's summary paragraph, then add our chapters placeholder, sources, calculations and disclaimer
    (the same honest packaging the free writer uses)."""
    from .packaging import make_metadata

    house = make_metadata(b, script)["description"].split("\n")
    tail = "\n".join(house[house.index("{CHAPTERS}"):]) if "{CHAPTERS}" in house else "\n".join(house)
    summary = script.description.strip().split("\n\n")[0].strip()[:600]
    title = script.title
    if script.format == "short" and "#shorts" not in title.lower():
        title = f"{title[:91]} #Shorts"
    return script.model_copy(update={"description": f"{summary}\n\n{tail}"[:4900], "title": title[:100]})


def paid_writer_allowed(settings: Settings) -> bool:
    return bool(settings.allow_paid_apis and settings.anthropic_api_key)


__all__ = ["write_long_free", "write_shorts_free", "write_with_claude", "paid_writer_allowed"]
