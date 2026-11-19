"""Buffer: always BUFFER_LONG (2) approved long videos and BUFFER_SHORTS (6) approved Shorts ready ahead of their
publish slots, produced PRODUCTION_LEAD_DAYS (2-3) days ahead.

"Ready" = approved and its suggested publish slot is still in the future (you upload manually with Schedule).
"In review" = rendered and waiting for your Approve. Videos on hold (voice) are counted separately.
When the buffer is low the daily run may produce early (never above the monthly totals) and you get an alert.
"""
from __future__ import annotations

import calendar
import json
import math
from datetime import date, datetime, timezone

from ..models import JobStatus


def status(store, settings, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    slots = json.loads(store.kv_get("publish_slots", "{}"))
    out = {"ready_long": 0, "ready_shorts": 0, "review_long": 0, "review_shorts": 0, "held": 0}
    for job in store.list(JobStatus.APPROVED, limit=400):
        slot = slots.get(job.id, {}).get("slot")
        if slot is None or datetime.fromisoformat(slot) > now:
            out["ready_long" if job.format == "long" else "ready_shorts"] += 1
    for job in store.list(JobStatus.PENDING_APPROVAL, limit=400):
        out["review_long" if job.format == "long" else "review_shorts"] += 1
    out["held"] = len(json.loads(store.kv_get("voice_held", "{}")))
    out["low_long"] = out["ready_long"] < settings.buffer_long
    out["low_shorts"] = out["ready_shorts"] < settings.buffer_shorts
    return out


def text(b: dict, settings) -> str:
    def line(kind, ready, review, need):
        mark = "✅" if ready >= need else "⚠️"
        return f"{mark} {kind}: {ready} approved and ready (target {need}), {review} waiting for your review"
    return "\n".join([line("Long videos", b["ready_long"], b["review_long"], settings.buffer_long),
                      line("Shorts", b["ready_shorts"], b["review_shorts"], settings.buffer_shorts)]
                     + ([f"⏸ {b['held']} on hold (voice)"] if b["held"] else []))


def _due(target: int, today: date, lead: int) -> int:
    days = calendar.monthrange(today.year, today.month)[1]
    return min(target, math.ceil(target * min(days, today.day + lead) / days))


def long_due(store, today: date, settings) -> tuple[int, int]:
    """(made this month, due by today + lead days)."""
    dates = [date.fromisoformat(d) for d in json.loads(store.kv_get("long_dates", "[]"))]
    made = sum((d.year, d.month) == (today.year, today.month) for d in dates)
    return made, _due(settings.long_videos_per_month, today, settings.production_lead_days)


def shorts_quota(store, today: date, settings, buffer: dict | None = None) -> int:
    """Shorts to make today: SHORTS_PER_DAY (3 -> 90 a month); up to twice that when the Shorts buffer is low;
    never above SHORTS_PER_MONTH for the calendar month."""
    counts = json.loads(store.kv_get("short_counts", "{}"))
    made = sum(n for d, n in counts.items() if d[:7] == today.isoformat()[:7])
    want = settings.shorts_per_day
    if buffer is not None and buffer.get("low_shorts"):
        deficit = settings.buffer_shorts - buffer["ready_shorts"] - buffer["review_shorts"]
        want = min(2 * settings.shorts_per_day, max(want, deficit))
    return max(0, min(want, settings.shorts_per_month - made))


def record_shorts(store, today: date, n: int) -> None:
    counts = json.loads(store.kv_get("short_counts", "{}"))
    counts[today.isoformat()] = counts.get(today.isoformat(), 0) + n
    store.kv_set("short_counts", json.dumps(dict(sorted(counts.items())[-120:])))


__all__ = ["status", "text", "long_due", "shorts_quota", "record_shorts"]
