"""Cost cuts: at most 1 rewrite per video, rewrites on the cheaper Claude model, production stops at 80% of the
Claude budget; health shows the weekly pace, the next batch part and cost per video."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from glivarao.scriptgen import claude as C
from glivarao.studio import costs


@pytest.fixture
def s(settings, tmp_path):
    return replace(settings, writer="claude_openrouter", openrouter_api_key="k", allow_paid_apis=True,
                   claude_spend_ledger_path=str(tmp_path / "c.json"), pace_mode="weekly")


def test_one_rewrite_per_video_then_the_draft_is_kept(s, monkeypatch):
    models = []

    def fake_chat(settings, system, prompt, max_tokens, schema=None, effort=None, session=None, model=None, **k):
        models.append(model or settings.openrouter_model)
        return "{}", {"prompt_tokens": 100, "completion_tokens": 100, "cost": 0.01}

    monkeypatch.setattr("glivarao.scriptgen.backends.openrouter_chat", fake_chat)
    monkeypatch.setattr(C, "_parse_json", lambda t: {})
    with costs.tag("draft:long:x"):
        C._ask(s, "write", "long")                          # the draft
        C._ask_rewrite(s, "fix it", "long")            # its one rewrite (cheaper model)
        with pytest.raises(C.RewriteBudgetReached):
            C._ask_rewrite(s, "fix again", "long")     # no second rewrite: nothing spent
    assert models == ["anthropic/claude-sonnet-5.5", "anthropic/claude-haiku-5.5"]


def test_production_stops_at_80_percent_of_the_claude_budget(s):
    ledger = C.ClaudeSpendLedger(Path(s.claude_spend_ledger_path))
    ledger.add(s.claude_monthly_budget_usd * 0.8, 0, 0)
    with pytest.raises(C.ClaudeBudgetExceeded, match="80%"):
        C._check_budget(s, ledger, 40000, "long", 2.0, 10.0)


def test_health_shows_weekly_pace_and_the_next_batch_part(s, store):
    from glivarao.studio import health
    from glivarao.studio.queue import TopicQueue

    store.kv_set("batch_mode", "on")
    q = TopicQueue(store)
    it = q.add_proposals([{"key": "aca_marketplace", "topic": "ACA 2027: subsidy cliff", "category": "x",
                           "market": "US", "score": 1, "why": []}], __import__("datetime").date(2026, 11, 20))[0]
    q.update(it.id, status="awaiting_input")
    text = health.report(s, store)
    assert "PACE (week of" in text and "/4" in text and "/21" in text and "due by now" not in text
    assert "NEXT\nACA Open Enrollment" in text or "Part 1" in text
    assert "subsidy cliff" not in text.split("NEXT")[1].split("\n\n")[0]


def test_old_non_batch_item_is_set_aside_for_the_batch_part(s, store, monkeypatch):
    from glivarao.studio import launch_plan, planner
    from glivarao.studio.queue import TopicQueue

    store.kv_set("batch_mode", "on")
    monkeypatch.setattr(launch_plan, "verify_fact_list", lambda facts, session=None: (facts, []))
    q = TopicQueue(store)
    old = q.add_proposals([{"key": "aca_marketplace", "topic": "ACA 2027: subsidy cliff", "category": "x",
                            "market": "US", "score": 1, "why": []}], __import__("datetime").date(2026, 11, 20))[0]
    q.update(old.id, status="awaiting_input")
    item = planner.plan_next(s, store, __import__("datetime").date(2026, 11, 25), send=False)
    assert item.card.get("batch") and q.get(old.id).status == "skipped"
