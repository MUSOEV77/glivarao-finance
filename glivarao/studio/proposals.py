"""Weekly topic ideas: research ranks finance topics; you get 5-7 of them in Telegram and pick what gets made."""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from ..content.brief import family_of
from ..content.writer import paid_writer_allowed
from .queue import TopicQueue

log = logging.getLogger(__name__)


def candidates(report: dict, exclude: set[str], n: int, free_writer: bool, max_per_category: int = 2) -> list[dict]:
    """Top-ranked, varied ideas: no repeats from the last 90 days, at most 2 per category."""
    out, per_cat = [], {}
    for c in sorted(report.get("ranked", []), key=lambda c: ({"high": 0, "medium": 1}.get(c["confidence"], 2),
                                                             -c["score"])):
        if c["key"] in exclude or (free_writer and family_of(c["key"]) == "generic"):
            continue
        if per_cat.get(c["category"], 0) >= max_per_category:
            continue
        out.append(c)
        per_cat[c["category"]] = per_cat.get(c["category"], 0) + 1
        if len(out) >= n:
            break
    return out


def propose_topics(settings, store, today: date | None = None, research_dir: Path | None = None,
                   send: bool = True, client=None):
    from ..research.run import run_research

    today = today or date.today()
    research_dir = research_dir or Path("reports/research")
    cached = research_dir / f"{today.isoformat()}.json"
    report = json.loads(cached.read_text()) if cached.exists() else run_research(today, research_dir, store)
    hist = json.loads(store.kv_get("used_topics", "[]"))
    cutoff = (today - timedelta(days=90)).isoformat()
    exclude = {h[1] for h in hist if h[0] >= cutoff}
    n = max(5, min(7, settings.topic_ideas_per_week))
    picks = candidates(report, exclude, n, free_writer=not paid_writer_allowed(settings))
    items = TopicQueue(store).add_proposals(picks, today)
    if send and items and settings.telegram_bot_token and settings.telegram_approver_chat_id:
        from ..publish.telegram import _client
        from .bot import send_proposals

        send_proposals(items, settings, _client(settings, client), store)
    return items


__all__ = ["propose_topics", "candidates"]
