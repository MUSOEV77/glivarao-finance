"""Worked examples / calculations: allowed without their own URL when clearly labeled, the rate comes from a sourced
fact and GLIVARAO's calculators reproduce the numbers. Real-world statistics still need a source."""
import pytest
from dataclasses import replace
from datetime import date

from glivarao.content import calculators as calc
from glivarao.content.brief import build_brief
from glivarao.models import ChartSpec, Scene, Script
from glivarao.studio import factcheck, launch_plan


def _brief():
    v = launch_plan.LAUNCH[0]                       # credit card debt: has the Fed G.19 card rate (22.36%)
    return build_brief(replace(v).card(), date(2026, 11, 22))


def _script(scene):
    end = Scene(heading="What to do", narration="This video is for education only and isn't financial advice.")
    return Script(format="short", topic="t", title="t", description="", thumbnail_text="", scenes=[scene, end])


def test_card_example_uses_the_sourced_rate():
    b = _brief()
    assert b.calcs["minimum"].inputs["apr"] == 0.2236
    assert any("22.36%" in f.text and "federalreserve.gov" in f.text for f in b.facts if f.kind == "EDITORIAL")


def test_labeled_example_chart_with_checked_math_passes_without_its_own_url():
    b = _brief()
    mp, fx = calc.minimum_payment_payoff(5000, 0.2236), calc.fixed_payment_payoff(5000, 0.2236, 200)
    sc = Scene(heading="The real cost", narration="Here is an example.",
               chart=ChartSpec(kind="bar_compare", title="Total interest on $5,000 (example)",
                               labels=["Minimum only", "$200 a month"],
                               values=[round(mp.results["total_interest"]), round(fx.results["total_interest"])],
                               source="Illustrative example"))
    claims = factcheck.check_claims(_script(sc), b)
    chart = next(c for c in claims if c.text.startswith("Chart:"))
    assert chart.status == "calculation" and chart.url and not factcheck.needs_source(claims)


def test_if_you_owe_sentence_is_checked_against_the_calculators():
    b = _brief()
    fx = calc.fixed_payment_payoff(5000, 0.2236, 200)
    good = (f"If you owe $5,000 at 22.36% and pay $200 a month, you'd pay about "
            f"${round(fx.results['total_interest']):,} in interest.")
    sc = Scene(heading="Example", narration=good)
    claims = factcheck.check_claims(_script(sc), b)
    assert claims[0].status in ("calculation", "source") and claims[0].url      # the brief's own checked example
    f3 = calc.fixed_payment_payoff(3000, 0.2236, 150)                            # an amount the brief doesn't have
    other = (f"For example, if you owe $3,000 at 22.36% and pay $150 a month, you'd pay about "
             f"${round(f3.results['total_interest']):,} in interest.")
    claims = factcheck.check_claims(_script(Scene(heading="Example", narration=other)), b)
    assert claims[0].status == "calculation" and "math checked" in claims[0].source and claims[0].url


def test_wrong_math_and_real_world_statistics_still_need_a_source():
    b = _brief()
    wrong = Scene(heading="Example", narration="If you owe $5,000 at 22.36%, you'd pay $9,999 in interest.",
                  chart=ChartSpec(kind="bar_compare", title="Total interest on $5,000 (example)", labels=["a", "b"],
                                  values=[1234, 4321], source="Illustrative example"))
    stat = Scene(heading="Stat", narration="Americans owe $987 billion on store cards.")
    for sc in (wrong, stat):
        assert factcheck.needs_source(factcheck.check_claims(_script(sc), b)), sc.narration


def _aca_brief():
    v = launch_plan.LAUNCH[1]                       # ACA deadline: fact library adds the HHS poverty guidelines
    assert v.key == "aca_marketplace"
    return build_brief(v.card(), date(2026, 11, 22))


def test_aca_rejections_from_the_daily_run_now_pass():
    b = _aca_brief()
    assert any("15,960" in f.text and "aspe.hhs.gov" in f.url for f in b.facts)
    fpl = Scene(heading="The income line", narration="The poverty guideline depends on household size.",
                chart=ChartSpec(kind="bar_compare", title="2026 federal poverty guideline", labels=["1", "2", "3", "4"],
                                values=[15960, 21640, 27320, 33000], source="HHS poverty guidelines (ASPE)"))
    line = Scene(heading="Premium tax credit line", narration="You qualify up to 400% of the poverty level.",
                 chart=ChartSpec(kind="bar_compare", title="Income line for premium tax credits",
                                 labels=["1 person", "family of 4"], values=[63840, 132000], source="HealthCare.gov"))
    plans = Scene(heading="Compare plans", narration="Say, for example, two plans differ by $50 a month. Over a year, "
                                                    "that's $600.")
    for sc in (fpl, line, plans):
        claims = factcheck.check_claims(_script(sc), b)
        assert not factcheck.needs_source(claims), [(c.text, c.status) for c in claims]


def test_charts_not_built_from_the_fact_sheet_are_removed_not_rejected():
    b = _aca_brief()
    bad = Scene(heading="Premiums", narration="Premiums vary a lot by plan.",
                chart=ChartSpec(kind="bar_compare", title="Average premium by plan", labels=["Bronze", "Gold"],
                                values=[411, 637], source="Claude"))
    s, dropped = factcheck.sanitize_charts(_script(bad), b)
    assert dropped == ["Average premium by plan"] and s.scenes[0].chart.kind == "none"
    assert not factcheck.needs_source(factcheck.check_claims(s, b))
    stat = Scene(heading="Stat", narration="About 21 million people enrolled last year.")
    assert factcheck.needs_source(factcheck.check_claims(_script(stat), b))     # real statistic: still needs a source


@pytest.mark.parametrize("n,text,ok", [
    (1, "At 22.36%, a $5,000 balance costs about $1,118 a year in interest. That's about $93 a month.", True),
    (1, "Americans owe about $1.4 trillion in revolving credit.", True),
    (1, "The average card rate is about 22%.", True),
    (1, "If you owe $5,000 at 22.36%, you'd pay $9,999 in interest.", False),
    (1, "Americans owe $987 billion on store cards.", False),
    (2, "The poverty line is $15,960 for one person. 400% of that is $63,840.", True),
    (2, "Say, with made-up numbers, two plans differ by $50 a month. Over a year, that's $600.", True),
    (2, "Say you spend $40 a week on takeout. That's $2,080 a year.", True),
    (2, "About 21 million people signed up.", False),
])
def test_how_claude_paraphrases_are_judged(n, text, ok):
    b = build_brief(launch_plan.LAUNCH[n - 1].card(), date(2026, 11, 22))
    claims = factcheck.check_claims(_script(Scene(heading="h", narration=text)), b)
    assert (not factcheck.needs_source(claims)) is ok, [(c.text, c.status) for c in claims]
