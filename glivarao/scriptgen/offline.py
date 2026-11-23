"""Deterministic offline script generator.

Used for dry runs and tests (no API key, no network). Output is clearly generic placeholder
copy — production scripts come from scriptgen/claude.py.
"""
from __future__ import annotations

from ..models import ChartSpec, Scene, Script

DISCLAIMER = "This video is for education only and isn't financial advice."


def _long_scenes(topic: str, target_words: int) -> list[Scene]:
    t = topic.rstrip(".")
    core = [
        Scene(heading="Why this matters", character="max", pose="talk", illustration="lightbulb",
              narration=(f"Today we're digging into {t.lower()}. It sounds dry, but it quietly shapes how much "
                         "money you keep every single year. By the end, you'll know exactly how it works, "
                         "the mistakes that cost people the most, and three moves you can make in the next seven days."),
              key_points=["How it works", "Costly mistakes", "What to do next"]),
        Scene(heading="Meet Penny", character="duo", pose="cheer", illustration="coin_stack",
              narration=("I'm Max, and this is Penny, our resident coin with a lot of questions. Penny, what "
                         "do people often get wrong here? She says they wait too long. And she's right. Time "
                         "is the ingredient many people underestimate."),
              key_points=[]),
        Scene(heading="The core idea", character="max", pose="point", illustration="growth_arrow",
              narration=("Let's start with a simple example. Say you put away one thousand dollars and add "
                         "one hundred dollars a month. At a hypothetical seven percent average yearly return, "
                         "watch what happens over thirty years. The early years look boring. The later years "
                         "do most of the heavy lifting."),
              chart=ChartSpec(kind="compound_growth", title="$1,000 + $100/month at a hypothetical 7%",
                              unit="$", params={"principal": 1000, "rate": 0.07, "years": 30, "monthly": 100})),
        Scene(heading="Small fees, big gaps", character="penny", pose="worry", illustration="scale",
              narration=("Now compare two hypothetical paths that differ by a single percentage point a year. "
                         "One percent sounds tiny. Over decades it can mean tens of thousands of dollars. "
                         "That's why fees, interest rates and timing deserve your attention."),
              chart=ChartSpec(kind="bar_compare", title="Same savings, different yearly rate", unit="$",
                              labels=["5% per year", "6% per year", "7% per year"],
                              values=[83_000, 100_000, 122_000], source="Illustrative example")),
        Scene(heading="Common mistake #1", character="max", pose="worry", illustration="warning",
              narration=("Mistake number one is waiting for the perfect moment. There rarely is one. Starting "
                         "small and staying consistent usually beats starting big and late."),
              key_points=["Start small", "Stay consistent"]),
        Scene(heading="Common mistake #2", character="penny", pose="think", illustration="credit_card",
              narration=("Mistake number two is ignoring high-interest debt. Paying twenty-something percent on "
                         "a credit card balance can cancel out almost any return your savings earn."),
              key_points=["Pay down high-rate debt first"]),
        Scene(heading="Where the money goes", character="max", pose="point", illustration="paycheck",
              narration=("Here's one popular way to split a paycheck: about half for needs, some for wants, "
                         "and a slice for savings and debt payoff. It's a starting point, not a rule. Adjust "
                         "it to your own life."),
              chart=ChartSpec(kind="pie_split", title="One example budget split", unit="%",
                              labels=["Needs", "Wants", "Savings"], values=[50, 30, 20],
                              source="Illustrative example")),
        Scene(heading="Your action plan", character="duo", pose="cheer", illustration="target",
              narration=("So here's your checklist. One, find out what you're paying or earning today. Two, "
                         "automate one small step. Three, check back in three months and adjust."),
              key_points=["Know your numbers", "Automate one step", "Review in 3 months"]),
    ]
    filler = Scene(heading="Going deeper", character="max", pose="talk", illustration="bank",
                   narration=("Let's go one level deeper. Every dollar decision is a trade between now and later. "
                              "When you understand the trade, you stop guessing and start choosing on purpose. "
                              "That shift, more than any single trick, is what changes long-term results."))
    outro = Scene(heading="Recap", character="max", pose="talk", illustration="calendar",
                  narration=(f"Quick recap: {t.lower()} rewards patience, punishes high costs, and works best "
                             f"when it's automatic. Thanks for watching GLIVARAO Finance. {DISCLAIMER}"),
                  key_points=["Patience", "Low costs", "Automation"])

    scenes = list(core)
    words = sum(len(s.narration.split()) for s in scenes + [outro])
    i = 0
    while words < target_words:
        extra = filler.model_copy(update={"heading": f"Going deeper, part {i + 1}"})
        scenes.insert(len(scenes) - 1, extra)
        words += len(extra.narration.split())
        i += 1
    scenes.append(outro)
    return scenes


