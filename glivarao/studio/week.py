"""Weekly pace: every Monday-Sunday week (Tashkent) ends at exactly WEEK_LONG long videos + WEEK_SHORTS Shorts
(4 + 21). Counted = videos made this week that are in review, approved or published (failed/rejected don't count).

* Each day makes its share of what is left this week, spread evenly over the days left, so a late start is caught
  up by Sunday: long videos on the days a normal week has them (Mon, Wed, Fri, Sun: by the end of day d the week
  has round(4*d/7)), never two long videos on one day; Shorts = ceil(Shorts left / days left).
* Catch-up publish slots: a day with more Shorts to publish than the 3 normal slots uses the extra slots
  (PUBLISH_TIMES_SHORTS_CATCHUP, New York time) - only until that week's 21 Short slots are booked.
* From the next Monday on, normal weeks: 1 long on Mon/Wed/Fri/Sun, 3 Shorts a day.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TASHKENT = ZoneInfo("Asia/Tashkent")
COUNTED = ("rendered", "pending_approval", "approved", "published")


def today_tk(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(TASHKENT).date()


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _made_on(job) -> date:
    dt = datetime.fromisoformat(job.created_at.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TASHKENT).date()


def counted(store, day: date) -> dict:
    """Videos made in day's Monday-Sunday week (Tashkent) that count: {'long': [...], 'short': [...]} of
    (job_id, status, made_on, topic)."""
    mon = monday(day)
    out = {"long": [], "short": []}
    for job in store.list(limit=2000):
        st = getattr(job.status, "value", str(job.status))
        if st not in COUNTED:
            continue
        d = _made_on(job)
        if mon <= d <= mon + timedelta(days=6):
            fmt = getattr(job.format, "value", str(job.format))
            out["long" if fmt == "long" else "short"].append((job.id, st, d, job.topic))
    for k in out:
        out[k].sort(key=lambda r: (r[2], r[0]))
    return out


def long_expected(d: int, per_week: int) -> int:
    """Long videos a normal week has by the end of day d (1 = Monday): 4 a week -> Mon, Wed, Fri, Sun."""
    return int(per_week * d / 7 + 0.5)


def plan(store, settings, day: date | None = None, today_done: bool | None = None) -> dict:
    """The rest of day's week: [{'date', 'long', 'shorts'}] from today (or tomorrow if today's run already made
    its videos) to Sunday, ending at exactly the weekly targets."""
    day = day or today_tk()
    mon = monday(day)
    c = counted(store, day)
    wl, ws = settings.week_long, settings.week_shorts
    if today_done is None:
        today_done = bool(store.kv_get(f"daily_done:{day.isoformat()}"))
    start = day + timedelta(days=1) if today_done else day
    left_l, left_s = max(0, wl - len(c["long"])), max(0, ws - len(c["short"]))
    days = [start + timedelta(days=k) for k in range((mon + timedelta(days=6) - start).days + 1)]
    out, have_l = [], len(c["long"])
    for i, d in enumerate(days):
        n_left = len(days) - i
        dn = (d - mon).days + 1
        lg = 1 if left_l and (have_l < long_expected(dn, wl) or left_l >= n_left) else 0
        sh = math.ceil(left_s / n_left) if left_s else 0
        out.append({"date": d.isoformat(), "long": lg, "shorts": sh})
        left_l -= lg
        left_s -= sh
        have_l += lg
    return {"monday": mon.isoformat(), "counted": c, "days": out, "week_long": wl, "week_shorts": ws,
            "short_of_long": left_l}


def today_quota(store, settings, day: date | None = None) -> tuple[int, int, str]:
    """(long videos, Shorts) to make today, and why."""
    day = day or today_tk()
    p = plan(store, settings, day, today_done=False)
    c = p["counted"]
    first = p["days"][0] if p["days"] else {"long": 0, "shorts": 0}
    why = (f"week of {p['monday']}: {len(c['long'])}/{p['week_long']} long + {len(c['short'])}/{p['week_shorts']} "
           "Shorts made so far")
    return first["long"], first["shorts"], why


def catchup_slots(settings, p: dict) -> list[tuple[str, list[str]]]:
    """Days that publish more Shorts than the normal slots: (date, the extra New York times used)."""
    normal = [t.strip() for t in settings.publish_times_shorts.split(",") if t.strip()]
    extra = [t.strip() for t in settings.publish_times_shorts_catchup.split(",") if t.strip()]
    out = []
    for d in p["days"]:
        over = d["shorts"] - len(normal)
        if over > 0:
            out.append((d["date"], extra[:over]))
    return out


def status_text(store, settings, day: date | None = None) -> str:
    day = day or today_tk()
    p = plan(store, settings, day)
    c = p["counted"]
    mon = date.fromisoformat(p["monday"])
    lines = [f"📆 GLIVARAO week {mon:%a %b %d} - {mon + timedelta(days=6):%a %b %d} (Tashkent): target "
             f"{p['week_long']} long + {p['week_shorts']} Shorts",
             f"Counted so far: {len(c['long'])} long + {len(c['short'])} Short{'' if len(c['short']) == 1 else 's'} "
             "(in review, approved or published)"]
    for kind in ("long", "short"):
        for jid, st, d, topic in c[kind]:
            lines.append(f"  {kind:5s} {d:%a %d}  {jid}  {st:16s} {topic[:60]}")
    lines.append("Still to make:")
    for d in p["days"]:
        dd = date.fromisoformat(d["date"])
        lines.append(f"  {dd:%a %b %d}: {d['long']} long + {d['shorts']} Shorts")
    slots = catchup_slots(settings, p)
    if slots:
        lines.append("Catch-up publish slots (New York time, on top of " + settings.publish_times_shorts + "):")
        lines += [f"  {date.fromisoformat(d):%a %b %d}: {', '.join(t)}" for d, t in slots]
    else:
        lines.append("No catch-up slots needed: the normal 3 Short slots a day are enough.")
    if p["short_of_long"]:
        lines.append(f"⚠ {p['short_of_long']} long video(s) can't fit this week (one long a day at most).")
    total_l = len(c["long"]) + sum(d["long"] for d in p["days"])
    total_s = len(c["short"]) + sum(d["shorts"] for d in p["days"])
    lines.append(f"Week total if every video passes review: {total_l} long + {total_s} Shorts. "
                 f"From {mon + timedelta(days=7):%a %b %d}: normal weeks (long Mon/Wed/Fri/Sun, 3 Shorts a day).")
    return "\n".join(lines)


def long_days(store, settings, n: int, day: date | None = None) -> list[date]:
    """The next n days a long video is made: what's left of this week, then Mon/Wed/Fri/Sun of normal weeks."""
    day = day or today_tk()
    out = [date.fromisoformat(d["date"]) for d in plan(store, settings, day)["days"] if d["long"]]
    mon = monday(day) + timedelta(days=7)
    while len(out) < n:
        for k in range(7):
            if long_expected(k + 1, settings.week_long) > long_expected(k, settings.week_long):
                out.append(mon + timedelta(days=k))
        mon += timedelta(days=7)
    return out[:n]


