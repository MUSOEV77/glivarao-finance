"""Writer backends: Claude through OpenRouter (default), Claude on Vertex AI (optional), shared $30 Claude cap,
Claude only (no other writer: any failure holds production). All HTTP and Google auth are simulated; no paid call."""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from glivarao.scriptgen import backends as B
from glivarao.scriptgen import claude as C
from glivarao.scriptgen.offline import generate_offline

SAMPLE = generate_offline("Credit card interest", "short").model_dump(exclude={"format", "topic"})


class FakeStream:
    def __init__(self, stop="end_turn"):
        self.stop = stop

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return SimpleNamespace(stop_reason=self.stop, stop_details=None,
                               content=[SimpleNamespace(type="text", text=json.dumps(SAMPLE))],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=2000))


class FakeVertex:
    def __init__(self, stop="end_turn", **kw):
        self.kw, self.calls, self.stop = kw, [], stop
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kw):
        self.calls.append(kw)
        return FakeStream(self.stop)


class FakeOpenRouter:
    """Replays OpenRouter answers: each item is an HTTP status or a dict of overrides for a 200 answer."""

    def __init__(self, *answers):
        self.calls, self.answers = [], list(answers) or [{}]

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, int):
            body = {"error": {"message": "nope KEY-SECRET"}}
            return type("R", (), {"status_code": a, "json": lambda s: body})()
        body = {"model": "anthropic/claude-sonnet-5.5",
                "choices": [{"finish_reason": "stop", "message": {"content": __import__("json").dumps(SAMPLE)}}],
                "usage": {"prompt_tokens": 3000, "completion_tokens": 5000, "cost": 0.056}}
        body.update(a)
        return type("R", (), {"status_code": 200, "json": lambda s: body})()


@pytest.fixture
def ors(settings, tmp_path):
    return replace(settings, allow_paid_apis=True, writer="claude_openrouter", openrouter_api_key="KEY-SECRET",
                   claude_spend_ledger_path=str(tmp_path / "c.json"), db_path=tmp_path / "db.sqlite3")


