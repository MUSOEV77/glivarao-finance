"""Telegram approval workflow.

1. `request_approval(job)` sends the thumbnail, title, compliance/fact-check notes and a preview clip
   to the approver chat with inline Approve / Reject buttons.
2. `poll_decisions()` reads button presses via getUpdates (no public webhook needed) and only
   accepts decisions from TELEGRAM_APPROVER_CHAT_ID. Anyone else is ignored and logged.

Nothing is published from here; an approval only moves the job to APPROVED.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from ..config import Settings
from ..models import Job, JobStatus
from ..storage import JobStore

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"
MAX_UPLOAD = 49 * 1024 * 1024


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, session: requests.Session | None = None):
        if not token:
            raise TelegramError("TELEGRAM_BOT_TOKEN is not set")
        self._token = token
        self.http = session or requests.Session()

    def call(self, method: str, files: dict | None = None, **params) -> dict:
        url = API.format(token=self._token, method=method)
        if files:
            data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}
            resp = self.http.post(url, data=data, files=files, timeout=120)
        else:
            resp = self.http.post(url, json=params, timeout=60)
        body = resp.json()
        if not body.get("ok"):
            # never include the URL (it contains the token) in errors
            raise TelegramError(f"{method} failed: {body.get('description', resp.status_code)}")
        return body["result"]


def _keyboard(job_id: str) -> dict:
    return {"inline_keyboard": [[{"text": "✅ Approve", "callback_data": f"approve:{job_id}"},
                                 {"text": "❌ Reject", "callback_data": f"reject:{job_id}"}]]}


def build_caption(job: Job, title: str, compliance_summary: str) -> str:
    dur = f"{job.duration_sec / 60:.1f} min" if job.duration_sec else "?"
    text = (f"🎬 GLIVARAO review — {job.format.upper()}\n"
            f"Job: {job.id}\nTitle: {title}\nTopic: {job.topic}\nDuration: {dur}\n\n"
            f"Checks:\n{compliance_summary}\n\nApprove to allow publishing (still private by default).")
    return text[:1024]  # Telegram caption limit


def request_approval(job: Job, store: JobStore, settings: Settings, title: str, compliance_summary: str,
                     preview: Path | None = None, client: TelegramClient | None = None) -> Job:
    if job.status != JobStatus.RENDERED:
        raise TelegramError(f"Job {job.id} is {job.status.value}; only rendered jobs can be sent for approval")
    client = client or TelegramClient(settings.telegram_bot_token)
    chat = settings.telegram_approver_chat_id
    caption = build_caption(job, title, compliance_summary)
    with open(job.thumbnail_path, "rb") as fh:
        msg = client.call("sendPhoto", files={"photo": fh}, chat_id=chat, caption=caption,
                          reply_markup=_keyboard(job.id))
    if preview and preview.exists() and preview.stat().st_size < MAX_UPLOAD:
        with open(preview, "rb") as fh:
            client.call("sendVideo", files={"video": fh}, chat_id=chat,
                        caption=f"Preview of {job.id} (first seconds, low-res)", supports_streaming=True)
    job.telegram_message_id = msg["message_id"]
    return store.transition(job, JobStatus.PENDING_APPROVAL, "sent to telegram")


def poll_decisions(store: JobStore, settings: Settings, client: TelegramClient | None = None) -> list[tuple[str, str]]:
    """Process pending button presses. Returns [(job_id, decision)]."""
    client = client or TelegramClient(settings.telegram_bot_token)
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
    (client or TelegramClient(settings.telegram_bot_token)).call(
        "sendMessage", chat_id=settings.telegram_approver_chat_id, text=text[:4000])
