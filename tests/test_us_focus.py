"""US-only rule: macro topics allowed, other countries rejected; sponsor-friendly language; closing "What to do"
section; [AFFILIATE: category] placeholders in descriptions (no real links)."""
from glivarao.compliance import check_script, has_what_to_do, sponsor_issues
from glivarao.research.finance_filter import gate, market_of, match_concepts
from glivarao.scriptgen.offline import generate_offline
from glivarao.scriptgen.prompts import SYSTEM_PROMPT
from glivarao.studio import affiliates, pillars


def test_us_macro_topics_fit_the_economy_pillar_and_other_countries_are_rejected():
    for text, key in [("Federal Reserve rate cut", "fed_rates"), ("housing market and mortgage rates", "us_housing"),
                      ("stock market correction", "us_stock_market"), ("national debt hits record", "national_debt"),
                      ("recession and layoffs", "recession"), ("medical debt on credit reports", "medical_debt")]:
        assert gate(text)[0], text
        keys = [c.key for c in match_concepts(text)]
        assert key in keys and pillars.pillar_of(key) is not None, (text, keys)
    assert not gate("Tariffs and the trade war")[0]                       # trade politics: still out
    assert market_of("pension rules in the united-kingdom", []) == "other"
    assert pillars.rejection({"key": "credit_card", "market": "CA"}) == "not a US household topic (US-only channel)"
    assert pillars.rejection({"key": "tfsa", "market": "CA"})


def test_system_prompt_carries_the_us_only_sponsor_and_what_to_do_rules():
    for phrase in ("US-ONLY", "US household", "No profanity", "No political sides", "No panic",
                   '"What to do"', "high-yield savings account", "credit monitoring"):
        assert phrase in SYSTEM_PROMPT, phrase


def test_sponsor_check_catches_profanity_panic_and_political_sides():
    s = generate_offline("Credit card interest", "long")
    assert sponsor_issues(s) == []
    scenes = list(s.scenes)
    scenes[1] = scenes[1].model_copy(update={"narration": scenes[1].narration + " This damn rate is brutal. The "
                                             "crash is coming, so act before it's too late. Republicans did this."})
    bad = s.model_copy(update={"scenes": scenes})
    issues = " | ".join(sponsor_issues(bad))
    assert "profanity: 'damn'" in issues and "crash is coming" in issues and "too late" in issues
    assert "political side: 'Republicans'" in issues
    assert any("sponsor-friendly" in e for e in check_script(bad, enforce_length=False).errors)
    calm = s.model_copy(update={"title": "Don't panic: a calm plan for your credit card"})
    assert sponsor_issues(calm) == []                                     # calm advice is fine


def test_long_videos_need_a_what_to_do_section():
    s = generate_offline("Credit card interest", "long")
    scenes = [sc.model_copy(update={"heading": "Recap"}) for sc in s.scenes]
    no_plan = s.model_copy(update={"scenes": scenes})
    assert not has_what_to_do(no_plan)
    assert any("What to do" in e for e in check_script(no_plan, enforce_length=True).errors)
    scenes[-2] = scenes[-2].model_copy(update={"heading": "What to do this week"})
    assert has_what_to_do(s.model_copy(update={"scenes": scenes}))


def test_affiliate_placeholder_per_category_and_no_links():
    assert affiliates.category_for("credit_card") == "debt payoff"
    assert affiliates.category_for("credit_score") == "credit monitoring"
    assert affiliates.category_for("fed_rates") == "high-yield savings"
    assert affiliates.category_for("tax_filing") == "tax software"
    assert affiliates.category_for("aca_marketplace") == "insurance"
    assert affiliates.category_for("bnpl") == "budgeting app"
    assert affiliates.category_for("credit_card", {"affiliate_category": "insurance"}) == "insurance"
    d = affiliates.add_placeholder("Summary.", "debt payoff")
    assert "[AFFILIATE: debt payoff]" in d and "http" not in d
    assert affiliates.add_placeholder(d, "debt payoff") == d              # once only