def test_openrouter_is_the_default_writer(monkeypatch):
    from glivarao.config import Settings

    monkeypatch.delenv("WRITER", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    st = Settings()
    assert st.writer == "claude_openrouter" and st.openrouter_model == "anthropic/claude-sonnet-5.5"
    assert st.claude_monthly_budget_usd == 30 and st.fps == 24


def test_openrouter_request_shape_cost_and_claude_only(ors, tmp_path):
    from glivarao.scriptgen.prompts import SCRIPT_SCHEMA, SYSTEM_PROMPT

    http = FakeOpenRouter()
    script = C.generate_with_claude("Credit card interest", "short", ors, client=http)
    c = http.calls[0]
    assert c["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert c["headers"]["Authorization"] == "Bearer KEY-SECRET" and "KEY-SECRET" not in json.dumps(c["json"])
    body = c["json"]
    assert body["model"] == "anthropic/claude-sonnet-5.5" and "models" not in body          # never another model
    assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}             # same prompts
    assert body["response_format"]["json_schema"]["schema"] == SCRIPT_SCHEMA               # structured output
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["provider"]["require_parameters"] is True and body["reasoning"] == {"effort": "high"}
    assert script.format == "short" and C.LAST_WRITER["name"] == "Claude anthropic/claude-sonnet-5.5 (OpenRouter)"
    assert C.ClaudeSpendLedger(tmp_path / "c.json").spent() == pytest.approx(0.056)       # OpenRouter's real cost


def test_openrouter_cost_from_list_price_when_not_reported(ors, tmp_path):
    http = FakeOpenRouter({"usage": {"prompt_tokens": 1000, "completion_tokens": 2000}})
    C.generate_with_claude("Credit card interest", "short", ors, client=http)
    assert C.ClaudeSpendLedger(tmp_path / "c.json").spent() == pytest.approx(1000 * 2 / 1e6 + 2000 * 10 / 1e6)


def test_openrouter_retries_429_then_succeeds(ors, monkeypatch):
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    http = FakeOpenRouter(429, 503, {})
    text, u = B.openrouter_chat(ors, "s", "p", 100, session=http, sleep=lambda s: None)
    assert len(http.calls) == 3 and u["cost"] == 0.056


@pytest.mark.parametrize("answer,why", [(402, "credits"), (401, "invalid"), (404, "model not found"),
                                        ({"model": "openai/gpt-9"}, "not Claude"),
                                        ({"choices": [{"finish_reason": "length", "message": {"content": "{"}}]},
                                         "truncated"),
                                        ({"choices": [{"finish_reason": "stop", "message": {"content": "",
                                                                                            "refusal": "no"}}]},
                                         "declined")])
def test_openrouter_failures_hold_production_and_never_leak_the_key(ors, answer, why):
    with pytest.raises(C.ClaudeUnavailable) as e:
        C.generate_with_claude("Credit card interest", "short", ors, client=FakeOpenRouter(answer))
    assert why in str(e.value) and "KEY-SECRET" not in str(e.value)


def test_openrouter_monthly_cap_blocks_before_any_call(ors, tmp_path):
    C.ClaudeSpendLedger(tmp_path / "c.json").add(29.99, 0, 0)
    http = FakeOpenRouter()
    with pytest.raises(C.ClaudeUnavailable, match="monthly budget"):
        C.generate_with_claude("Credit card interest", "long", ors, client=http)
    assert http.calls == []


def test_non_claude_openrouter_model_is_refused(ors):
    with pytest.raises(C.ClaudeUnavailable, match="not a Claude model"):
        C.generate_with_claude("x", "short", replace(ors, openrouter_model="google/gemini-3-pro"),
                               client=FakeOpenRouter())


def test_doctor_live_makes_one_tiny_openrouter_call(ors, tmp_path, capsys):
    from glivarao import doctor

    http = FakeOpenRouter({"choices": [{"finish_reason": "stop", "message": {"content": "OK"}}],
                           "usage": {"prompt_tokens": 12, "completion_tokens": 2, "cost": 0.00004}})
    http.get = lambda url, headers=None, timeout=None: type("R", (), {
        "status_code": 200, "json": lambda s: {"data": {"usage": 1.25, "limit_remaining": None}}})()
    r = doctor.Report()
    doctor.openrouter_live(ors, r, http)
    out = capsys.readouterr().out
    assert len(http.calls) == 1 and http.calls[0]["json"]["max_tokens"] == 16
    assert "answered 'OK'" in out and not r.todo and "KEY-SECRET" not in out
    assert C.ClaudeSpendLedger(tmp_path / "c.json").spent() == pytest.approx(0.00004)


@pytest.fixture
def vs(settings, tmp_path):
    key = tmp_path / "secrets" / "vertex-sa.json"
    key.parent.mkdir()
    key.write_text("{}")
    return replace(settings, allow_paid_apis=True, writer="claude_vertex", vertex_project_id="proj-1",
                   vertex_credentials_file=str(key), gemini_api_key="GKEY",
                   claude_spend_ledger_path=str(tmp_path / "c.json"), db_path=tmp_path / "db.sqlite3")


def test_vertex_backend_request_shape_and_price(vs, monkeypatch, tmp_path):
    made = {}

    def fake_vertex(**kw):
        made.update(kw)
        made["client"] = FakeVertex()
        return made["client"]

    import anthropic

    monkeypatch.setattr(anthropic, "AnthropicVertex", fake_vertex)
    monkeypatch.setattr(B, "vertex_credentials", lambda s: "CREDS")
    script = C.generate_with_claude("Credit card interest", "short", vs)
    assert made["project_id"] == "proj-1" and made["region"] == "global" and made["credentials"] == "CREDS"
    call = made["client"].calls[0]
    assert call["model"] == "claude-sonnet-5-5" and "betas" not in call and "fallbacks" not in call
    assert call["output_config"]["format"]["type"] == "json_schema" and "temperature" not in call
    assert script.format == "short" and "Vertex AI" in C.LAST_WRITER["name"]
    spent = C.ClaudeSpendLedger(tmp_path / "c.json").spent()
    assert spent == pytest.approx(1000 * 2 / 1e6 + 2000 * 10 / 1e6)     # Sonnet 5.5 rates, shared Claude cap


def test_vertex_refusal_or_missing_key_holds_never_another_writer(vs, monkeypatch, tmp_path):
    import anthropic

    monkeypatch.setattr(anthropic, "AnthropicVertex", lambda **kw: FakeVertex(stop="refusal"))
    monkeypatch.setattr(B.requests, "Session", lambda: pytest.fail("no HTTP writer may be called"))
    real_creds = B.vertex_credentials
    monkeypatch.setattr(B, "vertex_credentials", lambda s: "CREDS")
    with pytest.raises(C.ClaudeUnavailable, match="declined"):
        C.generate_with_claude("Credit card interest", "short", vs)
    monkeypatch.setattr(B, "vertex_credentials", real_creds)
    with pytest.raises(C.ClaudeUnavailable, match="key not found"):
        C.generate_with_claude("Credit card interest", "short",
                               replace(vs, vertex_credentials_file=str(tmp_path / "nope.json")))
    assert not hasattr(B, "gemini_write")                                   # the Gemini writer is gone


def test_key_file_errors_never_leak_contents(vs, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"private_key": "-----BEGIN PRIVATE KEY-----SECRET", "type": "service_account"}')
    with pytest.raises(B.WriterUnavailable) as e:
        B.vertex_credentials(replace(vs, vertex_credentials_file=str(bad)))
    assert "SECRET" not in str(e.value) and "PRIVATE" not in str(e.value)
