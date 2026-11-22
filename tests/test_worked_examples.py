"""Worked examples / calculations: allowed without their own URL when clearly labeled, the rate comes from a sourced
fact and GLIVARAO's calculators reproduce the numbers. Real-world statistics still need a source."""
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
