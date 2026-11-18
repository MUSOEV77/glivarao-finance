"""Telegram approval workflow.

1. `request_approval(job)` sends a complete review package to the approver chat:
     a. thumbnail (photo) with job summary
     b. full title, description and tags (text)
     c. preview clip (first 60 s, 480p)
     d. the finished MP4 (master if it fits the upload limit, otherwise a size-fitted 720p review copy;
        the master path is stated) and the SRT captions
     e. compliance / fact-check report, then the Approve / Reject buttons
2. `poll_decisions()` reads button presses via getUpdates (no public webhook needed) and only
   accepts decisions from TELEGRAM_APPROVER_CHAT_ID. Anyone else is ignored and logged.

Nothing is uploaded or published from here. Approval only moves the job to APPROVED; uploading is a
separate manual, interactive, private-only command.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from ..config import Settings
from ..models import Job, JobStatus, Script
from ..storage import JobStore

log = logging.getLogger(__name__)
TEXT_LIMIT = 4000


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, session: requests.Session | None = None,
                 base: str = "https://api.telegram.org"):
        if not token:
            raise TelegramError("TELEGRAM_BOT_TOKEN is not set")
        self._token = token
        self._base = base.rstrip("/")
        self.http = session or requests.Session()

    def call(self, method: str, files: dict | None = None, **params) -> dict:
        url = f"{self._base}/bot{self._token}/{method}"
        try:
            if files:
                data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}
                resp = self.http.post(url, data=data, files=files, timeout=1800)
            else:
                resp = self.http.post(url, json=params, timeout=60)
            body = resp.json()
        except (requests.RequestException, ValueError) as exc:
            # requests puts the URL (which contains the bot token) in its messages: never re-raise it
            raise TelegramError(f"{method} failed: {type(exc).__name__} (network/response error)") from None
        if not body.get("ok"):
            # never include the URL (it contains the token) in errors
            raise TelegramError(f"{method} failed: {body.get('description', resp.status_code)}")
        return body["result"]


def _keyboard(job_id: str) -> dict:
    return {"inline_keyboard": [[{"text": "✅ Approve", "callback_data": f"approve:{job_id}"},
                                 {"text": "❌ Reject", "callback_data": f"reject:{job_id}"}]]}


def _client(settings: Settings, client: TelegramClient | None) -> TelegramClient:
    return client or TelegramClient(settings.telegram_bot_token, base=settings.telegram_api_base)


def build_caption(job: Job, title: str) -> str:
    dur = f"{job.duration_sec / 60:.1f} min" if job.duration_sec else "?"
    return (f"🎬 GLIVARAO review — {job.format.upper()}\nJob: {job.id}\nTitle: {title}\n"
            f"Topic: {job.topic}\nDuration: {dur}")[:1024]


def _chunks(text: str, n: int = TEXT_LIMIT) -> list[str]:
    return [text[i:i + n] for i in range(0, len(text), n)] or [""]


def review_video_file(job: Job, settings: Settings) -> tuple[Path, str]:
    """The finished MP4 to send: the master if it fits the upload limit, else a size-fitted review copy."""
    from ..render.video import fit_to_size

    master = Path(job.video_path)
    limit = settings.telegram_max_upload_mb * 1024 * 1024 - 512 * 1024  # leave room for multipart overhead
    if master.stat().st_size <= limit:
        return master, "Finished video (full-quality master)"
    copy = fit_to_size(master, master.with_name("review_copy.mp4"), limit)
    mb = master.stat().st_size / 1024 / 1024
    return copy, (f"Finished video, complete length, compressed review copy (720p). The {mb:.0f} MB master "
                  f"exceeds the {settings.telegram_max_upload_mb} MB Bot API limit; it is on the server at "
                  f"{master}.")


def request_approval(job: Job, store: JobStore, settings: Settings, script: Script, compliance_summary: str,
                     preview: Path | None = None, client: TelegramClient | None = None) -> Job:
    if job.status != JobStatus.RENDERED:
        raise TelegramError(f"Job {job.id} is {job.status.value}; only rendered jobs can be sent for approval")
    client = _client(settings, client)
    chat = settings.telegram_approver_chat_id

    with open(job.thumbnail_path, "rb") as fh:  # a. thumbnail
        client.call("sendPhoto", files={"photo": fh}, chat_id=chat, caption=build_caption(job, script.title))
    meta = (f"TITLE:\n{script.title}\n\nDESCRIPTION:\n{script.description}\n\n"
            f"TAGS: {', '.join(script.tags)}")
    for part in _chunks(meta):  # b. title + description
        client.call("sendMessage", chat_id=chat, text=part)
    if preview and preview.exists() and preview != Path(job.video_path):  # c. preview clip
        with open(preview, "rb") as fh:
            client.call("sendVideo", files={"video": fh}, chat_id=chat, supports_streaming=True,
                        caption=f"Preview: first {min(60, int(job.duration_sec or 60))} s (480p)")
    video, note = review_video_file(job, settings)  # d. finished MP4 + captions
    with open(video, "rb") as fh:
        client.call("sendVideo", files={"video": fh}, chat_id=chat, supports_streaming=True, caption=note[:1024])
    if job.subtitles_path and Path(job.subtitles_path).exists():
        with open(job.subtitles_path, "rb") as fh:
            client.call("sendDocument", files={"document": fh}, chat_id=chat, caption="Captions (SRT)")
    report = (f"Automated checks for {job.id}:\n{compliance_summary}\n\n"
              "Approving does NOT upload or publish anything. Uploading is a separate manual step.")
    parts = _chunks(report)
    for part in parts[:-1]:
        client.call("sendMessage", chat_id=chat, text=part)
    msg = client.call("sendMessage", chat_id=chat, text=parts[-1], reply_markup=_keyboard(job.id))  # e.
    job.telegram_message_id = msg["message_id"]
    return store.transition(job, JobStatus.PENDING_APPROVAL, "review package sent to telegram")


def poll_decisions(store: JobStore, settings: Settings, client: TelegramClient | None = None) -> list[tuple[str, str]]:
    """Process pending button presses. Returns [(job_id, decision)]."""
    client = _client(settings, client)
    offset = int(store.kv_get("telegram_offset", "0"))
    updates = client.call("getUpdates", offset=offset, timeout=0, allowed_updates=["callback_query"])
    decisions = []
    for upd in updates:
        store.kv_set("telegram_offset", str(upd["update_id"] + 1))
        cq = upd.get("callback_query")
        if not cq:
            continue
        sender = str(cq.get("from", {}).get("id"))
        chat_id = str(cq.get("message", {}).get("chat", {}).get("id"))
        if settings.telegram_approver_chat_id not in {sender, chat_id}:
            log.warning("Ignoring decision from unauthorized Telegram user %s", sender)
            client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Not authorized")
            continue
        action, _, job_id = cq.get("data", "").partition(":")
        try:
            job = store.get(job_id)
        except KeyError:
            client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Unknown job")
            continue
        if job.status != JobStatus.PENDING_APPROVAL:
            client.call("answerCallbackQuery", callback_query_id=cq["id"], text=f"Already {job.status.value}")
            continue
        to = JobStatus.APPROVED if action == "approve" else JobStatus.REJECTED
        store.transition(job, to, f"telegram user {sender}")
        client.call("answerCallbackQuery", callback_query_id=cq["id"], text=f"{to.value}")
        client.call("editMessageReplyMarkup", chat_id=chat_id, message_id=cq["message"]["message_id"],
                    reply_markup={"inline_keyboard": []})
        client.call("sendMessage", chat_id=chat_id, text=f"{job_id}: {to.value.upper()}")
        decisions.append((job_id, to.value))
    return decisions


def notify(settings: Settings, text: str, client: TelegramClient | None = None) -> None:
    if not (settings.telegram_bot_token and settings.telegram_approver_chat_id):
        return
    _client(settings, client).call(
        "sendMessage", chat_id=settings.telegram_approver_chat_id, text=text[:4000])
