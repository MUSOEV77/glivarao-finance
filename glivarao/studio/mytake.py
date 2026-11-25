"""'My take' for tomorrow's long video: at 10:00 the bot asks you for 1-2 sentences (any language); your reply is
translated into natural US English (cheap Claude model) and used as the video's "My take". No reply = the video
is made without one."""
from __future__ import annotations

import json
from datetime import date, timedelta


def tomorrow_long(store, settings, day: date) -> dict | None:
    """The long video planned for tomorrow ({'entry', 'topic'}), or None if tomorrow has no long video."""
    from . import batch, week

    p = week.plan(store, settings, day + timedelta(days=1), today_done=False)
    if not p["days"] or not p["days"][0]["long"]:
        return None
    e = batch.next_long(store) if batch.active(store) else None
    return {"entry": e["id"], "topic": f"{e['title']}: Part {e['part']} {e['label']}"} if e else None


def ask(settings, store, day: date, client=None) -> dict | None:
    from ..publish.telegram import _client

    t = tomorrow_long(store, settings, day)
    if t is None:
        return None
    c = _client(settings, client)
    r = c.call("sendMessage", chat_id=settings.telegram_approver_chat_id, text=(
        f"🎙 Tomorrow's long video: \"{t['topic']}\".\nReply to this message with 1-2 sentences of your own take "
        "(any language: I'll put it in natural US English). No reply = the video is made without \"My take\"."))
    req = {**t, "date": (day + timedelta(days=1)).isoformat(),
           "msg": (r.get("result") or r or {}).get("message_id") if isinstance(r, dict) else None}
    store.kv_set("take_request", json.dumps(req))
    return req


def pending(store, day: date) -> dict | None:
    req = json.loads(store.kv_get("take_request", "{}") or "{}")
    return req if req and req.get("date", "") >= day.isoformat() else None


def to_english(settings, text: str) -> str:
    """Natural US English, 1-2 sentences, meaning unchanged (Claude, cheap model). English stays as it is."""
    text = " ".join(text.split())
    if all(ord(ch) < 128 for ch in text):
        return text
    from ..scriptgen.backends import openrouter_chat

    out, _ = openrouter_chat(settings, "Translate the user's text into natural, plain US English (1-2 sentences). "
                             "Keep the meaning exactly; add nothing. Reply with the translation only.", text, 300,
                             model=getattr(settings, "openrouter_rewrite_model", None) or None)
    return " ".join(out.split()).strip('"')


def save(settings, store, req: dict, text: str) -> str:
    eng = to_english(settings, text)
    store.kv_set(f"take_for:{req['entry']}", eng)
    return eng


def take_for(store, entry_id: str) -> str:
    return store.kv_get(f"take_for:{entry_id}", "") or ""


__all__ = ["ask", "pending", "save", "take_for", "to_english", "tomorrow_long"]