STORIES_PER_WEEK = 2


def stories_this_week(store, day: date | None = None) -> int:
    """Long videos in the 'money_story' format made this Monday-Sunday week (from the variety record)."""
    import json as _json

    mon = monday(day or today_tk()).strftime("%Y%m%d")
    end = (monday(day or today_tk()) + timedelta(days=6)).strftime("%Y%m%d")
    hist = _json.loads(store.kv_get("variety_history:long", "[]"))
    return sum(1 for h in hist if h.get("structure") == "money_story" and mon <= str(h.get("job", ""))[:8] <= end)


def want_story(store, brief, day: date | None = None) -> bool:
    """2 of the 4 weekly long videos are money stories (when a documented story is on file for the topic)."""
    from .stories import has_story

    return has_story(brief) and stories_this_week(store, day) < STORIES_PER_WEEK


def week_has_room(store, settings, slot_day: date, fmt: str) -> bool:
    """For catch-up publish slots: True while that week's booked Short slots are below the weekly target."""
    from .publish_times import taken

    mon = monday(slot_day)
    n = 0
    for v in taken(store).values():
        if v["format"] != fmt:
            continue
        d = datetime.fromisoformat(v["slot"]).astimezone(TASHKENT).date()
        n += mon <= d <= mon + timedelta(days=6)
    return n < settings.week_shorts


__all__ = ["counted", "plan", "today_quota", "status_text", "catchup_slots", "week_has_room", "monday", "today_tk",
           "long_expected", "long_days"]
