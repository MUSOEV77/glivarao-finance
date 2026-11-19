"""Upload pack: everything you need to upload an approved video yourself from the YouTube Studio phone app.

Sent to Telegram right after you tap ✅ Approve (or with /pack JOB_ID, or the "Send upload pack again" button):
  1. the FULL-QUALITY video as a file (sent as a document so Telegram never recompresses it). Needs the local
     Bot API server for files over 50 MB (long videos); see docs/TELEGRAM_LARGE_FILES.md
  2. the full-quality thumbnail (document)
  3. three title options, the full description (sources, AI note, affiliate disclosure), tags
  4. the suggested publish time in New York and Tashkent time, for YouTube Studio's "Schedule"
  5. series: links to earlier episodes in the description, end-screen / related-video advice, playlist; and the
     pillar's affiliate links that YOU added with /affiliate (just above the disclosure)
After uploading, reply to the pack with the YouTube link so later episodes can link to this one.
Text blocks are sent as <pre>/<code> so one tap copies them on a phone. Nothing is uploaded or scheduled here.
"""
from __future__ import annotations

import html
import json
import logging
from datetime import date
from pathlib import Path

from . import series as S
from .publish_times import describe, next_slot

log = logging.getLogger(__name__)
TAGS_LIMIT = 500          # YouTube's limit for all tags together
MSG_LIMIT = 3800          # Telegram allows 4096 characters per message; keep room for the labels


def _e(text: str) -> str:
    return html.escape(text, quote=False)


def tags_line(tags: list[str]) -> str:
    out, total = [], 0
    for t in dict.fromkeys(x.strip() for x in tags if x.strip()):
        add = len(t) + (2 if out else 0)
        if total + add > TAGS_LIMIT:
            break
        out.append(t)
        total += add
    return ", ".join(out)


def _chunks(text: str, n: int = MSG_LIMIT) -> list[str]:
    parts, cur = [], ""
    for para in text.split("\n"):
        if len(cur) + len(para) + 1 > n and cur:
            parts.append(cur)
            cur = ""
        cur = f"{cur}\n{para}" if cur else para
    return parts + ([cur] if cur else [])


def build_pack(job, settings, store) -> dict:
    out = Path(job.video_path).parent
    meta = json.loads((out / "metadata.json").read_text())
    titles = meta.get("title_options") or [meta["title"]]
    slot = next_slot(store, job.format, settings, job_id=job.id)
    series, pillar = meta.get("series"), meta.get("pillar")
    episode = None
    if series:
        episode = S.record_episode(store, job.id, series, pillar or "", titles[0], job.format,
                                   slot.date() if slot else date.today())
    blocks = S.description_blocks(store, job.id, series, pillar, job.format)
    description = S.insert_blocks(meta["description"], list(blocks), settings.affiliate_disclosure)
    return {"job": job.id, "format": job.format, "titles": titles, "description": description,
            "series": series, "episode": episode, "end_screen": S.end_screen_advice(store, job.id, series, job.format),
            "tags": tags_line(meta.get("tags", [])), "video": Path(job.video_path),
            "thumbnail": Path(job.thumbnail_path) if job.thumbnail_path else None, "slot": slot,
            "when": describe(slot), "duration": job.duration_sec}


def send_pack(job, settings, store, client=None) -> dict:
    from ..publish.telegram import _client

    c = _client(settings, client)
    chat = settings.telegram_approver_chat_id
    p = build_pack(job, settings, store)
    kind = "LONG VIDEO" if p["format"] == "long" else "SHORT"
    send = lambda text, **kw: c.call("sendMessage", chat_id=chat, text=text, parse_mode="HTML",  # noqa: E731
                                     disable_web_page_preview=True, **kw)
    ep = p["episode"]
    series_line = (f"Series: <b>{_e(p['series'])}</b> (episode {ep['episode']})\n" if ep else "")
    send(f"📦 <b>UPLOAD PACK — {kind}</b> ({_e(job.id)})\n{series_line}"
         f"Schedule it in YouTube Studio for:\n<b>{_e(p['when'])}</b>\n\n"
         "Steps: save the video file below → YouTube Studio app → ＋ → choose the video → paste the title, "
         "description and tags → set the thumbnail → Visibility → Schedule → enter the time above.\n"
         "Tap any grey block to copy it.")
    size_mb = p["video"].stat().st_size / 1024 / 1024
    limit_mb = settings.telegram_max_upload_mb - 1
    if size_mb <= limit_mb:
        with open(p["video"], "rb") as fh:
            c.call("sendDocument", files={"document": (p["video"].name if p["format"] == "short"
                                                       else f"{job.id}.mp4", fh)},
                   chat_id=chat, caption=f"Full-quality video ({size_mb:.0f} MB). Save it: tap ⋮ → Save to "
                                         "Downloads / Save to gallery.")
        video_note = "sent"
    else:
        send(f"⚠️ The full-quality file is {size_mb:.0f} MB, above this bot's {settings.telegram_max_upload_mb} MB "
             "limit. Set up the local Telegram Bot API server (up to 2,000 MB, see docs/TELEGRAM_LARGE_FILES.md); "
             f"until then the file is on the server at {_e(str(p['video']))}.")
        video_note = "too large for this bot server"
    if p["thumbnail"] and p["thumbnail"].exists():
        with open(p["thumbnail"], "rb") as fh:
            c.call("sendDocument", files={"document": (f"{job.id}_thumbnail.jpg", fh)}, chat_id=chat,
                   caption="Full-quality thumbnail (1280×720)" if p["format"] == "long" else
                   "Cover image (optional for Shorts)")
    for i, t in enumerate(p["titles"], 1):
        label = "TITLE (recommended)" if i == 1 else f"TITLE option {i}"
        send(f"<b>{label}</b>\n<code>{_e(t)}</code>")
    parts = _chunks(p["description"])
    for i, part in enumerate(parts, 1):
        label = "DESCRIPTION" + (f" (part {i}/{len(parts)}, paste in order)" if len(parts) > 1 else "")
        send(f"<b>{label}</b>\n<pre>{_e(part)}</pre>")
    send(f"<b>TAGS</b> ({len(p['tags'])}/500 characters)\n<pre>{_e(p['tags'])}</pre>")
    send(f"🔗 <b>{'END SCREEN' if p['format'] == 'long' else 'RELATED VIDEO'}</b>\n{_e(p['end_screen'])}")
    last = send(f"🕒 <b>PUBLISH TIME</b>\n{_e(p['when'])}\nIn YouTube Studio: Visibility → Schedule → set this date "
                "and time (Studio shows your phone's time zone).\n\n"
                "After uploading, <b>reply to this message with the YouTube link</b> so the next episodes can link "
                "to it.",
                reply_markup={"inline_keyboard": [[{"text": "📦 Send upload pack again",
                                                    "callback_data": f"pack:{job.id}"}]]})
    mid = (last or {}).get("message_id") if isinstance(last, dict) else None
    if mid is not None:
        msgs = json.loads(store.kv_get("pack_messages", "{}"))
        msgs[str(mid)] = job.id
        store.kv_set("pack_messages", json.dumps(dict(list(msgs.items())[-500:])))
    return {"video": video_note, "slot": p["slot"].isoformat(), "titles": len(p["titles"]), "parts": len(parts)}


__all__ = ["send_pack", "build_pack", "tags_line"]
