"""Production hardening: Claude spend guard + length revision, supervised daily runs, RAM-aware workers.
All Claude calls are simulated; no paid request is ever made."""
import json
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest

from glivarao.config import Settings
from glivarao.content.packaging import finalize_description
from glivarao.scriptgen.claude import (ClaudeSpendLedger, ScriptGenerationError, generate_with_claude,
                                       usage_cost)
from glivarao.scriptgen.prompts import SCRIPT_SCHEMA, normalize_direction
from glivarao.storage import JobStore
from glivarao import sysres

DISC = "This video is for education only and isn't financial advice."


def scene(words: int, last=False):
    text = " ".join(["money"] * words) + (" " + DISC if last else "")
    return {"heading": "A heading", "narration": text, "character": "max", "pose": "talk",
            "illustration": "coin_stack", "key_points": [], "set": "auto", "entrance": "auto",
            "transition": "iris", "money_fx": "auto",
            "chart": {"kind": "none", "title": "", "labels": [], "values": [], "unit": "",
                      "params": {"principal": 0, "rate": 0, "years": 0, "monthly": 0}, "source": ""}}


def script_json(n_scenes, words_each):
    return json.dumps({"title": "Credit Card Interest, Explained", "description": "Plain-English summary.\n\nMore.",
                       "tags": ["credit"], "thumbnail_text": "Pay More", "hook": "",
                       "scenes": [scene(words_each, i == n_scenes - 1) for i in range(n_scenes)]})


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class FakeClaude:
    """Mimics client.beta.messages.stream(...) and records each request."""

    def __init__(self, replies, out_tokens=8000):
        self.replies, self.calls, self.out_tokens = list(replies), [], out_tokens
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kw):
        self.calls.append(kw)
        text = self.replies.pop(0)
        usage = SimpleNamespace(input_tokens=3000, output_tokens=self.out_tokens, cache_creation_input_tokens=0,
                                cache_read_input_tokens=0)
        return FakeStream(SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)],
                                          usage=usage))


def settings(tmp_path, **kw):
    return Settings(allow_paid_apis=True, anthropic_api_key="x", claude_spend_ledger_path=str(tmp_path / "c.json"),
                    writer="claude_api", gemini_api_key="", db_path=tmp_path / "db.sqlite3",
                    **kw)


def test_short_draft_is_revised_not_discarded_and_spend_recorded(tmp_path):
    s = settings(tmp_path)
    fake = FakeClaude([script_json(20, 60), script_json(25, 112)])  # 1200 words -> 2800 words
    out = generate_with_claude("Credit card interest", "long", s, client=fake)
    assert 2550 <= out.word_count <= 3100
    assert len(fake.calls) == 2 and "Expand it" in fake.calls[1]["messages"][0]["content"]
    req = fake.calls[0]
    assert req["model"] == "claude-opus-5-5" and req["fallbacks"] == "default"
    assert req["output_config"]["format"]["schema"] is SCRIPT_SCHEMA
    led = json.loads((tmp_path / "c.json").read_text())
    row = led[date.today().strftime("%Y-%m")]
    assert row["requests"] == 2 and row["usd"] == pytest.approx(2 * (3000 * 4 + 8000 * 20) / 1e6)
    assert out.scenes[0].set is None and out.scenes[0].transition == "iris"  # "auto" -> director decides


def test_in_range_draft_needs_one_request(tmp_path):
    fake = FakeClaude([script_json(25, 112)])
    generate_with_claude("t", "long", settings(tmp_path), client=fake)
    assert len(fake.calls) == 1


def test_budget_blocks_request_before_any_call(tmp_path):
    s = settings(tmp_path, claude_monthly_budget_usd=1.0)
    ClaudeSpendLedger(tmp_path / "c.json").add(0.9, 0, 0)
    fake = FakeClaude([script_json(25, 112)])
    with pytest.raises(ScriptGenerationError, match="Claude monthly budget"):  # no Gemini key: nothing else to use
        generate_with_claude("t", "long", s, client=fake)
    assert fake.calls == []


def test_revision_skipped_when_budget_runs_out(tmp_path):
    s = settings(tmp_path, claude_monthly_budget_usd=0.8)  # first call fits, second does not
    fake = FakeClaude([script_json(20, 60), script_json(25, 112)], out_tokens=30000)
    out = generate_with_claude("t", "long", s, client=fake)
    assert len(fake.calls) == 1 and out.word_count < 2550  # draft kept, compliance will flag length


