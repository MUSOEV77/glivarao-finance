"""Suggested publish times for you to enter in YouTube Studio's "Schedule" (GLIVARAO never schedules or uploads).

Defaults for a US + Canada audience, in New York time (common starting points for US finance channels; replace them
with your own data once YouTube Studio → Analytics → Audience → "When your viewers are on YouTube" has enough
views):
  long videos: weekdays 2:00 PM, weekends 11:00 AM; at most one long video per day
  Shorts:      11:00 AM, 3:00 PM and 7:30 PM (one Short per slot)
Each approved video gets the next free slot at least PUBLISH_LEAD_HOURS ahead (time to download and upload it).
Shown in both New York and Tashkent time (Tashkent is UTC+5 all year; New York switches EST/EDT).
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
TASHKENT = ZoneInfo("Asia/Tashkent")


def _times(spec: str) -> list[time]:
    return [time.fromisoformat(t.strip()) for t in spec.split(",") if t.strip()]


def _slots_for_day(day, fmt: str, settings) -> list[datetime]:
    if fmt == "long":
        spec = settings.publish_times_long_weekend if day.weekday() >= 5 else settings.publish_times_long_weekday
    else:
        spec = settings.publish_times_shorts
    return [datetime.combine(day, t, NY) for t in _times(spec)]


def taken(store) -> dict:
    return json.loads(store.kv_get("publish_slots", "{}"))


def next_slot(store, fmt: str, settings, now: datetime | None = None, job_id: str = "") -> datetime:
    """The next free slot (reserved for job_id, so asking again for the same job returns the same slot)."""
    book = taken(store)
    if job_id and job_id in book:
        return datetime.fromisoformat(book[job_id]["slot"])
    now = (now or datetime.now(timezone.utc)).astimezone(NY)
    earliest = now + timedelta(hours=settings.publish_lead_hours)
    used = {v["slot"] for v in book.values() if v["format"] == fmt}
    long_days = {datetime.fromisoformat(v["slot"]).date() for v in book.values() if v["format"] == "long"}
    day = earliest.date()
    for _ in range(60):
        slots = _slots_for_day(day, fmt, settings)
        if fmt != "long" and getattr(settings, "pace_mode", "") == "weekly":
            from . import week

            if all(s.isoformat() in used or s < earliest for s in slots) and \
                    week.week_has_room(store, settings, day, fmt):   # catching up: the extra slots this week
                slots = slots + [datetime.combine(day, t, NY) for t in _times(settings.publish_times_shorts_catchup)]
        for slot in slots:
            if slot < earliest or slot.isoformat() in used:
                continue
            if fmt == "long" and slot.date() in long_days:
                continue
            if job_id:
                book[job_id] = {"format": fmt, "slot": slot.isoformat()}
                store.kv_set("publish_slots", json.dumps(dict(list(book.items())[-400:])))
            return slot
        day += timedelta(days=1)
    raise RuntimeError("no free publish slot in the next 60 days")


def describe(slot: datetime) -> str:
    ny, tk = slot.astimezone(NY), slot.astimezone(TASHKENT)
    fmt = lambda d: d.strftime("%a %d %b %Y, %I:%M %p").replace(" 0", " ")  # noqa: E731
    return f"{fmt(ny)} New York ({ny.tzname()})\n{fmt(tk)} Tashkent (UTC+5)"


__all__ = ["next_slot", "describe", "NY", "TASHKENT"]
