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
def test_claude_generator_parses_structured_output(monkeypatch, settings, tmp_path):
    from dataclasses import replace

    from glivarao.scriptgen import claude

    settings = replace(settings, claude_spend_ledger_path=str(tmp_path / "claude_spend.json"))

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
    assert script.format == "short" and len(script.scenes) == len(sample["scenes"])
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


def _tg_settings(settings, **kw):
    return settings.__class__(**{**settings.__dict__, "telegram_bot_token": "T", "telegram_approver_chat_id": "42",
                                 **kw})


def _with_media(store, job, tmp_path, video_bytes=2048):
    video, srt, prev = tmp_path / "video.mp4", tmp_path / "c.srt", tmp_path / "preview.mp4"
    video.write_bytes(b"\0" * video_bytes)
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    prev.write_bytes(b"p")
    job.video_path, job.subtitles_path = str(video), str(srt)
    store.save(job)
    return prev


def test_telegram_sends_full_review_package_then_buttons(store, settings, tmp_path):
    s = _tg_settings(settings)
    job = _rendered_job(store, tmp_path)
    prev = _with_media(store, job, tmp_path)
    script = generate_offline("Topic", "short")
    sess = FakeTelegramSession()
    telegram.request_approval(job, store, s, script, "errors=0", preview=prev,
                              client=telegram.TelegramClient("T", session=sess))
    methods = [m for m, _ in sess.calls]
    assert methods == ["sendPhoto", "sendMessage", "sendVideo", "sendVideo", "sendDocument", "sendMessage"]
    text = " ".join(str(p) for _, p in sess.calls)
    assert script.title in text and script.description.splitlines()[0] in text  # title + description
    assert "full-quality master" in text                                          # finished MP4 sent
    assert "approve:" in str(sess.calls[-1][1]["reply_markup"])                  # buttons come last
    assert "does NOT upload" in sess.calls[-1][1]["text"]
    assert store.get(job.id).status == JobStatus.PENDING_APPROVAL


def test_telegram_oversized_master_gets_fitted_review_copy(store, settings, tmp_path, monkeypatch):
    from glivarao.render import video as video_mod

    s = _tg_settings(settings, telegram_max_upload_mb=1)
    job = _rendered_job(store, tmp_path)
    _with_media(store, job, tmp_path, video_bytes=3 * 1024 * 1024)

    def fake_fit(src, dst, max_bytes, height=720):
        dst.write_bytes(b"\0" * (max_bytes // 2))
        return dst
    monkeypatch.setattr(video_mod, "fit_to_size", fake_fit)
    path, note = telegram.review_video_file(job, s)
    assert path.name == "review_copy.mp4" and path.stat().st_size < 1024 * 1024
    assert "compressed review copy" in note and str(job.video_path) in note


def test_telegram_authorized_approval_only(store, settings, tmp_path):
    s = _tg_settings(settings)
    job = _rendered_job(store, tmp_path)
    store.transition(job, JobStatus.PENDING_APPROVAL)
    sess = FakeTelegramSession([
        {"update_id": 1, "callback_query": {"id": "a", "data": f"approve:{job.id}", "from": {"id": 999},
                                            "message": {"message_id": 5, "chat": {"id": 999}}}},
        {"update_id": 2, "callback_query": {"id": "b", "data": f"approve:{job.id}", "from": {"id": 42},
                                            "message": {"message_id": 5, "chat": {"id": 42}}}},
    ])
    decisions = telegram.poll_decisions(store, s, client=telegram.TelegramClient("T", session=sess))
    assert decisions == [(job.id, "approved")]  # the unauthorized press was ignored
    assert store.get(job.id).status == JobStatus.APPROVED  # approved, NOT uploaded
    assert not any(m.startswith("upload") for m, _ in sess.calls)
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


def test_youtube_upload_is_manual_private_only(store, settings, tmp_path):
    script = generate_offline("Topic", "short")
    job = _rendered_job(store, tmp_path)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\x00" * 10)
    job.video_path = str(video)
    store.save(job)
    enabled = settings.__class__(**{**settings.__dict__, "youtube_publish_enabled": True})
    with pytest.raises(youtube.PublishBlocked, match="not 'approved'"):
        youtube.upload(job, script, store, enabled, operator_confirmation=job.id, youtube=FakeYouTube())
    store.transition(job, JobStatus.PENDING_APPROVAL)
    store.transition(job, JobStatus.APPROVED)
    with pytest.raises(youtube.PublishBlocked, match="Manual operator confirmation"):
        youtube.upload(job, script, store, enabled, youtube=FakeYouTube())  # approval alone is not enough
    with pytest.raises(youtube.PublishBlocked, match="kill-switch"):
        youtube.upload(job, script, store, settings, operator_confirmation=job.id, youtube=FakeYouTube())

    yt = FakeYouTube()
    assert youtube.upload(job, script, store, enabled, operator_confirmation=job.id, youtube=yt) == "vid123"
    assert yt.inserted["status"]["privacyStatus"] == "private" and "publishAt" not in yt.inserted["status"]
    assert "#Shorts" in yt.inserted["snippet"]["title"]


def test_cli_has_no_automatic_upload_paths(monkeypatch, capsys):
    from glivarao import __main__ as cli

    with pytest.raises(SystemExit):
        cli.main(["poll-approvals", "--auto-publish"])
    with pytest.raises(SystemExit):
        cli.main(["publish", "job", "--privacy", "public"])
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: False))
    assert cli.main(["publish", "some-job"]) == 1
    assert "interactive terminal" in capsys.readouterr().err


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


def test_network_errors_never_leak_tokens():
    import requests as rq

    class Boom:
        def post(self, url, **kw):
            raise rq.ConnectionError(f"Max retries exceeded with url: {url}")

        def get(self, url, params=None, **kw):
            raise rq.ConnectionError(f"Max retries exceeded with url: {url}?api_key={params['api_key']}")

    with pytest.raises(telegram.TelegramError) as e1:
        telegram.TelegramClient("123456:SECRET-TOKEN", session=Boom()).call("getMe")
    assert "SECRET" not in str(e1.value) and e1.value.__cause__ is None
    from glivarao.marketdata import MarketDataError

    with pytest.raises(MarketDataError) as e2:
        fetch_yearly("FEDFUNDS", "FRED-SECRET", session=Boom())
    assert "FRED-SECRET" not in str(e2.value)
