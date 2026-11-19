"""Telegram conversations for the human-in-the-loop workflow (all through getUpdates polling).

* Weekly ideas: one message per topic idea with [✅ Make this] [✖ Skip].
* When you pick one: GLIVARAO picks a format by rotation and asks for YOUR take, opinion or example.
  You reply with text or a voice note (reply to that message, or just send it: it goes to the oldest topic waiting).
  Buttons on that message: [🔁 Other format] [✖ Drop topic].
* /queue shows what's waiting.
Only messages from TELEGRAM_APPROVER_CHAT_ID are accepted.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from ..content.brief import build_brief
from .formats import FORMATS, choose_format, eligible
from .queue import TopicQueue

log = logging.getLogger(__name__)
PREFIXES = ("pick", "drop", "fmt")


def format_history(store) -> list[str]:
    return json.loads(store.kv_get("format_history", "[]"))


def push_format(store, style: str) -> None:
    store.kv_set("format_history", json.dumps((format_history(store) + [style])[-50:]))


def send_proposals(items, settings, client, store) -> None:
    chat = settings.telegram_approver_chat_id
    q = TopicQueue(store)
    client.call("sendMessage", chat_id=chat, text=(
        f"💡 This week's topic ideas ({len(items)}). Tap ✅ on the ones you want made "
        f"(about {settings.long_videos_per_month} long videos a month). After you pick one, I'll ask for your own take."))
    for n, it in enumerate(items, 1):
        why = (it.card.get("why") or [""])[0]
        text = f"{n}. {it.topic}\n{it.category} · research score {it.card.get('score', '?')}\n{why}"[:1000]
        msg = client.call("sendMessage", chat_id=chat, text=text, reply_markup={"inline_keyboard": [[
            {"text": "✅ Make this", "callback_data": f"pick:{it.id}"},
            {"text": "✖ Skip", "callback_data": f"drop:{it.id}"}]]})
        q.update(it.id, proposal_msg_id=msg.get("message_id"))


def _ask_for_input(it, settings, client, store) -> None:
    fmt = FORMATS[it.format]
    text = (f"✍️ \"{it.topic}\" — format: {fmt.label}\n{fmt.summary}\n\n"
            "Before I write it, send me YOUR take: an opinion, a personal experience, or an example "
            "(text or a voice note, a few sentences is perfect). Reply to this message. "
            "It goes into the video as \"My take\", and numbers you mention get flagged for you to confirm.")
    msg = client.call("sendMessage", chat_id=settings.telegram_approver_chat_id, text=text, reply_markup={
        "inline_keyboard": [[{"text": "🔁 Other format", "callback_data": f"fmt:{it.id}"},
                             {"text": "✖ Drop topic", "callback_data": f"drop:{it.id}"}]]})
    TopicQueue(store).update(it.id, input_msg_id=msg.get("message_id"))


def handle_callback(cq: dict, store, settings, client, today: date | None = None) -> str:
    action, _, item_id = cq.get("data", "").partition(":")
    q = TopicQueue(store)
    it = q.get(item_id)
    if it is None:
        client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Unknown topic")
        return "unknown"
    if action == "drop":
        q.update(item_id, status="dropped")
        client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Dropped")
        return "dropped"
    brief = build_brief(it.card, today or date.today())
    if action == "pick":
        if it.status != "proposed":
            client.call("answerCallbackQuery", callback_query_id=cq["id"], text=f"Already {it.status}")
            return it.status
        style = choose_format(brief, format_history(store))
        push_format(store, style)
        it = q.pick(item_id, style)
        client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Picked")
        _ask_for_input(it, settings, client, store)
        return "picked"
    if action == "fmt":
        options = eligible(brief)
        nxt = options[(options.index(it.format) + 1) % len(options)] if it.format in options else options[0]
        q.update(item_id, format=nxt)
        client.call("answerCallbackQuery", callback_query_id=cq["id"], text=FORMATS[nxt].label)
        client.call("sendMessage", chat_id=settings.telegram_approver_chat_id,
                    text=f"🔁 \"{it.topic}\" will now be a {FORMATS[nxt].label}: {FORMATS[nxt].summary}")
        return "format"
    return "ignored"


def _download_voice(msg: dict, client, workdir: Path) -> Path | None:
    media = msg.get("voice") or msg.get("audio")
    if not media:
        return None
    info = client.call("getFile", file_id=media["file_id"])
    dst = workdir / f"voice_{msg.get('message_id', 0)}.ogg"
    client.download(info["file_path"], dst)
    return dst


def handle_message(msg: dict, store, settings, client, workdir: Path | None = None, transcriber=None) -> str:
    chat = settings.telegram_approver_chat_id
    text = (msg.get("text") or msg.get("caption") or "").strip()
    q = TopicQueue(store)
    if text.lower().startswith("/queue") or text.lower() in ("/start", "/help"):
        client.call("sendMessage", chat_id=chat, text=q.status_text())
        return "queue"
    reply_to = (msg.get("reply_to_message") or {}).get("message_id")
    it = q.by_message(reply_to) if reply_to else None
    if it is None or it.status not in ("awaiting_input", "ready"):
        waiting = q.awaiting_input()
        it = waiting[0] if waiting else None
    if it is None:
        client.call("sendMessage", chat_id=chat, text="No topic is waiting for your input right now. "
                    "Pick one from this week's ideas (or send /queue).")
        return "no_target"
    kind = "text"
    if msg.get("voice") or msg.get("audio"):
        from .transcribe import transcribe

        workdir = Path(workdir or "data/voice_notes")
        workdir.mkdir(parents=True, exist_ok=True)
        path = _download_voice(msg, client, workdir)
        heard, engine = (transcriber or transcribe)(path, settings) if path else (None, "none")
        if not heard:
            client.call("sendMessage", chat_id=chat, text="I saved your voice note but couldn't transcribe it on "
                        "this server. Please send the same thing as a text message.")
            return "voice_untranscribed"
        text, kind = heard, "voice"
    if not text:
        return "empty"
    it = q.add_input(it.id, text, kind)
    shown = text if len(text) < 600 else text[:600] + "…"
    client.call("sendMessage", chat_id=chat, text=(
        f"✅ Saved your take for \"{it.topic}\" ({FORMATS[it.format].label}).\n"
        + (f"I heard: \"{shown}\"\nIf I got something wrong, just send a correction.\n" if kind == "voice" else "")
        + "It will be used in the next production run (pace: "
        f"{settings.long_videos_per_month} long videos a month)."))
    return "saved"


__all__ = ["send_proposals", "handle_callback", "handle_message", "format_history", "push_format", "PREFIXES"]
