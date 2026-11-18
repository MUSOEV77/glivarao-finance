"""External services are mocked: no network, no credentials, nothing published."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from glivarao.marketdata import fetch_yearly, fill_fred_charts
from glivarao.models import JobStatus
from glivarao.publish import telegram, youtube
from glivarao.scriptgen.offline import generate_offline
from glivarao.tts import amplitude_envelope, synthesize

from .conftest import FakeResponse, FakeTelegramSession


# ---------------- TTS ----------------
def test_silent_tts_duration(tmp_path, settings):
    dur = synthesize("word " * 150, tmp_path / "a.wav", settings, provider="silent")
    assert 60 <= dur <= 61


@pytest.mark.skipif(not shutil.which("espeak-ng"), reason="espeak-ng not installed")
def test_espeak_tts_produces_speech(tmp_path, settings):
    wav = tmp_path / "b.wav"
    dur = synthesize("Compound interest rewards patience.", wav, settings, provider="espeak")
    env = amplitude_envelope(wav, 12)
    assert 1.0 < dur < 6 and env.max() == 1.0 and (env > 0.2).sum() > 5


# ---------------- Claude script generation (mocked SDK) ----------------
def test_claude_generator_parses_structured_output(monkeypatch, settings):
    from glivarao.scriptgen import claude

    sample = generate_offline("Roth IRA vs Traditional IRA explained", "short").model_dump(
        exclude={"format", "topic"})
    captured = {}

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return SimpleNamespace(stop_reason="end_turn", stop_details=None,
                                   content=[SimpleNamespace(type="text", text=json.dumps(sample))],
                                   usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    class FakeClient:
        def __init__(self, api_key):
            self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self.stream))

        def stream(self, **kw):
            captured.update(kw)
            return FakeStream()

    monkeypatch.setattr(claude.anthropic, "Anthropic", FakeClient)
    script = claude.generate_with_claude("Roth IRA vs Traditional IRA explained", "short", settings)
    assert script.format == "short" and len(script.scenes) == 4
    assert captured["model"] == "claude-opus-5-5"
    assert captured["output_config"]["format"]["type"] == "json_schema"


# ---------------- FRED (mocked HTTP) ----------------
def test_fred_yearly_yoy_and_fill():
    obs = [{"date": f"{y}-0{m}-01", "value": str(100 * 1.03 ** (y - 2019))} for y in range(2019, 2024) for m in (1, 6)]
    session = SimpleNamespace(get=lambda *a, **k: FakeResponse({"observations": obs}))
    labels, values = fetch_yearly("CPIAUCSL", "k", start_year=2020, session=session)
    assert labels == ["2020", "2021", "2022", "2023"] and all(abs(v - 3.0) < 0.01 for v in values)
    script = generate_offline("Inflation", "short")
    script.scenes[1].chart.kind, script.scenes[1].chart.source = "line_series", "FRED:CPIAUCSL"
    notes = fill_fred_charts(script, "k", session=session)
    assert script.scenes[1].chart.values == values and "FRED" in script.scenes[1].chart.source and notes


# ---------------- Telegram approval (mocked Bot API) ----------------
def _rendered_job(store, tmp_path):
    job = store.create("short", "Topic")
    store.transition(job, JobStatus.SCRIPTED)
    thumb = tmp_path / "t.jpg"
    thumb.write_bytes(b"jpg")
    job.thumbnail_path, job.duration_sec = str(thumb), 50.0
    return store.transition(job, JobStatus.RENDERED)


def test_telegram_request_and_authorized_approval(store, settings, tmp_path):
    s = settings.__class__(**{**settings.__dict__, "telegram_bot_token": "T", "telegram_approver_chat_id": "42"})
    job = _rendered_job(store, tmp_path)
    sess = FakeTelegramSession()
    client = telegram.TelegramClient("T", session=sess)
    telegram.request_approval(job, store, s, "Title", "errors=0", client=client)
    assert store.get(job.id).status == JobStatus.PENDING_APPROVAL
    assert sess.calls[0][0] == "sendPhoto" and "approve:" in sess.calls[0][1]["reply_markup"]

    sess.updates = [
        {"update_id": 1, "callback_query": {"id": "a", "data": f"approve:{job.id}", "from": {"id": 999},
                                            "message": {"message_id": 5, "chat": {"id": 999}}}},
        {"update_id": 2, "callback_query": {"id": "b", "data": f"approve:{job.id}", "from": {"id": 42},
                                            "message": {"message_id": 5, "chat": {"id": 42}}}},
    ]
    decisions = telegram.poll_decisions(store, s, client=client)
    assert decisions == [(job.id, "approved")]  # the unauthorized press was ignored
    assert store.get(job.id).status == JobStatus.APPROVED
    assert store.kv_get("telegram_offset") == "3"


def test_telegram_reject(store, settings, tmp_path):
    s = settings.__class__(**{**settings.__dict__, "telegram_approver_chat_id": "42"})
    job = _rendered_job(store, tmp_path)
    store.transition(job, JobStatus.PENDING_APPROVAL)
    sess = FakeTelegramSession([{"update_id": 7, "callback_query": {
        "id": "c", "data": f"reject:{job.id}", "from": {"id": 42}, "message": {"message_id": 1, "chat": {"id": 42}}}}])
    telegram.poll_decisions(store, s, client=telegram.TelegramClient("T", session=sess))
    assert store.get(job.id).status == JobStatus.REJECTED


# ---------------- YouTube (mocked API client) ----------------
class FakeYouTube:
    def __init__(self):
        self.inserted = None

    def videos(self):
        outer = self

        class V:
            def insert(self, part, body, media_body):
                outer.inserted = body
                return SimpleNamespace(next_chunk=lambda: (None, {"id": "vid123"}))
        return V()

    def thumbnails(self):
        return SimpleNamespace(set=lambda **k: SimpleNamespace(execute=lambda: {}))

    def captions(self):
        return SimpleNamespace(insert=lambda **k: SimpleNamespace(execute=lambda: {}))


def test_youtube_gates_and_upload(store, settings, tmp_path):
    script = generate_offline("Topic", "short")
    job = _rendered_job(store, tmp_path)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\x00" * 10)
    job.video_path = str(video)
    store.save(job)
    with pytest.raises(youtube.PublishBlocked, match="not 'approved'"):
        youtube.upload(job, script, store, settings, youtube=FakeYouTube())
    store.transition(job, JobStatus.PENDING_APPROVAL)
    store.transition(job, JobStatus.APPROVED)
    with pytest.raises(youtube.PublishBlocked, match="kill-switch"):
        youtube.upload(job, script, store, settings, youtube=FakeYouTube())

    enabled = settings.__class__(**{**settings.__dict__, "youtube_publish_enabled": True})
    yt = FakeYouTube()
    assert youtube.upload(job, script, store, enabled, youtube=yt) == "vid123"
    assert yt.inserted["status"]["privacyStatus"] == "private"
    assert "#Shorts" in yt.inserted["snippet"]["title"]
    assert store.get(job.id).status == JobStatus.PUBLISHED


def test_analytics_stores_rows(store, settings, tmp_path):
    job = _rendered_job(store, tmp_path)
    for st in (JobStatus.PENDING_APPROVAL, JobStatus.APPROVED, JobStatus.PUBLISHED):
        store.transition(job, st)
    job.youtube_video_id = "vid1"
    store.save(job)
    res = {"columnHeaders": [{"name": "views"}, {"name": "likes"}], "rows": [[120, 7]]}
    fake = SimpleNamespace(reports=lambda: SimpleNamespace(query=lambda **k: SimpleNamespace(execute=lambda: res)))
    rows = youtube.fetch_analytics(store, settings, analytics=fake)
    assert rows[0]["views"] == 120 and rows[0]["video_id"] == "vid1"
