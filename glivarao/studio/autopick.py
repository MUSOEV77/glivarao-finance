"""Automatic topic selection (TOPIC_MODE=auto, the default).

Rules, in order:
1. Fresh research: official news (Fed, CFPB, IRS), Google Trends, Google search questions, CFPB complaint trends,
   Stack Exchange questions and Wikipedia demand (see research/).
2. Ranking: research score (search interest and demand, curiosity, practical value, freshness, ...), with
   high/medium-confidence topics first.
3. No repeats: not the same topic, not the same topic family as the last 3 videos, and no angle similar to any
   of the last 30 videos.
4. Rotation: never the same category twice in a row, at most 2 of the last 7 videos per category.
The reasons (with source URLs) are kept and shown in Telegram so you can reject the whole video.
"""
from __future__ import annotations

import json
import re

from ..content.brief import family_of

RECENT_VIDEOS = 30
FAMILY_GAP = 3
ANGLE_SIMILAR = 0.5
STOP = set("the and for with your you that this what how why are from into about when they them more most "
           "than have has does will would could should their there here just like only over also".split())


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3 and w not in STOP}


def similarity(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def angle_text(card: dict) -> str:
    parts = [card.get("topic", "")] + card.get("specific_angles", [])[:2] + \
            [n["title"] for n in card.get("official_news", [])[:1]]
    return " ".join(parts)


def recent(store, n: int = RECENT_VIDEOS, key: str = "used_topics") -> list[list]:
    """Last n picks: [date, key, category, family, angle]."""
    return json.loads(store.kv_get(key, "[]"))[-n:]


def pick_topic(report: dict, store, free_writer: bool, history_key: str = "used_topics",
               recent_videos: int = RECENT_VIDEOS, family_gap: int = FAMILY_GAP,
               exclude: set[str] | None = None) -> tuple[dict | None, list[str], dict]:
    """history_key/recent_videos: long videos use the last 30 long topics; Shorts days use their own history
    (last 10 Shorts topics) because 90 Shorts a month can't all have a topic unused for 30 videos."""
    hist = recent(store, recent_videos, history_key)
    keys = {h[1] for h in hist} | set(exclude or ())
    fams = [h[3] for h in hist[-family_gap:] if len(h) > 3] if family_gap else []
    cats = [h[2] for h in hist[-7:] if len(h) > 2]
    last_cat = cats[-1] if cats else None
    angles = [h[4] for h in hist if len(h) > 4 and h[4]]
    skipped: dict[str, int] = {}

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    ranked = sorted(report.get("ranked", []), key=lambda c: ({"high": 0, "medium": 1}.get(c["confidence"], 2),
                                                             -c["score"]))
    for c in ranked:
        fam = family_of(c["key"])
        if c["key"] in keys:
            skip(f"covered in the last {recent_videos} videos")
            continue
        if free_writer and fam == "generic":
            skip("needs the Claude writer")
            continue
        if fam != "generic" and fam in fams:
            skip(f"same topic family as one of the last {FAMILY_GAP} videos")
            continue
        if c["category"] == last_cat:
            skip("same category as the previous video")
            continue
        if cats.count(c["category"]) >= 2:
            skip("category already used twice in the last 7 videos")
            continue
        sim = max((similarity(angle_text(c), a) for a in angles), default=0.0)
        if sim >= ANGLE_SIMILAR:
            skip(f"angle similar to a recent video ({sim:.0%} overlap)")
            continue
        why = [f"Ranked #{c.get('rank', report.get('ranked', []).index(c) + 1)} of {len(report.get('ranked', []))} finance topics in today's research "
               f"(score {c['score']}/100, {c['confidence']} confidence, sources: {', '.join(c.get('sources', []))})"]
        prac = c.get("scores", {}).get("practical", {}).get("value")
        if prac is not None:
            why.append(f"Practical value for viewers: {prac}/10")
        why += c.get("why", [])
        why.append(f"Category {c['category']}" + (f" (previous video: {last_cat})" if last_cat else ""))
        if skipped:
            why.append("Skipped higher-ranked topics: " + "; ".join(f"{n}× {r}" for r, n in skipped.items()))
        return c, why, skipped
    return None, [], skipped


__all__ = ["pick_topic", "similarity", "angle_text", "recent", "RECENT_VIDEOS"]
