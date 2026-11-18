"""Format-aware free writer: a different structure, opening, closing and on-screen beats per format, plus the
creator's own input woven in as a "My take" scene. Builds on the reviewed library and exact calculators.

Openings, closings and Short hooks rotate from pools and avoid lines used recently (`used_lines`).
"""
from __future__ import annotations

import random
import re

from ..models import Scene, Script
from ..studio.formats import FORMATS, PERSONAS, fill, pick_line
from .brief import Brief, topic_phrase
from .library import LIB, MYTHS
from .writer import DISCLAIMER, _data_hook, _fit_short, _lc, _math_scenes, _s, _wrap

SHORT_KINDS = ("number", "myth", "mistake", "question", "tip")
SHORT_HOOKS = {
    "number": ("One number about {topic} that most people never see:", "Here's the math on {topic} in under a minute.",
               "Watch what happens to the numbers on {topic}."),
    "myth": ("Here's a {topic} myth that costs people money.", "You've probably heard this about {topic}. It's wrong.",
             "Myth or fact? Let's settle it fast."),
    "mistake": ("The {topic} mistake I see most often.", "Don't make this {topic} mistake.",
                "One {topic} habit that quietly costs you."),
    "question": ("Someone asked: {question}", "Real question, quick answer: {question}",
                 "Here's a question people keep asking: {question}"),
    "tip": ("One move that makes {topic} easier.", "If you do one thing about {topic} this week, do this.",
            "Here's the simplest fix for {topic}."),
}


def clean_creator_text(text: str, max_words: int = 140) -> str:
    """Tidy the host's own words for narration: whitespace, a closing period, a sensible length."""
    t = re.sub(r"\s+", " ", (text or "")).strip().strip('"')
    words = t.split()
    if len(words) > max_words:  # cut at a sentence boundary within the limit
        cut = " ".join(words[:max_words])
        t = cut[: cut.rfind(".") + 1] if "." in cut else cut + "."
    if t and t[-1] not in ".!?":
        t += "."
    return t


def creator_scene(text: str, rng: random.Random) -> Scene:
    lead = rng.choice(("Here's my own take.", "Let me add my own view here.", "Speaking for myself:",
                       "From my own experience:"))
    return _s("My take", f"{lead} {clean_creator_text(text)}", "lightbulb", "studio").model_copy(
        update={"beat": "creator", "key_points": []})


def _b(scene: Scene, beat: str) -> Scene:
    return scene.model_copy(update={"beat": beat})


def _question(b: Brief) -> str:
    return (b.viewer_questions[0]["title"].rstrip("?") + "?") if b.viewer_questions else ""


def write_long_format(b: Brief, style: str, creator_text: str = "", used_lines: list[str] | None = None,
                      variant: int = 0) -> Script:
    fmt = FORMATS[style]
    used = used_lines or []
    rng = random.Random(f"{b.date}{b.topic_key}{style}{variant}")
    lib = LIB.get(b.family, LIB["generic"])
    topic = topic_phrase(b.topic)
    name = rng.choice(PERSONAS)
    question = _question(b)
    f = lambda t: fill(t, topic=topic, name=name, question=question)  # noqa: E731
    intro = f(pick_line(fmt.intros, used, rng, f))
    outro = f(pick_line(fmt.outros, used, rng, f))
    math = _math_scenes(b)
    hook = _data_hook(b)
    take = creator_scene(creator_text, rng) if creator_text.strip() else None
    acts = lib["actions"]
    plan = _s("What to do", f"So here's what to do. One: {_lc(acts[0])}. Two: {_lc(acts[1])}. "
              f"And three: {_lc(acts[2])}.", "target", "studio", key_points=acts)
    sc: list[Scene] = []

    if style == "myth_vs_fact":
        sc.append(_s("Myth vs fact", intro, "warning", "studio"))
        for i, (myth, fact, illo) in enumerate(MYTHS.get(b.family, MYTHS["generic"])[:3]):
            nth = ("one", "two", "three", "four")[i]
            sc.append(_b(_s(f"Myth {i + 1}", f"Myth number {nth}: {myth[0].lower() + myth[1:]}", "warning",
                            "studio"), "myth"))
            sc.append(_b(_s("The fact", f"The fact: {fact}", illo, "board"), "fact"))
            if i == 0 and math:
                sc.append(math[0])
        if take:
            sc.append(take)
        sc.append(plan)
    elif style == "case_study":
        sc.append(_b(_s(f"Case: {name}", f"{intro} {name} is working on {topic}, and has two realistic options. "
                        "Everything here is a hypothetical example, but the math is exact.", "paycheck", "home"), "case"))
        for h, n, illo, st in lib["how"][:1]:
            sc.append(_s(h, n, illo, st))
        for i, m in enumerate(math[:2]):
            prefix = f"Option {'one' if i == 0 else 'two'} for {name}. "
            sc.append(_b(m.model_copy(update={"narration": prefix + m.narration}), "option_a" if i == 0 else "option_b"))
        sc.append(_s("What we can learn", f"{name}'s lesson applies to most of us: {_lc(acts[0])}.", "lightbulb",
                     "studio"))
        if take:
            sc.append(take)
        sc.append(plan)
    elif style == "viewer_question" and question:
        sc.append(_b(_s("The question", intro + " It was asked on a public personal-finance forum, and it deserves "
                        "a clear answer.", "lightbulb", "studio"), "question"))
        sc.append(_s("The short answer", f"The short answer: {_lc(acts[0])}. Now let's see why.", "target", "studio"))
        for h, n, illo, st in lib["how"]:
            sc.append(_s(h, n, illo, st))
        sc += math[:1]
        if take:
            sc.append(take)
        mh, mn, mi, ms = lib["mistakes"][0]
        sc.append(_s("The follow-up question", f"People usually ask next: what should I avoid? {mn}", mi, ms))
        sc.append(plan)
    elif style == "comparison" and len(math) >= 2:
        sc.append(_s("Side by side", intro, "scale", "studio"))
        sc.append(_b(math[0].model_copy(update={"heading": "Option A"}), "option_a"))
        sc.append(_b(math[1].model_copy(update={"heading": "Option B"}), "option_b"))
        for h, n, illo, st in lib["how"][1:2]:
            sc.append(_s(h, n, illo, st))
        if take:
            sc.append(take)
        sc.append(_b(_s("The verdict", f"So which is better? For most people, {_lc(acts[0])}. But your own "
                        "numbers and goals decide. Run the comparison with your real figures.", "scale", "studio"),
                     "verdict"))
    elif style == "news_breakdown" and hook:
        sc.append(_b(_s("What changed", f"{intro} {hook[0]} That's from the US Consumer Financial Protection Bureau's "
                        "public complaint database.", "warning", "city", key_points=hook[1]), "update"))
        sc.append(_s("What it means", lib["how"][0][1], lib["how"][0][2], lib["how"][0][3]))
        sc.append(_s("Who is affected", lib["how"][-1][1], lib["how"][-1][2], lib["how"][-1][3]))
        sc += math[:1]
        if take:
            sc.append(take)
        sc.append(plan)
        sc.append(_s("What to watch next", "Complaint numbers are a signal, not a full picture of every consumer. "
                     "We'll keep watching the data, and update you if it changes again.", "calendar", "studio"))
    else:  # explainer (and the fallback when a format's material is missing)
        style = "explainer"
        fmt = FORMATS[style]
        intro = f(pick_line(fmt.intros, used, rng, f))
        outro = f(pick_line(fmt.outros, used, rng, f))
        opener = f"{intro} {hook[0]}" if hook else intro
        sc.append(_s(b.topic[:40], opener, "lightbulb", "studio", key_points=hook[1] if hook else None))
        for h, n, illo, st in lib["how"]:
            sc.append(_s(h, n, illo, st))
        sc += math
        if take:
            sc.append(take)
        for h, n, illo, st in lib["mistakes"]:
            sc.append(_s(h, n, illo, st))
        sc.append(plan)
    sc.append(_s("Wrap-up", f"{outro} {DISCLAIMER}", "lightbulb", rng.choice(["studio", "city"])))
    script = _wrap(b, "long", sc)
    return script.model_copy(update={"style": style, "hook": intro})


