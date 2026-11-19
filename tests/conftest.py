import pytest

from glivarao.config import Settings
from glivarao.storage import JobStore


@pytest.fixture
def settings(tmp_path):
    return Settings(mode="dry-run", output_dir=tmp_path / "out", db_path=tmp_path / "db.sqlite3", fps=6,
                    tts_provider="silent", anthropic_api_key="", telegram_bot_token="",
                    telegram_approver_chat_id="", youtube_publish_enabled=False,
                    youtube_client_secrets_file=tmp_path / "none.json", youtube_token_file=tmp_path / "tok.json",
                    buffer_long=0, buffer_shorts=0,  # buffer rules are tested in test_buffer_schedule.py
                    quiet_start="00:00", quiet_end="00:00",  # no quiet hours: tests must not depend on the clock
                    writer="claude_api")


@pytest.fixture
def store(settings):
    import json

    st = JobStore(settings.db_path)
    st.kv_set("launch_done", json.dumps(list(range(1, 17))))  # research-driven by default; launch tests reset this
    return st


class FakeResponse:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, str(payload)

    def json(self):
        return self._p


class FakeTelegramSession:
    """Records Bot API calls and replays queued getUpdates results."""

    def __init__(self, updates=None):
        self.calls, self.updates, self._mid = [], list(updates or []), 100

    def post(self, url, json=None, data=None, files=None, timeout=None):
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, json or data))
        if method == "getUpdates":
            res, self.updates = self.updates, []
            return FakeResponse({"ok": True, "result": res})
        self._mid += 1
        return FakeResponse({"ok": True, "result": {"message_id": self._mid}})
