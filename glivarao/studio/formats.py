"""Video formats. Each one has its own structure, opening, closing and on-screen look, so the channel never
settles into one template. The format is chosen per video by rotation (least recently used, never the same
twice in a row) among the formats that suit the topic.

`news_breakdown` covers consumer-finance changes only (new complaint data, rule or limit changes), never
politics or general economic news, in line with the channel's finance-only rule.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Format:
    key: str
    label: str              # shown to you in Telegram
    kicker: str             # first on-screen card
    accent: str             # editorial palette colour for this format
    summary: str            # one line for the topic message
    claude_structure: str   # structure instructions for the Claude writer
    intros: tuple = field(default_factory=tuple)
    outros: tuple = field(default_factory=tuple)


FORMATS: dict[str, Format] = {
    "explainer": Format(
        "explainer", "Explainer", "EXPLAINER", "navy",
        "How it works, the math, the mistakes, and a plan.",
        "Classic explainer: concrete opening situation; how it works step by step; worked numbers; common "
        "mistakes; a three-step action plan; short recap.",
        intros=("Let's untangle {topic}, step by step, with real numbers.",
                "{Topic} sounds complicated. It doesn't have to be. Here's how it actually works.",
                "If {topic} has ever confused you, you're not alone. Let's make it simple.",
                "Here's what nobody explains clearly about {topic}, and why it matters for your money."),
        outros=("That's {topic}, in plain English. Pick one step from the plan and do it this week.",
                "Now you know how {topic} really works. Start with the first step, and let it build.",
                "Small, steady moves beat perfect plans. That's the whole lesson on {topic}.")),
    "myth_vs_fact": Format(
        "myth_vs_fact", "Myth vs Fact", "MYTH VS FACT", "crimson",
        "Common beliefs, tested one by one against the facts.",
        "Myth vs fact: open with the most common belief; then 3-4 rounds, each a scene with beat 'myth' (the belief, "
        "stated fairly) followed by a scene with beat 'fact' (what's actually true, with numbers or a source); end "
        "with what to do instead.",
        intros=("You've probably heard a few things about {topic} that just aren't true. Let's test them.",
                "Some of the most repeated advice about {topic} is wrong. Here are the myths, and the facts.",
                "Let's put the popular beliefs about {topic} to the test, one at a time."),
        outros=("Myths are easy to repeat. Facts are worth checking. Now you've got the facts on {topic}.",
                "Next time someone repeats one of these myths about {topic}, you'll know the real story.")),
    "case_study": Format(
        "case_study", "Case study", "CASE STUDY", "green",
        "One hypothetical household, followed decision by decision.",
        "Case study: follow ONE clearly hypothetical person (say so on screen and in narration) through a real "
        "decision: the situation (beat 'case'), option one with numbers, option two with numbers, what happened, "
        "and the lesson for the viewer. Never imply the person is real.",
        intros=("Meet {name}, a hypothetical example, facing a very real decision about {topic}.",
                "Let's follow one hypothetical household, {name}'s, through a decision about {topic}.",
                "This is a made-up example, but the numbers are real math. Meet {name}."),
        outros=("{name} isn't real, but the math is. Run your own numbers the same way.",
                "Every situation is different, but {name}'s numbers show what really moves the needle.")),
    "viewer_question": Format(
        "viewer_question", "Viewer question", "YOU ASKED", "amber",
        "A real question people are asking online, answered properly.",
        "Viewer question: open with the real question (beat 'question', quote it and say where it was asked); give "
        "the short answer first; then the why; the numbers; the follow-up questions people usually have; and a "
        "clear takeaway.",
        intros=("Here's a question people keep asking about {topic}: {question}",
                "A real question from the internet today: {question} Let's answer it properly.",
                "Someone asked this, and it's a great question: {question}"),
        outros=("That's the honest answer. If you have a question about {topic}, it might be the next video.",
                "Great question, and now a clear answer. Keep the questions coming.")),
    "comparison": Format(
        "comparison", "Comparison", "SIDE BY SIDE", "navy",
        "Two choices, side by side, with the numbers.",
        "Comparison: set up the two choices; a scene with beat 'option_a' and one with beat 'option_b' (each with "
        "numbers); a side-by-side chart; when each one makes sense; a fair verdict (beat 'verdict') with caveats.",
        intros=("Two ways to handle {topic}. Same starting point, very different results. Let's compare.",
                "Option A or option B? When it comes to {topic}, the difference is bigger than it looks.",
                "Let's put two approaches to {topic} side by side, and let the numbers decide."),
        outros=("Neither option is right for everyone. But now you can compare them with real numbers.",
                "The best choice depends on your situation. The comparison just made it clearer.")),
    "news_breakdown": Format(
        "news_breakdown", "What changed (data / rules)", "WHAT CHANGED", "crimson",
        "New consumer-finance data or rules, and what they mean for you.",
        "Consumer-finance update (never politics or market news): what changed, with the source (beat 'update'); "
        "what it means in plain English; who is affected; what to do now; what to watch next.",
        intros=("New data just came out on {topic}, and it says something important.",
                "Something changed with {topic}. Here's what it is, and what it means for you.",
                "The latest numbers on {topic} are in. Let's break them down."),
        outros=("That's what changed with {topic}, and what to do about it. We'll keep an eye on it.",
                "Data changes. The basics don't. Check the sources below, and act on what matters to you.")),
}

PERSONAS = ("Dana", "Marcus", "Priya", "Luis", "Grace", "Owen", "Aisha", "Tom")


def eligible(brief) -> list[str]:
    """Formats that genuinely suit this topic's material."""
    keys = ["explainer", "myth_vs_fact", "case_study"]
    if brief.viewer_questions:
        keys.append("viewer_question")
    if brief.calcs and len(brief.calcs) >= 2:
        keys.append("comparison")
    if any(p.get("year_ago") and p["complaints_90d"] > p["year_ago"] * 1.1 for p in brief.problems) or \
            getattr(brief, "news", None):
        keys.append("news_breakdown")
    return keys


def choose_format(brief, history: list[str]) -> str:
    """Least recently used eligible format, never the same as the last video."""
    options = eligible(brief)
    last = history[-1] if history else None
    def recency(k):
        return max((i for i, h in enumerate(history) if h == k), default=-1)
    ranked = sorted((k for k in options if k != last), key=recency)
    return ranked[0] if ranked else options[0]


def pick_line(pool: tuple, used: list[str], rng: random.Random, filler=lambda t: t) -> str:
    """A template whose filled-in line wasn't used recently (falls back to the least recently used one).
    `used` holds finished lines, which may carry trailing text (e.g. the disclaimer after a closing line)."""
    def last_use(p):
        line = filler(p)
        return max((i for i, u in enumerate(used) if line and line in u), default=-1)
    fresh = [p for p in pool if last_use(p) < 0]
    if fresh:
        return rng.choice(fresh)
    return min(pool, key=last_use)


def fill(template: str, **kw) -> str:
    topic = kw.get("topic", "")
    return template.format(topic=topic, Topic=topic[:1].upper() + topic[1:], **{k: v for k, v in kw.items()
                                                                               if k != "topic"})


__all__ = ["FORMATS", "Format", "PERSONAS", "eligible", "choose_format", "pick_line", "fill"]
