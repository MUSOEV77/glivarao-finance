"""Daily delivery by 20:00 Tashkent: the day's long video + 3 Shorts in Telegram before DELIVERY_DEADLINE.

* Planned start = the usual DAILY_START (13:17), or earlier when the MEASURED durations say it would not finish in
  time: deadline - (script + long + 3 Shorts) x DELIVERY_MARGIN - DELIVERY_BUFFER_MIN, minus any automatic shift.
  Durations are measured on every run (80th percentile of the last 10; safe defaults until there are 3).
* The systemd timer checks every 15 minutes; the run starts once the planned start has come.
* A video delivered after the deadline is still finished and sent when ready, and you get a Telegram alert with
  the reason (late start, a step that took longer than measured, ...).
* Late 2 days in a row -> the start moves earlier automatically (by the larger lateness + 15 min) and you are told
  the new time. If that is before the end of the 'your take' window, the window is shortened to the new start.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULTS = {"script": 15 * 60.0, "long": 45 * 60.0, "short": 8 * 60.0}   # seconds, until measured
EARLIEST = time(9, 15)              # after the 09:00 announcement


def _tz(settings):
    return ZoneInfo(settings.local_tz)


def now_local(settings) -> datetime:
    return datetime.now(_tz(settings))


def _at(settings, day: date, hhmm: str) -> datetime:
    return datetime.combine(day, time.fromisoformat(hhmm), _tz(settings))


def record_duration(store, kind: str, seconds: float) -> None:
    d = json.loads(store.kv_get("durations", "{}"))
    d[kind] = (d.get(kind, []) + [round(float(seconds), 1)])[-10:]
    store.kv_set("durations", json.dumps(d))


def estimate(store, kind: str) -> float:
    vals = sorted(json.loads(store.kv_get("durations", "{}")).get(kind, []))
    if len(vals) < 3:
        return max([DEFAULTS[kind]] + vals)
    return vals[min(len(vals) - 1, math.ceil(0.8 * len(vals)) - 1)]


def shift_minutes(store) -> int:
    return int(store.kv_get("delivery_shift_min", "0"))


def plan(settings, store, day: date, n_long: int = 1, n_short: int = 3) -> dict:
    """{'start': datetime, 'deadline': datetime, 'needed_min': .., 'why': ..}."""
    deadline = _at(settings, day, settings.delivery_deadline)
    work = estimate(store, "script") + n_long * estimate(store, "long") + n_short * estimate(store, "short")
    needed = timedelta(seconds=work * settings.delivery_margin) + timedelta(minutes=settings.delivery_buffer_min)
    usual = _at(settings, day, settings.daily_start)
    latest_safe = deadline - needed
    start = min(usual, latest_safe) - timedelta(minutes=shift_minutes(store))
    earliest = datetime.combine(day, EARLIEST, _tz(settings))
    clamped = start < earliest
    start = max(start, earliest)
    why = (f"needs ~{work / 60:.0f} min of work (measured) x {settings.delivery_margin:g} + "
           f"{settings.delivery_buffer_min:g} min margin before {settings.delivery_deadline}"
           + (f"; started {shift_minutes(store)} min earlier after late days" if shift_minutes(store) else "")
           + ("; can't start before 09:15, so the deadline may be at risk" if clamped else ""))
    return {"start": start, "deadline": deadline, "needed_min": round(needed.total_seconds() / 60), "why": why,
            "usual": usual}


def due(settings, store, now: datetime | None = None) -> tuple[bool, dict]:
    now = now or now_local(settings)
    p = plan(settings, store, now.date())
    retry_after = store.kv_get(f"daily_retry_after:{now.date().isoformat()}")
    if retry_after and now.timestamp() < float(retry_after):
        return False, p
    return now >= p["start"], p


def input_wait_overridden(settings, p: dict) -> bool:
    """True when the planned start is before the end of the 'your take' window (09:00 + wait): don't wait longer."""
    window_end = p["start"].replace(hour=9, minute=0, second=0, microsecond=0) + \
        timedelta(hours=settings.creator_input_wait_hours)
    return p["start"] < window_end


def start_run(settings, store, day: date, p: dict) -> None:
    store.kv_set(f"delivery_run:{day.isoformat()}", json.dumps({
        "planned": p["start"].isoformat(timespec="minutes"), "started": now_local(settings).isoformat(timespec="minutes"),
        "deadline": p["deadline"].isoformat(timespec="minutes")}))


def delivered(settings, store, day: date, job: tuple, elapsed_s: float, notify) -> int:
    """Called when a video of the daily run reaches Telegram. Alerts if it is after the deadline (with the reason).
    Returns minutes late (0 if on time)."""
    run = json.loads(store.kv_get(f"delivery_run:{day.isoformat()}", "{}"))
    if not run:
        return 0
    now = now_local(settings)
    deadline = datetime.fromisoformat(run["deadline"])
    late = max(0, math.ceil((now - deadline).total_seconds() / 60))
    if late:
        planned, started = datetime.fromisoformat(run["planned"]), datetime.fromisoformat(run["started"])
        reasons = []
        if (started - planned).total_seconds() > 15 * 60:
            reasons.append(f"the run started at {started:%H:%M}, planned {planned:%H:%M}")
        expected = estimate(store, job[1])
        if elapsed_s > expected * 1.2:
            reasons.append(f"this {job[1]} took {elapsed_s / 60:.0f} min (measured usual {expected / 60:.0f} min)")
        if not reasons:
            reasons.append("the whole day's work took longer than planned")
        key = f"late_alert:{job[0]}"
        if not store.kv_get(key):
            store.kv_set(key, "1")
            notify(settings, f"⏰ GLIVARAO: {job[1]} {job[0]} reached Telegram at {now:%H:%M}, {late} min after "
                             f"{deadline:%H:%M}. Reason: {'; '.join(reasons)}. It was finished and sent anyway.")
    d = json.loads(store.kv_get("delivery_late", "{}"))
    d[day.isoformat()] = max(d.get(day.isoformat(), 0), late)
    store.kv_set("delivery_late", json.dumps(dict(sorted(d.items())[-30:])))
    return late


def close_day(settings, store, day: date, notify) -> int | None:
    """After the daily run: late 2 days in a row -> start earlier automatically. Returns the new shift (minutes)."""
    d = json.loads(store.kv_get("delivery_late", "{}"))
    today_late, prev_late = d.get(day.isoformat(), 0), d.get((day - timedelta(days=1)).isoformat(), 0)
    if not (today_late and prev_late):
        return None
    if store.kv_get(f"delivery_shifted:{day.isoformat()}"):
        return None
    store.kv_set(f"delivery_shifted:{day.isoformat()}", "1")
    old = plan(settings, store, day + timedelta(days=1))["start"]
    step = int(math.ceil(max(today_late, prev_late) / 15.0) * 15) + 15
    store.kv_set("delivery_shift_min", str(shift_minutes(store) + step))
    new = plan(settings, store, day + timedelta(days=1))
    note = (" The 'your take' window is shortened to end at the new start." if input_wait_overridden(settings, new)
            else "")
    notify(settings, f"⏰ GLIVARAO: videos were late two days in a row ({prev_late} and {today_late} min after "
                     f"{settings.delivery_deadline}). From tomorrow production starts at {new['start']:%H:%M} "
                     f"instead of {old:%H:%M} ({step} min earlier).{note}")
    return shift_minutes(store)


__all__ = ["plan", "due", "record_duration", "estimate", "delivered", "close_day", "start_run", "now_local",
           "input_wait_overridden", "shift_minutes"]
