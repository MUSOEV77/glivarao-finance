"""Recurring series, YouTube links and your affiliate links (all stored in the kv table; set from Telegram).

* An approved video becomes an episode of its series when its upload pack is sent.
* After you upload, reply to the upload pack with the YouTube link (or just send the link): later episodes then
  link to it in their description, and the pack tells you which video to put on the end screen.
* /playlist <series> <link>  saves the series playlist (created once by you in YouTube Studio).
* Affiliate links: see studio/affiliates.py (/affiliate <program> <link>).
"""
from __future__ import annotations

import json
import re
from datetime import date

from .pillars import all_series_names

YOUTUBE_VIDEO = re.compile(r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[\w\-?=&]+$")
YOUTUBE_PLAYLIST = re.compile(r"^https?://(?:www\.|m\.)?youtube\.com/playlist\?list=[\w\-]+$")
HTTPS_URL = re.compile(r"^https://[^\s<>\"]+$")
MAX_LINKED = 4


def _get(store, key: str, default):
    return json.loads(store.kv_get(key, json.dumps(default)))


def _set(store, key: str, value) -> None:
    store.kv_set(key, json.dumps(value))


# ------------------------------------------------------------------------------------------------- episodes
def episodes(store, series: str | None = None) -> list[dict]:
    eps = _get(store, "series_episodes", [])
    return [e for e in eps if series is None or e["series"] == series]


def record_episode(store, job_id: str, series: str, pillar: str, title: str, fmt: str, day: date) -> dict:
    """Idempotent: re-sending a pack never adds the same video twice."""
    eps = _get(store, "series_episodes", [])
    for e in eps:
        if e["job"] == job_id:
            return e
    n = sum(1 for e in eps if e["series"] == series and e["format"] == fmt) + 1
    e = {"job": job_id, "series": series, "pillar": pillar, "title": title, "format": fmt, "date": day.isoformat(),
         "episode": n, "url": ""}
    _set(store, "series_episodes", (eps + [e])[-1000:])
    return e


def ensure_episode(store, job, settings=None) -> dict:
    """Register a video as an episode if it isn't one yet (videos made by render-draft, batch-make or by hand):
    its series = the metadata series, else its batch topic's series, else 'Single videos'."""
    import json as _json
    from pathlib import Path as _P

    for e in _get(store, "series_episodes", []):
        if e["job"] == job.id:
            return e
    meta = {}
    if job.video_path and (_P(job.video_path).parent / "metadata.json").exists():
        meta = _json.loads((_P(job.video_path).parent / "metadata.json").read_text())
    series = meta.get("series")
    if not series:
        from . import batch

        for t in batch.topics(store):
            if job.id in [j["job"] for j in batch.topic_jobs(store, t.slug)]:
                series = t.series
                break
    title = (meta.get("title_options") or [meta.get("title") or job.topic])[0]
    fmt = getattr(job.format, "value", str(job.format))
    return record_episode(store, job.id, series or "Single videos", meta.get("pillar") or "", title, fmt,
                          date.fromisoformat(job.created_at[:10]) if job.created_at else date.today())


def backfill_episodes(store) -> list[str]:
    """Every approved or published video gets an episode record (so its YouTube link can be saved)."""
    from ..models import JobStatus

    have = {e["job"] for e in _get(store, "series_episodes", [])}
    added = []
    for st in (JobStatus.APPROVED, JobStatus.PUBLISHED):
        for job in store.list(st, limit=1000):
            if job.id not in have:
                ensure_episode(store, job)
                added.append(job.id)
    return added


def set_link(store, job_id: str, url: str) -> dict | None:
    eps = _get(store, "series_episodes", [])
    for e in eps:
        if e["job"] == job_id:
            e["url"] = url
            _set(store, "series_episodes", eps)
            return e
    try:                                   # not an episode yet (render-draft, by hand): register it, then save
        job = store.get(job_id)
    except KeyError:
        return None
    ensure_episode(store, job)
    return set_link(store, job_id, url)


def next_episode_number(store, series: str, fmt: str = "long") -> int:
    return sum(1 for e in episodes(store, series) if e["format"] == fmt) + 1


def linked_episodes(store, series: str, exclude_job: str = "", fmt: str | None = "long") -> list[dict]:
    """Most recent first: published episodes of a series that have a YouTube link."""
    eps = [e for e in episodes(store, series) if e["url"] and e["job"] != exclude_job
           and (fmt is None or e["format"] == fmt)]
    return list(reversed(eps))[:MAX_LINKED]


def unlinked_target(store, url: str) -> dict | None:
    """The episode a bare link (not a reply) most likely belongs to: the newest one without a link, matching
    Shorts links to Shorts."""
    want = "short" if "/shorts/" in url else None
    for e in reversed(episodes(store)):
        if not e["url"] and (want is None or e["format"] == want):
            return e
    return None


# ------------------------------------------------------------------------------------------- playlists / links
def playlists(store) -> dict[str, str]:
    return _get(store, "series_playlists", {})


def set_playlist(store, series: str, url: str) -> None:
    pl = playlists(store)
    pl[series] = url
    _set(store, "series_playlists", pl)






def resolve_series(store, text: str, today: date) -> str | None:
    """Case-insensitive match against current series names and any series that already has episodes."""
    t = " ".join(text.lower().split())
    names = all_series_names(today) + [e["series"] for e in episodes(store)]
    return next((n for n in names if n.lower() == t), None)


# ------------------------------------------------------------------------------------------------ text blocks
def description_blocks(store, job_id: str, series: str | None, pillar: str | None, fmt: str,
                       topic_key: str = "") -> tuple[str, str]:
    """(series block, affiliate block) to insert in the description. Either may be empty.
    Affiliates: 1-2 approved programs for long videos only (studio/affiliates.py)."""
    from . import affiliates

    series_txt = ""
    if series:
        lines = [f"📺 Series: {series}"]
        prev = linked_episodes(store, series, exclude_job=job_id)
        if prev:
            lines.append("More episodes:")
            lines += [f"▶ {e['title']}: {e['url']}" for e in prev]
        pl = playlists(store).get(series)
        if pl:
            lines.append(f"Full playlist: {pl}")
        series_txt = "\n".join(lines) if (prev or pl or fmt == "long") else ""
    aff_txt = ""
    links, _ = affiliates.for_video(store, topic_key, pillar, fmt)
    if links:
        aff_txt = "\n".join(["Helpful tools (affiliate links: I may earn a commission at no extra cost to you):"]
                            + [f"• {n}: {u}" for n, u in links])
    return series_txt, aff_txt


def insert_blocks(description: str, blocks: list[str], disclosure: str) -> str:
    """Put the series/affiliate blocks just above the disclosure (so the disclosure sits next to the links),
    or at the end. Keeps YouTube's 5,000-character limit."""
    add = "\n\n".join(b for b in blocks if b)
    if not add:
        return description
    if disclosure and disclosure in description:
        i = description.index(disclosure)
        out = description[:i].rstrip() + "\n\n" + add + "\n\n" + description[i:]
    else:
        out = description.rstrip() + "\n\n" + add
    return out if len(out) <= 5000 else description


def end_screen_advice(store, job_id: str, series: str | None, fmt: str) -> str:
    if fmt != "long":
        prev = linked_episodes(store, series, exclude_job=job_id) if series else []
        target = prev[0] if prev else next((e for e in reversed(episodes(store)) if e["format"] == "long"
                                            and e["url"] and e["job"] != job_id), None)
        if target:
            return (f"RELATED VIDEO (Shorts → Related video in YouTube Studio):\n{target['title']}\n{target['url']}")
        return "RELATED VIDEO: none yet. Once a long video has its YouTube link saved, I'll suggest it here."
    prev = linked_episodes(store, series, exclude_job=job_id) if series else []
    lines = ["END SCREEN (Editor → End screen, last 20 seconds):"]
    if prev:
        lines.append(f"• Video → Choose specific video → \"{prev[0]['title']}\" ({prev[0]['url']})")
    else:
        lines.append("• Video → Best for viewer (no earlier episode of this series has a link yet)")
    pl = playlists(store).get(series or "")
    lines.append(f"• Playlist → \"{series}\"" + (f" ({pl})" if pl else " (create it once in YouTube Studio, then "
                                                                       f"send /playlist {series} <link>)"))
    lines.append("• Subscribe")
    if series:
        lines.append(f"Also add the video to the \"{series}\" playlist when you upload.")
    return "\n".join(lines)


def status_text(store, today: date) -> str:
    lines = ["📺 Series"]
    eps = episodes(store)
    pl = playlists(store)
    for name in all_series_names(today):
        mine = [e for e in eps if e["series"] == name]
        linked = sum(1 for e in mine if e["url"])
        lines.append(f"• {name}: {len(mine)} approved, {linked} with YouTube link"
                     + (" · playlist ✓" if name in pl else ""))
    lines += ["", "Reply to an upload pack with the video's YouTube link after you upload it.",
              "Playlist: /playlist <series name> <playlist link>"]
    return "\n".join(lines)



__all__ = ["record_episode", "set_link", "episodes", "linked_episodes", "next_episode_number", "description_blocks",
           "insert_blocks", "end_screen_advice", "status_text", "set_playlist", "playlists", "unlinked_target",
           "YOUTUBE_VIDEO", "YOUTUBE_PLAYLIST", "HTTPS_URL"]
