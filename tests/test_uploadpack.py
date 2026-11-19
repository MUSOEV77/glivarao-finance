"""Upload pack after approval: full-quality file, titles, description (sources, AI note, affiliate disclosure),
tags, thumbnail, publish time (New York + Tashkent). Telegram is simulated; nothing is uploaded or scheduled."""
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from glivarao.content.brief import build_brief
from glivarao.content.format_writer import write_long_format
from glivarao.content.packaging import title_options
from glivarao.models import JobStatus
from glivarao.publish import telegram
from glivarao.studio import publish_times
from glivarao.studio.uploadpack import send_pack, tags_line
from tests.test_authenticity import FakeTG
from tests.test_content_audio_daily import card

NOW = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)  # Thursday 10:00 New York


class RecTG(FakeTG):
    def __init__(self):
        super().__init__()
        self.files = []

    def call(self, method, files=None, **params):
        if files:
            f = next(iter(files.values()))
            name, fh = f if isinstance(f, tuple) else (getattr(f, "name", "?").rsplit("/", 1)[-1], f)
            self.files.append((method, name, len(fh.read())))
        return super().call(method, files, **params)


def approved_job(settings, store, tmp_path, fmt="long", size=1000):
    job = store.create(fmt, "Credit cards")
    out = tmp_path / job.id
    out.mkdir()
    (out / "video.mp4").write_bytes(b"0" * size)
    (out / "thumbnail.jpg").write_bytes(b"jpg")
    b = build_brief(card(), NOW.date())
    s = write_long_format(b, "myth_vs_fact")
    desc = s.description + "\n\nDisclosure: affiliate links..."
    (out / "metadata.json").write_text(json.dumps({"title": s.title, "title_options": title_options(b, s),
                                                   "description": desc, "tags": s.tags}))
    job.video_path, job.thumbnail_path, job.duration_sec = str(out / "video.mp4"), str(out / "thumbnail.jpg"), 60
    store.save(job)
    for st in (JobStatus.SCRIPTED, JobStatus.RENDERED, JobStatus.PENDING_APPROVAL, JobStatus.APPROVED):
        store.transition(job, st, "test")
    return store.get(job.id)


def test_publish_slots_ny_and_tashkent(settings, store):
    a = publish_times.next_slot(store, "long", settings, NOW, "L1")
    b = publish_times.next_slot(store, "long", settings, NOW, "L2")
    s1 = publish_times.next_slot(store, "short", settings, NOW, "S1")
    assert a.astimezone(publish_times.NY).strftime("%a %H:%M") == "Thu 14:00"
    assert b.date() > a.date()                                  # one long video per day
    assert s1.astimezone(publish_times.NY).strftime("%H:%M") == "15:00"   # 11:00 is inside the 2 h lead time
    assert publish_times.next_slot(store, "long", settings, NOW, "L1") == a  # stable for the same video
    text = publish_times.describe(a)
    assert "2:00 PM New York (EST)" in text and "12:00 AM Tashkent (UTC+5)" in text and "Fri 20 Nov" in text


def test_title_options_and_tags_limit():
    b = build_brief(card(), NOW.date())
    opts = title_options(b, write_long_format(b, "comparison"))
    assert len(opts) == 3 and len(set(opts)) == 3 and all(len(t) <= 100 for t in opts)
    assert opts[1] == "Credit Cards: Which Option Costs Less?"
    line = tags_line([f"tag number {i}" for i in range(80)])
    assert len(line) <= 500 and line.startswith("tag number 0")


def test_pack_sends_full_file_titles_description_tags_time(settings, store, tmp_path):
    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42", telegram_max_upload_mb=1900)
    job = approved_job(s, store, tmp_path, size=5000)
    tg = RecTG()
    r = send_pack(job, s, store, tg)
    assert r["video"] == "sent" and r["titles"] == 3
    assert ("sendDocument", f"{job.id}.mp4", 5000) in tg.files                 # the original file, not a copy
    assert any(name.endswith("_thumbnail.jpg") for _, name, _ in tg.files)
    texts = tg.texts()
    assert any("TITLE (recommended)" in t for t in texts) and sum("TITLE option" in t for t in texts) == 2
    desc = next(t for t in texts if t.startswith("<b>DESCRIPTION"))
    assert "Sources:" in desc and "affiliate" in desc and "<pre>" in desc
    assert any(t.startswith("<b>TAGS</b>") for t in texts)
    assert any("New York" in t and "Tashkent" in t for t in texts)
    assert all(p.get("parse_mode") == "HTML" for m, p in tg.calls if m == "sendMessage")


def test_pack_explains_when_file_is_over_the_cloud_limit(settings, store, tmp_path):
    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42", telegram_max_upload_mb=1)
    job = approved_job(s, store, tmp_path, size=3 * 1024 * 1024)
    tg = RecTG()
    assert send_pack(job, s, store, tg)["video"] == "too large for this bot server"
    assert not any(n.endswith(".mp4") for _, n, _ in tg.files)
    assert any("TELEGRAM_LARGE_FILES" in t for t in tg.texts())


def test_approve_button_triggers_the_pack(settings, store, tmp_path, monkeypatch):
    s = replace(settings, telegram_bot_token="T", telegram_approver_chat_id="42", telegram_max_upload_mb=1900)
    job = approved_job(s, store, tmp_path)
    store.conn.execute("UPDATE jobs SET status='pending_approval' WHERE id=?", (job.id,))
    j = store.get(job.id)
    j.status = JobStatus.PENDING_APPROVAL
    store.save(j)
    updates = [{"update_id": 1, "callback_query": {"id": "a", "from": {"id": 42},
                                                   "message": {"message_id": 5, "chat": {"id": 42}},
                                                   "data": f"approve:{job.id}"}}]

    class C(RecTG):
        def call(self, method, files=None, **params):
            if method == "getUpdates":
                return updates
            return super().call(method, files, **params)

    c = C()
    telegram.poll_decisions(store, s, client=c)
    assert store.get(job.id).status == JobStatus.APPROVED
    assert any(n == f"{job.id}.mp4" for _, n, _ in c.files) and any("UPLOAD PACK" in t for t in c.texts())


def test_local_bot_api_file_paths_are_read_directly(tmp_path):
    src = tmp_path / "voice.oga"
    src.write_bytes(b"OggS-local")
    dst = telegram.TelegramClient("T", base="http://127.0.0.1:8081").download(str(src), tmp_path / "out.oga")
    assert dst.read_bytes() == b"OggS-local"


def test_plan_next_skips_when_no_long_video_is_due(settings, store, capsys, monkeypatch, tmp_path):
    from glivarao import __main__ as cli

    monkeypatch.setattr(cli, "get_settings", lambda: replace(settings, long_videos_per_month=0))
    cli.main(["plan-next", "--no-telegram", "--date", "2026-11-19"])
    assert "Shorts day" in capsys.readouterr().out
