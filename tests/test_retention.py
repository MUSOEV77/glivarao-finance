"""Hold US viewers: concrete hook in the first seconds (no intro), short sentences to 'you', an open loop or pattern
interrupt every 45-60 s in long videos, one clear action; Shorts: 2-second hook, loop line last. Checked by code
(paid scripts get one Claude rewrite, then the normal rejection + auto-retry); all fact rules unchanged."""
from glivarao.compliance import check_script, retention_issues
from glivarao.models import Scene, Script
from glivarao.scriptgen.prompts import SYSTEM_PROMPT, sponsor_prompt, user_prompt

DISC = "This video is for education only and isn't financial advice."
BEFORE = ("Welcome back to GLIVARAO, today we're going to talk about the Affordable Care Act and what open enrollment "
          "means for your family's health insurance.")
AFTER = "Miss December 15, and your Marketplace plan won't start on January 1."


def _s(fmt, scenes):
    return Script(format=fmt, topic="t", title="t", description="", thumbnail_text="",
                  scenes=[Scene(heading=f"s{i}", narration=t) for i, t in enumerate(scenes)])


def _long_body(loop_every_words):
    sents, since = [], 0
    for k in range(160):
        sents.append(f"You check the statement number {k} and keep the plan simple.")      # 11 words
        since += 11
        if loop_every_words and since >= loop_every_words:
            sents.append("But here's the part that's easy to miss.")
            since = 0
    return sents


def test_before_and_after_hook():
    bad = retention_issues(_s("long", [BEFORE, DISC]))
    assert any("intro" in i for i in bad) and any("first sentence has" in i for i in bad)
    good = retention_issues(_s("long", [AFTER + " " + " ".join(_long_body(110)[:20]), DISC]))
    assert not [i for i in good if "intro" in i or "first sentence" in i], good


def test_hook_must_be_concrete():
    vague = retention_issues(_s("long", ["Money is a tricky topic for everyone these days.", DISC]))
    assert any("not a hook" in i for i in vague)
    assert not [i for i in retention_issues(_s("short", ["You're paying 22.36% on that card.", DISC]))
                if "hook" in i]


def test_long_video_loop_gaps_are_a_warning_only():
    sents = _long_body(0)
    no_loops = _s("long", [AFTER] + [" ".join(sents[i:i + 10]) for i in range(0, len(sents), 10)] + [DISC])
    from glivarao.compliance import check_script, pacing_warnings

    assert not any("pattern interrupt" in i for i in retention_issues(no_loops))      # never a rejection
    assert pacing_warnings(no_loops)
    rep = check_script(no_loops, retention=True)
    assert any("PACING" in w for w in rep.warnings) and not any("pattern interrupt" in e for e in rep.errors)
    sents = _long_body(110)                                  # about every 42 s
    looped = _s("long", [AFTER] + [" ".join(sents[i:i + 10]) for i in range(0, len(sents), 10)] + [DISC])
    assert not pacing_warnings(looped)


def test_short_words_and_you():
    long_winded = ("You should know that the way most credit card companies calculate the interest you owe each month, "
                   "based on your average daily balance across the whole billing cycle, is complicated and costly.")
    issues = retention_issues(_s("long", [AFTER + " " + long_winded, DISC]))
    assert any("over 30 words" in i for i in issues)
    distant = retention_issues(_s("long", ["The rate is 22%. " + "Households often pay the minimum each month. " * 30,
                                           DISC]))
    assert any("talks to 'you'" in i for i in distant)


def test_shorts_hook_within_two_seconds():
    slow = retention_issues(_s("short", ["As of November 2026, the average rate on cards charged interest was 22.36% "
                                         "a year.", DISC]))
    assert any("max 10" in i for i in slow)


def test_errors_for_paid_scripts_warnings_for_templates():
    bad = _s("long", [BEFORE, DISC])
    assert any("Won't hold viewers" in e for e in check_script(bad, enforce_length=True, retention=True).errors)
    r = check_script(bad, enforce_length=False, retention=True)
    assert not any("Won't hold" in e for e in r.errors) and any("Won't hold" in w for w in r.warnings)


def test_prompts_carry_the_retention_rules_and_keep_the_fact_rules():
    for phrase in ("RETENTION", "FIRST sentence is the hook", "No intro", "every 45-60 seconds", "ONE clear action",
                   "loop line", "NUMBERS (strict"):
        assert phrase in SYSTEM_PROMPT, phrase
    assert "loop line" in user_prompt("t", "short", 0.8) and "open loop" in user_prompt("t", "long", 16)
    p = sponsor_prompt("{}", [], False, retention_issues=["opens with an intro"])
    assert "hold US viewers" in p and "opens with an intro" in p
