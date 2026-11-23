"""Approve / Reject in Telegram: immediate answer on the phone, the buttons show the decision, a confirmation
message; an old press that Telegram refuses to answer never blocks other decisions; poll-approvals --now."""
import json

from glivarao.models import JobStatus
from glivarao.publish import telegram
from tests.conftest import FakeResponse, FakeTelegramSession
from tests.test_integrations import _rendered_job, _tg_settings


class StaleAnswers(FakeTelegramSession):
    """Telegram refuses answers to old button presses ('query is too old')."""

    def post(self, url, json=None, data=None, files=None, timeout=None):
        if url.endswith("/answerCallbackQuery"):
            self.calls.append(("answerCallbackQuery", json or data))
            return FakeResponse({"ok": False, "error_code": 400, "description": "Bad Request: query is too old"},
                                400)
        return super().post(url, json=json, data=data, files=files, timeout=timeout)


def _press(uid, action, job_id, mid=5):
    return {"update_id": uid, "callback_query": {"id": f"q{uid}", "data": f"{action}:{job_id}", "from": {"id": 42},
                                                 "message": {"message_id": mid, "chat": {"id": 42}}}}


def _pending(store, tmp_path, n=1):
    jobs = []
    for _ in range(n):
        j = _rendered_job(store, tmp_path)
        store.transition(j, JobStatus.PENDING_APPROVAL)
        jobs.append(j)
    return jobs


def test_approve_and_reject_give_immediate_visible_feedback(store, settings, tmp_path, monkeypatch):
    monkeypatch.setattr("glivarao.studio.uploadpack.send_pack", lambda *a, **k: "ok")
    s = _tg_settings(settings)
    a, r = _pending(store, tmp_path, 2)
    sess = FakeTelegramSession([_press(1, "approve", a.id), _press(2, "reject", r.id, mid=6)])
    out = telegram.poll_decisions(store, s, client=telegram.TelegramClient("T", session=sess))
    assert out == [(a.id, "approved"), (r.id, "rejected")]
    calls = [(m, p) for m, p in sess.calls if m != "getUpdates"]
    assert calls[0] == ("answerCallbackQuery", {"callback_query_id": "q1", "text": "✅ Approved"})   # first thing
    edits = [p for m, p in calls if m == "editMessageReplyMarkup"]
    assert edits[0]["reply_markup"]["inline_keyboard"][0][0]["text"] == "✅ Approved"
    assert edits[1]["reply_markup"]["inline_keyboard"][0][0]["text"] == "❌ Rejected"
    texts = [p["text"] for m, p in calls if m == "sendMessage"]
    assert any(t.startswith("✅ Approved:") and a.id in t for t in texts)
    assert any(t.startswith("❌ Rejected:") and r.id in t for t in texts)
    assert ("answerCallbackQuery", {"callback_query_id": "q2", "text": "❌ Rejected"}) in calls


def test_an_old_press_that_cannot_be_answered_never_blocks_decisions(store, settings, tmp_path, monkeypatch):
    monkeypatch.setattr("glivarao.studio.uploadpack.send_pack", lambda *a, **k: "ok")
    monkeypatch.setattr(telegram.TelegramClient, "RETRIES", 0)
    s = _tg_settings(settings)
    a, b = _pending(store, tmp_path, 2)
    sess = StaleAnswers([_press(1, "approve", a.id), _press(2, "approve", b.id)])
    out = telegram.poll_decisions(store, s, client=telegram.TelegramClient("T", session=sess))
    assert out == [(a.id, "approved"), (b.id, "approved")]
    assert store.get(b.id).status == JobStatus.APPROVED


def test_pressing_again_shows_the_existing_decision(store, settings, tmp_path, monkeypatch):
    monkeypatch.setattr("glivarao.studio.uploadpack.send_pack", lambda *a, **k: "ok")
    s = _tg_settings(settings)
    (a,) = _pending(store, tmp_path)
    sess = FakeTelegramSession([_press(1, "approve", a.id), _press(2, "reject", a.id), _press(3, "noop", "decided")])
    out = telegram.poll_decisions(store, s, client=telegram.TelegramClient("T", session=sess))
    assert out == [(a.id, "approved")] and store.get(a.id).status == JobStatus.APPROVED
    answers = [p["text"] for m, p in sess.calls if m == "answerCallbackQuery"]
    assert answers == ["✅ Approved", "Already decided: ✅ Approved", "Already decided"]


def test_poll_approvals_now_skips_the_backoff(store, settings, monkeypatch, capsys):
    import time

    from glivarao import __main__ as cli

    s = _tg_settings(settings)
    monkeypatch.setattr(cli, "get_settings", lambda: s)
    monkeypatch.setattr(cli, "_store", lambda st: store)
    store.kv_set("poll_backoff", json.dumps({"fails": 3, "next": time.time() + 3000}))
    polled = []
    monkeypatch.setattr("glivarao.publish.telegram.poll_decisions", lambda st, se, client=None: polled.append(1) or [])
    cli.main(["poll-approvals"])
    assert "backing off" in capsys.readouterr().out and not polled
    cli.main(["poll-approvals", "--now"])
    assert polled == [1]