def write_shorts_format(b: Brief, long_style: str, n: int = 2, used_lines: list[str] | None = None,
                        creator_text: str = "") -> list[Script]:
    """n Shorts, each with its own hook and its own single point (different kinds, not cut from the long)."""
    used = list(used_lines or [])
    rng = random.Random(f"{b.date}{b.topic_key}shorts")
    lib = LIB.get(b.family, LIB["generic"])
    topic = topic_phrase(b.topic)
    question = _question(b)
    math = _math_scenes(b)
    avoid = {"myth_vs_fact": "myth", "viewer_question": "question"}.get(long_style)
    kinds = [k for k in ("number", "myth", "mistake", "question", "tip")
             if k != avoid and (k != "number" or math) and (k != "question" or question)]
    rng.shuffle(kinds)
    out = []
    for kind in kinds[:n]:
        fh = lambda t: fill(t, topic=topic, question=question)  # noqa: E731
        hook = fh(pick_line(SHORT_HOOKS[kind], used, rng, fh))
        used.append(hook)
        if kind == "number":
            body = [math[0].model_copy(update={"heading": "The math"})]
            point = f"The takeaway: {_lc(lib['actions'][0])}."
        elif kind == "myth":
            myth, fact, illo = rng.choice(MYTHS.get(b.family, MYTHS["generic"]))
            body = [_b(_s("Myth", f"The myth: {myth[0].lower() + myth[1:]}", "warning", "studio"), "myth"),
                    _b(_s("Fact", f"The fact: {fact}", illo, "board"), "fact")]
            point = "Check the facts before you follow the advice."
        elif kind == "mistake":
            mh, mn, mi, ms = rng.choice(lib["mistakes"])
            body = [_s(mh.replace("Mistake: ", "").capitalize(), mn, mi, ms)]
            point = f"Instead: {_lc(lib['actions'][1])}."
        elif kind == "question":
            body = [_b(_s("The question", question, "lightbulb", "studio"), "question"),
                    _s("Quick answer", f"Quick answer: {_lc(lib['actions'][0])}.", "target", "studio")]
            point = "Every situation is different, but that's the rule of thumb."
        else:
            body = [_s("The move", f"{lib['actions'][rng.randrange(len(lib['actions']))]}. "
                       + lib["how"][0][1].split(". ")[0] + ".", lib["how"][0][2], "studio")]
            point = "Small step, real difference."
        scenes = [_s("Hook", hook, "warning", "studio", entrance="walk_in")] + body + \
                 [_s("Takeaway", f"{point} {DISCLAIMER}", "target", "studio")]
        taken = " ".join(sc.narration for o in out for sc in o.scenes)
        script = _wrap(b, "short", _fit_short(scenes, lib, avoid=taken),
                       suffix="the mistake" if kind in ("mistake", "myth") else "the number")
        out.append(script.model_copy(update={"style": f"short_{kind}", "hook": hook}))
    return out


__all__ = ["write_long_format", "write_shorts_format", "creator_scene", "clean_creator_text", "SHORT_HOOKS"]