def _short_scenes(topic: str, angle: str) -> list[Scene]:
    t = topic.rstrip(".").lower()
    if "mistake" in angle.lower():
        return [
            Scene(heading="Stop doing this", character="penny", pose="worry", illustration="warning",
                  narration=f"The most common mistake with {t}? Waiting until you feel ready."),
            Scene(heading="Why it hurts", character="max", pose="point", illustration="hourglass",
                  narration="Every year you wait is a year your money isn't working. And you can't buy "
                            "those years back later, no matter how much you earn."),
            Scene(heading="Waiting costs", character="max", pose="talk", illustration="scale",
                  narration="Starting ten years later can mean ending up with about half as much, even if "
                            "you save the exact same amount each month.",
                  chart=ChartSpec(kind="bar_compare", title="$200/month to age 65, hypothetical 7%", unit="$",
                                  labels=["Start at 25", "Start at 35"], values=[525_000, 244_000],
                                  source="Illustrative example")),
            Scene(heading="The fix", character="duo", pose="cheer", illustration="target",
                  narration="The fix is boring and it works. Pick a small amount you won't miss, automate it "
                            "today, and raise it a little every time you get a raise."),
            Scene(heading="Takeaway", character="max", pose="talk", illustration="lightbulb",
                  narration=f"Ready comes after you start, not before. {DISCLAIMER}"),
        ]
    return [
        Scene(heading="One number", character="penny", pose="cheer", illustration="hourglass",
              narration=f"Here's one number that makes {t} finally click."),
        Scene(heading="The math", character="max", pose="point", illustration="growth_arrow",
              narration="A hundred dollars a month at a hypothetical seven percent grows to over a hundred "
                        "and twenty thousand dollars in thirty years.",
              chart=ChartSpec(kind="compound_growth", title="$100/month, hypothetical 7%", unit="$",
                              params={"principal": 0, "rate": 0.07, "years": 30, "monthly": 100})),
        Scene(heading="The surprise", character="penny", pose="think", illustration="coin_stack",
              narration="You only put in thirty six thousand of that. The rest is growth earning growth, "
                        "and most of it shows up in the last ten years."),
        Scene(heading="Why it matters", character="max", pose="talk", illustration="calendar",
              narration="That's why time matters more than timing. The early years feel slow, but they set "
                        "up everything that comes later."),
        Scene(heading="Takeaway", character="max", pose="talk", illustration="target",
              narration=f"Start small, start now, and keep it automatic. {DISCLAIMER}"),
    ]


def generate_offline(topic: str, fmt: str, minutes: float | None = None, angle: str = "") -> Script:
    if fmt == "long":
        minutes = minutes or 2.0
        from .prompts import WORDS_PER_MINUTE

        scenes = _long_scenes(topic, int(minutes * WORDS_PER_MINUTE))
        title = f"{topic}: A Plain-English Guide"
    else:
        scenes = _short_scenes(topic, angle)
        title = (f"The #1 mistake with {topic.lower()}" if "mistake" in angle.lower()
                 else f"{topic}: one number that explains it")
    return Script(
        format=fmt, topic=topic, title=title[:90],
        description=(f"{topic}, explained simply with original animation.\n\n{DISCLAIMER}\n"
                     "Charts marked 'Illustrative example' use hypothetical numbers."),
        tags=["personal finance", "money", "investing basics", "GLIVARAO Finance"],
        thumbnail_text=" ".join(topic.split(":")[0].split()[:7]),
        hook=scenes[0].narration.split(".")[0],
        scenes=scenes,
    )
