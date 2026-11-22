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

    RETRIES = 3

    def call(self, method: str, files: dict | None = None, **params) -> dict:
        """One Bot API call. Temporary problems (network, 429 flood control, 5xx) are retried with backoff,
        honouring Telegram's retry_after; files are rewound before each retry."""
        import time as _time

        url = f"{self._base}/bot{self._token}/{method}"
        last = ""
        for attempt in range(self.RETRIES + 1):
            if attempt:
                for f in (files or {}).values():
                    fh = f[1] if isinstance(f, tuple) else f
                    if hasattr(fh, "seek"):
                        fh.seek(0)
            try:
                if files:
                    data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}
                    resp = self.http.post(url, data=data, files=files, timeout=1800)
                else:
                    resp = self.http.post(url, json=params, timeout=60)
                body = resp.json()
            except (requests.RequestException, ValueError) as exc:
                # requests puts the URL (which contains the bot token) in its messages: never re-raise it
                last = f"{type(exc).__name__} (network/response error)"
                if attempt < self.RETRIES and method != "getUpdates":
                    _time.sleep(min(30, 2 * 2 ** attempt))
                    continue
                raise TelegramError(f"{method} failed: {last}") from None
            if body.get("ok"):
                return body["result"]
            code = body.get("error_code", getattr(resp, "status_code", 0))
            wait = (body.get("parameters") or {}).get("retry_after")
            if (code == 429 or (isinstance(code, int) and code >= 500)) and attempt < self.RETRIES:
                _time.sleep(min(60, float(wait or 2 * 2 ** attempt)))
                continue
            # never include the URL (it contains the token) in errors
            raise TelegramError(f"{method} failed: {body.get('description', code)}")
        raise TelegramError(f"{method} failed: {last}")


    def download(self, file_path: str, dst: Path) -> Path:
        """Download a file sent to the bot (e.g. a voice note). Errors never include the URL/token.
        With the local Bot API server (--local), getFile returns an absolute path on this machine."""
        if file_path.startswith("/") and Path(file_path).is_file():
            Path(dst).write_bytes(Path(file_path).read_bytes())
            return Path(dst)
        try:
            resp = self.http.get(f"{self._base}/file/bot{self._token}/{file_path}", timeout=120)
        except requests.RequestException as exc:
            raise TelegramError(f"download failed: {type(exc).__name__}") from None
        if resp.status_code != 200:
            raise TelegramError(f"download failed: HTTP {resp.status_code}")
        Path(dst).write_bytes(resp.content)
        return Path(dst)


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
                     preview: Path | None = None, client: TelegramClient | None = None,
                     attachments: list[tuple[Path, str]] | None = None) -> Job:
    if job.status != JobStatus.RENDERED:
        raise TelegramError(f"Job {job.id} is {job.status.value}; only rendered jobs can be sent for approval")
    if job.format == "short":  # last line of defence: a Short over the limit never reaches Telegram
        from ..daily_v2 import _video_seconds

        secs = max(job.duration_sec or 0.0, _video_seconds(job.video_path) if job.video_path else 0.0)
        if secs > settings.short_max_seconds:
            raise TelegramError(f"Short {job.id} is {secs:.1f} s (limit {settings.short_max_seconds:.0f} s); not sent")
    client = _client(settings, client)
    chat = settings.telegram_approver_chat_id

    with open(job.thumbnail_path, "rb") as fh:  # a. thumbnail
        client.call("sendPhoto", files={"photo": fh}, chat_id=chat, caption=build_caption(job, script.title))
    send_thumbnail_picker(job, settings, client)
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
    for path, caption in attachments or []:  # e.g. "why this topic" research card and the fact sheet
        if Path(path).exists():
            with open(path, "rb") as fh:
                client.call("sendDocument", files={"document": fh}, chat_id=chat, caption=caption[:1024])
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
    updates = client.call("getUpdates", offset=offset, timeout=0, allowed_updates=["callback_query", "message"])
    decisions = []
    from ..studio import bot

    for upd in updates:
        store.kv_set("telegram_offset", str(upd["update_id"] + 1))
        msg = upd.get("message")
        if msg:  # your topic input (text / voice note) or /queue
            sender = str((msg.get("from") or {}).get("id"))
            chat_id = str((msg.get("chat") or {}).get("id"))
            if settings.telegram_approver_chat_id not in {sender, chat_id}:
                log.warning("Ignoring message from unauthorized Telegram user %s", sender)
                continue
            try:
                bot.handle_message(msg, store, settings, client)
            except Exception as exc:  # noqa: BLE001  one bad message must not block the others
                log.warning("could not handle message: %s", exc)
            continue
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
        if action == "voicepick":  # voice audition: lock the chosen narrator
            from ..studio import voice_audition

            try:
                locked = voice_audition.pick(settings, store, job_id)
                held = len(json.loads(store.kv_get("voice_held", "{}")))
                client.call("answerCallbackQuery", callback_query_id=cq["id"], text=f"{job_id} locked")
                client.call("sendMessage", chat_id=chat_id, text=(
                    f"🔒 Voice locked: {locked['GEMINI_TTS_VOICE']}, energetic style, speed ×"
                    f"{locked['GEMINI_TTS_SPEED']} (~{locked['wpm']} words/min). Every new video uses it."
                    + (f" {held} video(s) on hold will be re-voiced with it within the hour." if held else "")))
                decisions.append((job_id, "voice_locked"))
            except Exception as exc:  # noqa: BLE001
                log.warning("voice pick failed: %s", exc)
                client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Could not lock that voice")
                client.call("sendMessage", chat_id=chat_id, text=f"⚠️ Voice not changed: {str(exc)[:200]}")
            continue
        if action in ("launch", "launchedit"):  # the US-only launch list
            from ..studio import launch_plan

            if action == "launch" and job_id == launch_plan.VERSION:
                launch_plan.approve(store)
                client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Launch list approved")
                client.call("sendMessage", chat_id=chat_id, text=(
                    f"✅ Launch list approved ({len(launch_plan.LAUNCH)} US-only videos, starting with "
                    f"\"{launch_plan.LAUNCH[0].topic}\"). Production is still PAUSED: nothing is made until you "
                    "send resume."))
                decisions.append((job_id, "launch_approved"))
            elif action == "launch":
                client.call("answerCallbackQuery", callback_query_id=cq["id"], text="That list is out of date")
            else:
                client.call("answerCallbackQuery", callback_query_id=cq["id"], text="OK")
                client.call("sendMessage", chat_id=chat_id, text=(
                    "✏️ Tell Claude (in your Claude Code session) which videos to change, drop or reorder; a new list "
                    "will be sent here for approval. Nothing is planned until you approve a list."))
                decisions.append(("launch", "changes_requested"))
            continue
        if action == "thumb":  # thumbnail choice (long videos)
            jid, _, n = job_id.rpartition(":")
            try:
                pick_thumbnail(store, jid, int(n))
                client.call("answerCallbackQuery", callback_query_id=cq["id"], text=f"Thumbnail {n} selected")
                after = store.get(jid).status in (JobStatus.APPROVED, JobStatus.PUBLISHED)
                client.call("sendMessage", chat_id=chat_id, text=f"🖼 {jid}: thumbnail option {n} selected. " + (
                    "The upload pack was already sent: tap \"📦 Send upload pack again\" for this thumbnail."
                    if after else "It goes into the upload pack."))
                decisions.append((jid, f"thumbnail:{n}"))
            except Exception as exc:  # noqa: BLE001
                log.warning("could not pick thumbnail: %s", exc)
                client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Could not pick that one")
            continue
        if action == "pack":  # resend an upload pack
            try:
                from ..studio.uploadpack import send_pack

                job = store.get(job_id)
                client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Sending the upload pack")
                send_pack(job, settings, store, client)
                decisions.append((job_id, "pack"))
            except Exception as exc:  # noqa: BLE001
                log.warning("could not resend upload pack: %s", exc)
            continue
        if action in bot.PREFIXES:  # topic picks, drops and format changes
            try:
                decisions.append((job_id, "topic:" + bot.handle_callback(cq, store, settings, client)))
            except Exception as exc:  # noqa: BLE001
                log.warning("could not handle topic button: %s", exc)
            continue
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
        mid = cq.get("message", {}).get("message_id")
        if mid is not None:  # remove the buttons; cosmetic, so a failure must not block other decisions
            try:
                client.call("editMessageReplyMarkup", chat_id=chat_id, message_id=mid,
                            reply_markup={"inline_keyboard": []})
            except Exception as exc:  # noqa: BLE001
                log.warning("could not remove buttons for %s: %s", job_id, exc)
        client.call("sendMessage", chat_id=chat_id, text=f"{job_id}: {to.value.upper()}")
        decisions.append((job_id, to.value))
        if to == JobStatus.APPROVED:  # deliver the full-quality file + copy-paste upload pack (no upload here)
            try:
                from ..studio.uploadpack import send_pack

                result = send_pack(store.get(job_id), settings, store, client)
                log.info("upload pack sent for %s: %s", job_id, result)
            except Exception as exc:  # noqa: BLE001  approval is recorded even if the pack fails to send
                log.warning("upload pack failed for %s: %s", job_id, exc)
                try:
                    client.call("sendMessage", chat_id=chat_id, text=f"⚠️ Approved, but the upload pack for {job_id} "
                                f"could not be sent ({type(exc).__name__}). Use the 'pack' command to retry.")
                except Exception:  # noqa: BLE001
                    pass
    return decisions


