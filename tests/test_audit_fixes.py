"""Audit fixes: Telegram retries, reviews never lost on a Telegram error, tolerant polling with backoff, doctor
(--live with simulated APIs), update/reboot scripts."""
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from glivarao.publish import telegram as T


class Resp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def json(self):
        return self._b


class FlakyHTTP:
    def __init__(self, bodies):
        self.bodies, self.calls = list(bodies), 0

    def post(self, url, **kw):
        self.calls += 1
        b = self.bodies.pop(0)
        if isinstance(b, Exception):
            raise b
        return Resp(b)


def test_telegram_retries_flood_control_and_network_errors(monkeypatch):
    import requests

    monkeypatch.setattr("time.sleep", lambda s: None)
    http = FlakyHTTP([requests.ConnectionError("x"), {"ok": False, "error_code": 429, "parameters": {"retry_after": 3}},
                      {"ok": True, "result": {"message_id": 7}}])
    c = T.TelegramClient("123:ABC", session=http)
    assert c.call("sendMessage", chat_id=1, text="hi") == {"message_id": 7} and http.calls == 3
    bad = T.TelegramClient("123:ABC", session=FlakyHTTP([{"ok": False, "error_code": 400, "description": "chat not found"}]))
    with pytest.raises(T.TelegramError, match="chat not found") as e:
        bad.call("sendMessage", chat_id=1, text="hi")
    assert "123:ABC" not in str(e.value)


def test_poll_backs_off_instead_of_failing(settings, store, monkeypatch, capsys):
    from glivarao import __main__ as cli

    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42")
    monkeypatch.setattr(cli, "get_settings", lambda: s)

    def boom(*a, **k):
        raise T.TelegramError("getUpdates failed: ConnectionError")

    monkeypatch.setattr(T, "poll_decisions", boom)
    cli.main(["poll-approvals"])                      # no exception -> the systemd unit never fails
    st = json.loads(store.kv_get("poll_backoff"))
    assert st["fails"] == 1 and "retry in 5 min" in capsys.readouterr().out
    cli.main(["poll-approvals"])
    assert "backing off" in capsys.readouterr().out
    monkeypatch.setattr(T, "poll_decisions", lambda *a, **k: [])
    store.kv_set("poll_backoff", json.dumps({"fails": 1, "next": 0}))
    cli.main(["poll-approvals"])
    assert json.loads(store.kv_get("poll_backoff"))["fails"] == 0


class FakeAPIs:
    """Simulated Google + Telegram endpoints for doctor --live."""

    def __init__(self):
        self.urls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.urls.append(url)
        if "generativelanguage" in url and url.endswith("/models"):
            return Resp({"models": [{"name": "models/gemini-3.1-pro-preview", "supportedGenerationMethods":
                                     ["generateContent"]}]})
        return Resp({}, 200)

    def post(self, url, **kw):
        self.urls.append(url)
        return Resp({"candidates": [{"content": {"parts": [{"text": "OK"}]}}]})


def test_doctor_lists_every_setting_and_runs_live_checks(settings, store, capsys, tmp_path, monkeypatch):
    from glivarao import doctor

    s = replace(settings, allow_paid_apis=True, gemini_api_key="AIza" + "x" * 35, youtube_api_key="bad-key",
                writer="claude_vertex", vertex_project_id="proj-abc-1", vertex_credentials_file=str(tmp_path / "k.json"))
    r = doctor.run(s, store, live=True, session=FakeAPIs())
    out = capsys.readouterr().out
    assert "[MISSING] TELEGRAM_BOT_TOKEN" in out and "[  ok   ] GEMINI_API_KEY" in out
    assert "[INVALID] YOUTUBE_API_KEY" in out and "[MISSING] Vertex service-account key" in out
    assert "AI Studio spend limit" in out and "Gemini test answer (voice)" in out and "writer rule" in out and "Claude only" in out
    assert "gemini-3.1-pro-preview" not in out                     # the Gemini writer is off: not even tested
    assert "x" * 35 not in out                                   # key values are never printed
    assert not r.broken
    with pytest.raises(SystemExit):
        doctor.run(replace(s, youtube_publish_enabled=True), store, strict=True)


def test_scripts_are_valid_bash():
    for f in Path("deploy").glob("*.sh"):
        subprocess.run(["bash", "-n", str(f)], check=True)
    up = Path("deploy/update.sh").read_text()
    assert ".deployed_commit" in up and "git reset -q --hard FETCH_HEAD" in up   # compares the INSTALLED version
    assert ".deployed_commit" in Path("deploy/install.sh").read_text()
    poll = Path("deploy/systemd/glivarao-poll.service").read_text()
    assert "StartLimitIntervalSec=0" in poll and "Restart=" not in poll


def test_aq_keys_valid_and_402_body_printed(settings, store, capsys):
    from glivarao import doctor

    class Pay402(FakeAPIs):
        def post(self, url, **kw):
            return Resp({"error": {"code": 402, "status": "RESOURCE_EXHAUSTED",
                                   "message": "Your prepayment credits are depleted."}}, 402)

    key = "AQ.Ab8RN6" + "k" * 44                                   # new AI Studio key format, 53 chars
    s = replace(settings, allow_paid_apis=True, gemini_api_key=key, writer="free")
    doctor.run(s, store, live=True, session=Pay402())
    out = capsys.readouterr().out
    assert "[  ok   ] GEMINI_API_KEY" in out and key not in out
    assert "HTTP 402: prepay balance is empty" in out and "prepayment credits are depleted" in out


def test_voice_402_is_not_retried(tmp_path):
    from glivarao.tts.gemini_tts import GeminiTTSNarrator, SpendLedger
    from glivarao.tts.voice_lock import VoiceUnavailable
    from tests.test_gemini_voice import FakeGemini

    g = FakeGemini(status=402)
    n = GeminiTTSNarrator("K", cache_dir=tmp_path, ledger=SpendLedger(tmp_path / "s.json"), session=g,
                          sleep=lambda s: None)
    with pytest.raises(VoiceUnavailable, match="prepay balance is empty"):
        n.narrate("Hello there.")
    assert len(g.calls) == 1