def test_usage_cost_counts_cache_tokens():
    u = SimpleNamespace(input_tokens=1000, cache_creation_input_tokens=1000, cache_read_input_tokens=10000,
                        output_tokens=1000)
    usd, tin, tout = usage_cost(u, 4, 20)
    assert usd == pytest.approx((1000 + 1250 + 1000) * 4 / 1e6 + 1000 * 20 / 1e6) and tin == 12000


def test_schema_direction_fields_required_and_normalized():
    props = SCRIPT_SCHEMA["properties"]["scenes"]["items"]
    assert {"set", "entrance", "transition", "money_fx"} <= set(props["required"])
    assert normalize_direction({"set": "auto", "heading": "auto"}) == {"set": None, "heading": "auto"}


def test_chapters_added_to_description_without_placeholder():
    d = finalize_description("Summary line.\n\nSources:\n- X", ["Intro", "Middle", "End"], [0, 40, 95], True)
    assert d.startswith("Summary line.\n\nChapters:\n0:00 Intro\n0:40 Middle\n1:35 End")
    assert "Sources:" in d


def test_safe_workers_caps_by_ram(monkeypatch):
    monkeypatch.setattr(sysres, "available_mb", lambda: 2400)
    monkeypatch.setattr(sysres.os, "cpu_count", lambda: 8)
    monkeypatch.delenv("RENDER_WORKERS", raising=False)
    assert sysres.safe_workers() == 2           # (2400 - 400) // 1000
    assert sysres.safe_workers(1) == 1
    monkeypatch.setattr(sysres, "available_mb", lambda: 300)
    assert sysres.safe_workers() == 1           # never below 1
    monkeypatch.setattr(sysres, "available_mb", lambda: 64000)
    monkeypatch.setenv("RENDER_WORKERS", "3")
    assert sysres.safe_workers() == 3


def _patch_run(monkeypatch, fn):
    import glivarao.daily_v2 as d

    monkeypatch.setattr(d, "run_daily_v2", fn)
    return d


def test_supervised_retries_then_alerts(tmp_path, monkeypatch):
    calls, alerts = [], []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("research outage")

    d = _patch_run(monkeypatch, boom)
    s = Settings(output_dir=tmp_path / "out", db_path=tmp_path / "db.sqlite3")
    store = JobStore(s.db_path)
    with pytest.raises(RuntimeError):
        d.supervised_daily(s, store, today=date(2026, 11, 18), retries=1, retry_delay=0,
                           notifier=lambda st, t: alerts.append(t))
    assert len(calls) == 2 and "FAILED" in alerts[0] and "research outage" in alerts[0]


def test_supervised_is_idempotent_and_reports_bad_jobs(tmp_path, monkeypatch):
    runs, alerts = [], []

    def ok(*a, **k):
        runs.append(1)
        from glivarao.daily_v2 import DailyResult

        r = DailyResult("Topic", "free")
        r.jobs = [("j1", "long", "pending_approval", "v.mp4", ""), ("j2", "short", "failed", None, "oom")]
        return r

    d = _patch_run(monkeypatch, ok)
    s = Settings(output_dir=tmp_path / "out", db_path=tmp_path / "db.sqlite3")
    store = JobStore(s.db_path)
    note = lambda st, t: alerts.append(t)  # noqa: E731
    assert d.supervised_daily(s, store, today=date(2026, 11, 18), notifier=note) is not None
    assert d.supervised_daily(s, store, today=date(2026, 11, 18), notifier=note) is None  # already done
    assert len(runs) == 1 and "j2" in alerts[0] and "oom" in alerts[0]
    d.supervised_daily(s, store, today=date(2026, 11, 18), force=True, notifier=note)
    assert len(runs) == 2


def test_supervised_single_instance_lock(tmp_path, monkeypatch):
    import fcntl

    d = _patch_run(monkeypatch, lambda *a, **k: None)
    s = Settings(output_dir=tmp_path / "out", db_path=tmp_path / "db.sqlite3")
    lock = tmp_path / "daily.lock"
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        with pytest.raises(d.AlreadyRunning):
            d.supervised_daily(s, JobStore(s.db_path), lock_path=lock)


def test_disk_check(tmp_path, monkeypatch):
    monkeypatch.setattr(sysres, "free_disk_mb", lambda p: 100)
    with pytest.raises(RuntimeError, match="MB free"):
        sysres.check_disk(tmp_path)
