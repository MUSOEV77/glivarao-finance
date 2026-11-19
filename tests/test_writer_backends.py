"""Writer backends: Claude on Vertex AI (service-account JSON), automatic Gemini Pro fallback, shared Claude cap,
fallback alert. All HTTP and Google auth are simulated; no paid call is made."""
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


class FakeGeminiHTTP:
    def __init__(self, status=200):
        self.calls, self.status = [], status

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": __import__("json").dumps(SAMPLE)}]}}],
                "usageMetadata": {"promptTokenCount": 3000, "candidatesTokenCount": 4000}}
        return type("R", (), {"status_code": self.status, "json": lambda s: body})()


@pytest.fixture
def vs(settings, tmp_path):
    key = tmp_path / "secrets" / "vertex-sa.json"
    key.parent.mkdir()
    key.write_text("{}")
    return replace(settings, allow_paid_apis=True, writer="claude_vertex", vertex_project_id="proj-1",
                   vertex_credentials_file=str(key), gemini_api_key="GKEY",
                   claude_spend_ledger_path=str(tmp_path / "c.json"),
                   gemini_writer_ledger_path=str(tmp_path / "g.json"), db_path=tmp_path / "db.sqlite3")


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


def test_vertex_failure_falls_back_to_gemini_and_alerts_once(vs, monkeypatch):
    import anthropic

    monkeypatch.setattr(anthropic, "AnthropicVertex", lambda **kw: FakeVertex(stop="refusal"))
    monkeypatch.setattr(B, "vertex_credentials", lambda s: "CREDS")
    http = FakeGeminiHTTP()
    monkeypatch.setattr(B.requests, "Session", lambda: http)
    alerts = []
    monkeypatch.setattr("glivarao.publish.telegram.notify", lambda s, t: alerts.append(t))
    C.generate_with_claude("Credit card interest", "short", vs)
    C.generate_with_claude("Credit card interest", "short", vs)
    assert "Gemini gemini-3.1-pro-preview (fallback)" == C.LAST_WRITER["name"]
    c = http.calls[0]
    assert c["url"].endswith("/models/gemini-3.1-pro-preview:generateContent") and "GKEY" not in c["url"]
    assert c["json"]["generationConfig"]["responseMimeType"] == "application/json"
    assert len(alerts) == 1 and "Claude writer failed" in alerts[0]          # one alert per day


def test_missing_key_file_goes_straight_to_gemini(vs, monkeypatch, tmp_path):
    s = replace(vs, vertex_credentials_file=str(tmp_path / "nope.json"))
    http = FakeGeminiHTTP()
    monkeypatch.setattr(B.requests, "Session", lambda: http)
    monkeypatch.setattr("glivarao.publish.telegram.notify", lambda s, t: None)
    C.generate_with_claude("Credit card interest", "short", s)
    assert http.calls and "key not found" in C.LAST_WRITER["note"]


def test_gemini_writer_cap_and_both_failing(vs, monkeypatch, tmp_path):
    B.GeminiWriterLedger(tmp_path / "g.json").add(4.99, 0, 0)
    with pytest.raises(B.WriterUnavailable, match="Gemini writer monthly budget"):
        B.gemini_write(vs, "sys", "prompt", {}, "long", session=FakeGeminiHTTP())
    s = replace(vs, vertex_credentials_file=str(tmp_path / "nope.json"))
    monkeypatch.setattr("glivarao.publish.telegram.notify", lambda s, t: None)
    with pytest.raises(C.ScriptGenerationError, match="Gemini fallback failed"):
        C.generate_with_claude("Credit card interest", "long", s)


def test_key_file_errors_never_leak_contents(vs, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"private_key": "-----BEGIN PRIVATE KEY-----SECRET", "type": "service_account"}')
    with pytest.raises(B.WriterUnavailable) as e:
        B.vertex_credentials(replace(vs, vertex_credentials_file=str(bad)))
    assert "SECRET" not in str(e.value) and "PRIVATE" not in str(e.value)
