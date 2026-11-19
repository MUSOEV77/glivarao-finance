"""Quiet hours (your time zone, LOCAL_TZ = Asia/Tashkent): no Telegram messages from QUIET_START (23:00) to
QUIET_END (08:00). Alerts and review packages created at night are queued and delivered when quiet hours end
(the 5-minute poll timer flushes the queue). Replies to things YOU do at night (button presses, commands) are
still answered: you're awake then."""
from __future__ import annotations

import json
import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)


def is_quiet(settings, now: datetime | None = None) -> bool:
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(settings.local_tz))
    start, end, t = time.fromisoformat(settings.quiet_start), time.fromisoformat(settings.quiet_end), now.time()
    return (start <= t or t < end) if start > end else (start <= t < end)


def queue_text(store, text: str) -> None:
    box = json.loads(store.kv_get("outbox_text", "[]"))
    box.append(text[:4000])
    store.kv_set("outbox_text", json.dumps(box[-50:]))


def queue_review(store, job_id: str, payload: dict) -> None:
    box = json.loads(store.kv_get("outbox_review", "{}"))
    box[job_id] = payload
    store.kv_set("outbox_review", json.dumps(box))


def pending(store) -> tuple[int, int]:
    return (len(json.loads(store.kv_get("outbox_text", "[]"))), len(json.loads(store.kv_get("outbox_review", "{}"))))


def flush(settings, store, client=None, now: datetime | None = None) -> int:
    """Deliver queued alerts and reviews once quiet hours are over. Returns the number delivered."""
    if is_quiet(settings, now):
        return 0
    from pathlib import Path

    from ..models import Script
    from ..publish.telegram import _client, request_approval

    c = _client(settings, client)
    sent = 0
    texts = json.loads(store.kv_get("outbox_text", "[]"))
    if texts:
        store.kv_set("outbox_text", "[]")
        joined = "🌅 While you were offline:\n\n" + "\n\n".join(texts)
        for i in range(0, len(joined), 3900):
            c.call("sendMessage", chat_id=settings.telegram_approver_chat_id, text=joined[i:i + 3900])
        sent += len(texts)
    reviews = json.loads(store.kv_get("outbox_review", "{}"))
    for job_id, p in list(reviews.items()):
        try:
            job = store.get(job_id)
            script = Script.model_validate_json(Path(job.script_path).read_text())
            request_approval(job, store, settings, script, Path(p["checks"]).read_text(),
                             preview=Path(p["preview"]) if p.get("preview") else None,
                             attachments=[(Path(a), cap) for a, cap in p.get("attachments", [])], client=c)
            sent += 1
        except Exception as exc:  # noqa: BLE001  keep the rest of the queue moving
            log.warning("could not deliver queued review %s: %s", job_id, exc)
            continue
        reviews.pop(job_id)
        store.kv_set("outbox_review", json.dumps(reviews))
    return sent


__all__ = ["is_quiet", "queue_text", "queue_review", "flush", "pending"]
