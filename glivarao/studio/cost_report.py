"""`python -m glivarao cost-report`: what each long video and each Short really cost (Claude, voice, images).

Amounts are the billed amounts the spend ledgers record for every paid call (the same numbers the monthly budget
uses), logged per video by studio/costs.py. Cached voice clips and reused images cost nothing and add nothing.
"""
from __future__ import annotations

import time
from datetime import date, datetime
from pathlib import Path

from . import costs

DELIVERED = {"rendered", "pending_approval", "approved", "scheduled", "published", "uploaded"}
WASTED = {"rejected_compliance", "failed", "rejected"}


def _dirs(settings) -> list[Path]:
    return [Path(settings.claude_spend_ledger_path).parent, Path(settings.tts_spend_ledger_path).parent,
            Path(settings.image_spend_ledger_path).parent]


def build(settings, store, days: int = 30, now: float | None = None) -> dict:
    now = now or time.time()
    since = now - days * 86400
    events, links = costs.load(_dirs(settings))
    by_tag = costs.per_tag(events, links, since)
    videos, other, unused = [], {k: 0.0 for k in costs.KINDS}, {k: 0.0 for k in costs.KINDS}
    for t, amounts in by_tag.items():
        if t.startswith("draft:"):            # written but never became a video (e.g. the run stopped)
            for k in costs.KINDS:
                unused[k] += amounts[k]
            continue
        try:
            job = store.get(t) if t else None
        except KeyError:
            job = None
        if job is None:                        # voice test, research, health checks, ...
            for k in costs.KINDS:
                other[k] += amounts[k]
            continue
        status = getattr(job.status, "value", str(job.status))
        videos.append({"id": job.id, "format": getattr(job.format, "value", str(job.format)), "status": status,
                       "topic": job.topic, **{k: round(amounts[k], 4) for k in costs.KINDS},
                       "total": round(sum(amounts.values()), 4)})
    videos.sort(key=lambda v: v["id"])
    avg = {}
    for fmt in ("long", "short"):
        done = [v for v in videos if v["format"] == fmt and v["status"] in DELIVERED]
        if done:
            avg[fmt] = {"n": len(done), **{k: round(sum(v[k] for v in done) / len(done), 4)
                                           for k in (*costs.KINDS, "total")}}
    month = {}
    if avg:
        month = {"long": settings.long_videos_per_month, "short": settings.shorts_per_month,
                 "usd": round(avg.get("long", {}).get("total", 0) * settings.long_videos_per_month +
                              avg.get("short", {}).get("total", 0) * settings.shorts_per_month, 2)}
    wasted = round(sum(v["total"] for v in videos if v["status"] in WASTED), 4)
    return {"days": days, "since": date.fromtimestamp(since).isoformat(), "videos": videos, "avg": avg,
            "month_estimate": month, "wasted": wasted,
            "other": {k: round(v, 4) for k, v in other.items()}, "unused_drafts": {k: round(v, 4)
                                                                                for k, v in unused.items()},
            "ledgers": _ledgers(settings)}


def _ledgers(settings) -> dict:
    from ..art.gemini_image import ImageLedger
    from ..scriptgen.claude import ClaudeSpendLedger
    from ..tts.gemini_tts import SpendLedger

    m = datetime.now().strftime("%Y-%m")
    return {"month": m, "claude": ClaudeSpendLedger(Path(settings.claude_spend_ledger_path)).spent(m),
            "voice": SpendLedger(Path(settings.tts_spend_ledger_path)).spent(m),
            "images": ImageLedger(Path(settings.image_spend_ledger_path)).spent(m)}


def _usd(x: float) -> str:
    return f"${x:,.2f}" if x >= 0.995 or x == 0 else f"${x:.3f}"


def text(r: dict) -> str:
    lines = [f"Real spend per video, last {r['days']} days (since {r['since']}), USD"]
    if not r["videos"]:
        lines.append("No paid calls tied to a video yet. Per-video tracking starts with this version: the next "
                     "video made will show here.")
    else:
        lines.append(f"{'video':28s} {'type':5s} {'status':19s} {'Claude':>8s} {'Voice':>8s} {'Images':>8s} "
                     f"{'Total':>8s}")
        for v in r["videos"]:
            lines.append(f"{v['id']:28s} {v['format']:5s} {v['status']:19s} {_usd(v['claude']):>8s} "
                         f"{_usd(v['voice']):>8s} {_usd(v['images']):>8s} {_usd(v['total']):>8s}")
    lines.append("")
    names = {"long": "long video", "short": "Short"}
    for fmt in ("long", "short"):
        a = r["avg"].get(fmt)
        if a:
            lines.append(f"Average per {names[fmt]} (n={a['n']} sent for review): Claude {_usd(a['claude'])}, "
                         f"voice {_usd(a['voice'])}, images {_usd(a['images'])} = {_usd(a['total'])}")
        else:
            lines.append(f"Average per {names[fmt]}: no {names[fmt]} sent for review in this period yet")
    if r["month_estimate"]:
        m = r["month_estimate"]
        lines.append(f"At {m['long']} long + {m['short']} Shorts a month: about {_usd(m['usd'])} a month "
                     "(from the averages above)")
    lines.append(f"Rejected / failed videos (cost already included in the rows above): {_usd(r['wasted'])}")
    o, u = r["other"], r["unused_drafts"]
    lines.append(f"Not tied to a video (voice tests, checks): Claude {_usd(o['claude'])}, voice {_usd(o['voice'])}, "
                 f"images {_usd(o['images'])}")
    if sum(u.values()):
        lines.append(f"Scripts written but never made into a video: {_usd(sum(u.values()))}")
    g = r["ledgers"]
    lines.append(f"Budget ledgers for {g['month']} (everything billed this month, including before per-video "
                 f"tracking): Claude {_usd(g['claude'])}, voice {_usd(g['voice'])}, images {_usd(g['images'])}")
    return "\n".join(lines)


__all__ = ["build", "text", "DELIVERED", "WASTED"]

