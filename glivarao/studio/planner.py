"""Plans the next video automatically: fresh research -> pick a topic (studio/autopick.py) -> pick a format
(rotation) -> announce it in Telegram with why it was picked and its sources -> ask for your take.

Runs every evening (glivarao-plan.timer) and, as a fallback, at the start of a production run. Your take is
optional in auto mode: if you reply before CREATOR_INPUT_WAIT_HOURS pass it goes in as "My take"; otherwise the
video is made without it (and the review says so).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from ..content.brief import build_brief, family_of
from ..content.writer import paid_writer_allowed
from .autopick import angle_text, pick_topic
from .bot import format_history, push_format
from .formats import FORMATS, choose_format
from .queue import TopicQueue

log = logging.getLogger(__name__)


def active_item(store):
    q = TopicQueue(store)
    return next((i for i in q.items() if i.status in ("awaiting_input", "ready")), None)


def announce(item, settings, client=None) -> None:
    if not (settings.telegram_bot_token and settings.telegram_approver_chat_id):
        return
    from ..publish.telegram import _client

    fmt = FORMATS[item.format]
    wait = settings.creator_input_wait_hours
    from .pillars import pillar_of, series_for

    p = pillar_of(item.key)
    s = series_for(item.key, date.fromisoformat(item.proposed_on) if item.proposed_on else date.today())
    lines = [f"🗓 Next video, picked automatically: \"{item.topic}\"",
             f"Pillar: {p.name if p else '?'}" + (f" · Series: {s}" if s else ""),
             f"Format: {fmt.label} ({fmt.summary})", "", "Why this topic:"]
    lines += [f"• {w}" for w in item.why[:8]]
    lines += ["", ("Want to add your own take (an opinion, experience or example)? Reply to this message with text "
                   f"or a voice note within {wait:g} hours and it goes into the video as \"My take\". "
                   "Otherwise the video is made without it.") if wait > 0 else
              "Reply with your own take any time before production to include it.",
              "You can still reject the whole video when the review arrives."]
    from . import quiet

    if quiet.is_quiet(settings):  # announced at 09:00 normally; a night-time plan waits for the morning
        from ..storage import JobStore

        quiet.queue_text(JobStore(settings.db_path), "\n".join(lines)[:3800])
        return None
    c = _client(settings, client)
    msg = c.call("sendMessage", chat_id=settings.telegram_approver_chat_id, text="\n".join(lines)[:4000],
                 disable_web_page_preview=True, reply_markup={"inline_keyboard": [[
                     {"text": "🔁 Other format", "callback_data": f"fmt:{item.id}"},
                     {"text": "⏭ Skip this topic", "callback_data": f"drop:{item.id}"}]]})
    return msg


def plan_next(settings, store, today: date | None = None, research_dir: Path | None = None, send: bool = True,
              client=None):
    """Returns the planned queue item (or the one already waiting), or None if no eligible topic exists."""
    from .pause import guard

    guard(settings, "planning the next topic")
    from ..daily_v2 import _mark_used, _notify
    from ..research.run import run_research

    existing = active_item(store)
    if existing is not None:
        return existing
    today = today or date.today()
    research_dir = research_dir or Path("reports/research")
    cached = research_dir / f"{today.isoformat()}.json"
    from . import batch, launch_plan
    from .pillars import is_news

    bentry = batch.next_long(store) if batch.active(store) else None
    if bentry is not None and launch_plan.awaiting_approval(store):
        pass                         # batch testing replaces the launch-list order (batch 1 approved by you)
    elif launch_plan.awaiting_approval(store):  # the US-only launch list waits for your ✅ in Telegram
        key = f"launch_wait_alert:{today.isoformat()}"
        if send and not store.kv_get(key):
            store.kv_set(key, "1")
            _notify(settings, "🇺🇸 GLIVARAO: the launch list is waiting for your approval, so no topic is planned. "
                              "Tap ✅ under the list (resend it: python -m glivarao launch-list --send).")
        return None
    launch = None if bentry is not None else launch_plan.next_video(store)
    if bentry is not None:   # BATCH TEST: the next part (never the same topic twice in a row), facts re-checked
        card = batch.card_for(store, bentry)
        from .launch_plan import LaunchFact, verify_fact_list

        kept, notes = verify_fact_list([LaunchFact(**f) for f in card["launch_facts"]])
        from dataclasses import asdict as _asdict

        card["launch_facts"] = [_asdict(f) for f in kept]
        why = list(card["why"]) + [f"Official facts: {len(kept)} checked on the source pages"]
        why += [f"⚠ {f.text[:90]}… — {note}" for f, note in notes]
        skipped = {}
    elif launch is not None:  # your launch list comes first (16 long videos), facts re-checked on official pages
        from dataclasses import replace as _replace

        kept, notes = launch_plan.verify_facts(launch)
        card = _replace(launch, facts=kept).card()  # a copy: the launch list itself is never modified
        why = list(card["why"]) + [f"Official facts: {len(kept)} checked on the source pages"]
        why += [f"⚠ {f.text[:90]}… — {note}" for f, note in notes]
        skipped = {}
    else:
        report = json.loads(cached.read_text()) if cached.exists() else run_research(today, research_dir, store)
        from .repetition import recent_topics

        card, why, skipped = pick_topic(report, store, free_writer=not paid_writer_allowed(settings), today=today,
                                        exclude=recent_topics(store, today))
    if card is None:
        log.warning("no eligible topic today (%s)", skipped)
        if send:
            _notify(settings, "GLIVARAO: no topic passed today's checks (5 pillars, no repeats, rotation). "
                              f"Skipped: {skipped}. I'll try again with tomorrow's research.")
        return None
    brief = build_brief(card, today)
    from .formats import eligible

    hist = format_history(store)
    want = (card["batch"]["format"] if bentry is not None else launch.format if launch is not None else "")
    style = (want if want in eligible(brief) and (not hist or hist[-1] != want)   # never the last video's structure
             else choose_format(brief, hist))
    push_format(store, style)
    q = TopicQueue(store)
    item = q.add_proposals([card], today)[0]
    status = "awaiting_input" if settings.creator_input_wait_hours > 0 else "ready"
    item = q.update(item.id, status=status, format=style, auto=True, why=why,
                    picked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    _mark_used(store, today, card["key"], card["category"], family_of(card["key"]), angle_text(card),
               news=is_news(card))
    if launch is not None:
        launch_plan.mark_done(store, launch.n)
    if bentry is not None:
        batch.mark_planned(store, bentry["id"])
    if send:
        try:
            msg = announce(item, settings, client)
            if msg:
                q.update(item.id, input_msg_id=msg.get("message_id"))
        except Exception as exc:  # noqa: BLE001  the announcement is helpful, not essential
            log.warning("could not announce the next topic: %s", exc)
    return q.get(item.id)


def input_window_over(item, settings, now: datetime | None = None) -> bool:
    if not item.picked_at:
        return True
    now = now or datetime.now(timezone.utc)
    age_h = (now - datetime.fromisoformat(item.picked_at)).total_seconds() / 3600
    return age_h >= settings.creator_input_wait_hours


__all__ = ["plan_next", "announce", "active_item", "input_window_over"]