def thumbnail_options(job: Job) -> list[Path]:
    out = Path(job.video_path).parent if job.video_path else None
    return [p for p in (sorted(out.glob("thumbnail_[0-9].jpg")) if out else []) if p.exists()]


def send_thumbnail_picker(job: Job, settings: Settings, client: TelegramClient) -> None:
    """Long videos: the 3 thumbnail options, then one message with [1] [2] [3]. Option 1 is used until you pick."""
    opts = thumbnail_options(job)
    if len(opts) < 2:
        return
    chat = settings.telegram_approver_chat_id
    for k, p in enumerate(opts, 1):
        with open(p, "rb") as fh:
            client.call("sendPhoto", files={"photo": fh}, chat_id=chat, caption=f"Thumbnail option {k}")
    client.call("sendMessage", chat_id=chat, text="Pick the thumbnail (option 1 is used if you don't pick):",
                reply_markup={"inline_keyboard": [[{"text": f"🖼 {k}", "callback_data": f"thumb:{job.id}:{k}"}
                                                   for k in range(1, len(opts) + 1)]]})


def pick_thumbnail(store: JobStore, job_id: str, n: int) -> Path:
    job = store.get(job_id)
    opts = thumbnail_options(job)
    if not 1 <= n <= len(opts):
        raise TelegramError(f"no thumbnail option {n}")
    job.thumbnail_path = str(opts[n - 1])
    store.save(job)
    return opts[n - 1]


def notify(settings: Settings, text: str, client: TelegramClient | None = None, now=None) -> None:
    """Send an alert, or queue it during quiet hours (delivered when they end; see studio/quiet.py)."""
    if not (settings.telegram_bot_token and settings.telegram_approver_chat_id):
        return
    from ..studio import quiet

    if quiet.is_quiet(settings, now):
        quiet.queue_text(JobStore(settings.db_path), text)
        return
    _client(settings, client).call(
        "sendMessage", chat_id=settings.telegram_approver_chat_id, text=text[:4000])
