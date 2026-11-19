"""Automatic topic selection (TOPIC_MODE=auto, the default).

Rules, in order:
1. Fresh research: official news (Fed, CFPB, IRS), Google Trends, Google search questions, CFPB complaint trends,
   Stack Exchange questions and Wikipedia demand (see research/).
2. Ranking: research score (search interest and demand, curiosity, practical value, freshness, ...), with
   high/medium-confidence topics first.
3. No repeats: not the same topic, not the same topic family as the last 3 videos, and no angle similar to any
   of the last 30 videos.
4. Channel focus (studio/pillars.py): every topic must fit one of the 5 pillars; anything else is rejected.
   Pillars rotate: never the same pillar twice in a row, at most 2 of the last 5 videos per pillar (taxes: 3 in
   December-April), and pillars not covered recently (and taxes in tax season) are preferred.
The reasons (with source URLs) are kept and shown in Telegram so you can reject the whole video.
"""
from __future__ import annotations

import json
import re
from datetime import date

from ..content.brief import family_of
from . import pillars as P

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


DEBT_REPEAT_GAP = 8   # a debt/credit topic may return after 8 long videos (new angle); others after 30


def pick_topic(report: dict, store, free_writer: bool, history_key: str = "used_topics",
               recent_videos: int = RECENT_VIDEOS, family_gap: int = FAMILY_GAP,
               exclude: set[str] | None = None, today: date | None = None) -> tuple[dict | None, list[str], dict]:
    """history_key/recent_videos: long videos use the last 30 long topics; Shorts days use their own history
    (last 10 Shorts topics) because 90 Shorts a month can't all have a topic unused for 30 videos.
    Long videos also follow the channel focus: >= 60% debt and credit, at most 1 news video in 4, evergreen
    preferred."""
    long_video = history_key == "used_topics"
    hist = recent(store, recent_videos, history_key)
    focus_keys = P.PILLARS[P.FOCUS_PILLAR].concepts
    keys = {h[1] for h in hist if not (long_video and h[1] in focus_keys)} | set(exclude or ())
    keys |= {h[1] for h in hist[-DEBT_REPEAT_GAP:]} if long_video else set()
    fams = [h[3] for h in hist[-family_gap:] if len(h) > 3] if family_gap else []
    today = today or date.today()
    recent_pillars = [p.key for p in (P.pillar_of(h[1]) for h in hist) if p is not None]
    last_pillar = P.PILLARS[recent_pillars[-1]].name if recent_pillars else None
    angles = [h[4] for h in hist if len(h) > 4 and h[4]]
    recent_news = any(len(h) > 5 and h[5] for h in hist[-(P.NEWS_EVERY - 1):])
    skipped: dict[str, int] = {}

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    all_ranked = report.get("ranked", [])
    bonus = {}
    for c in all_ranked:
        p = P.pillar_of(c["key"])
        b, note = P.priority_bonus(p, recent_pillars, today) if p else (0.0, "")
        if long_video and c.get("type") == "evergreen":
            b += P.EVERGREEN_BONUS
        bonus[c["key"]] = (b, note)
    ranked = sorted(all_ranked, key=lambda c: ({"high": 0, "medium": 1}.get(c["confidence"], 2),
                                               -(c["score"] + bonus[c["key"]][0])))
    must_focus = long_video and P.needs_focus(recent_pillars)

    def first_ok(only_focus: bool | None):
        for c in ranked:
            pillar = P.pillar_of(c["key"])
            if only_focus is True and (pillar is None or pillar.key != P.FOCUS_PILLAR):
                continue
            fam = family_of(c["key"])
            off = P.rejection(c)
            if off:
                skip(off)
                continue
            if c["key"] in keys:
                skip(f"covered in the last {DEBT_REPEAT_GAP if c['key'] in focus_keys and long_video else recent_videos} videos")
                continue
            if free_writer and fam == "generic":
                skip("needs the Claude writer")
                continue
            recent_fams = fams[-1:] if ((fam == "tax" and P.tax_season(today)) or
                                        (long_video and pillar.key == P.FOCUS_PILLAR)) else fams
            if fam != "generic" and fam in recent_fams:
                skip(f"same topic family as one of the last {FAMILY_GAP} videos")
                continue
            blocked = P.rotation_block(pillar, recent_pillars, today, focus=long_video)
            if blocked:
                skip(blocked)
                continue
            if long_video and P.is_news(c) and recent_news:
                skip(f"news limit: at most 1 news video in {P.NEWS_EVERY} long videos")
                continue
            sim = max((similarity(angle_text(c), a) for a in angles), default=0.0)
            if sim >= ANGLE_SIMILAR:
                skip(f"angle similar to a recent video ({sim:.0%} overlap)")
                continue
            return c, pillar
        return None, None

    c, pillar = first_ok(True if must_focus else None)
    focus_note = ""
    if must_focus:
        focus_note = "Channel focus: debt and credit (at least 3 of every 5 long videos)"
        if c is None:
            c, pillar = first_ok(None)
            focus_note = "No debt/credit topic passed today's checks, so another pillar was used"
    if c is None:
        return None, [], skipped
    why = [f"Pillar: {pillar.name} ({pillar.short})" + (f"; previous video: {last_pillar}" if last_pillar else ""),
           f"Ranked #{c.get('rank', all_ranked.index(c) + 1)} of {len(all_ranked)} finance topics in today's research "
           f"(score {c['score']}/100, {c['confidence']} confidence, sources: {', '.join(c.get('sources', []))})"]
    if focus_note:
        why.insert(1, focus_note)
    if long_video:
        why.append("Type: " + ("news-driven (max 1 in 4 long videos)" if P.is_news(c) else
                               f"{c.get('type') or 'evergreen'} (preferred)"))
    prac = c.get("scores", {}).get("practical", {}).get("value")
    if prac is not None:
        why.append(f"Practical value for viewers: {prac}/10")
    why += c.get("why", [])
    if bonus[c["key"]][1]:
        why.append(f"Pillar rotation: {bonus[c['key']][1]}")
    series = P.series_for(c["key"], today)
    if series:
        why.append(f"Series: {series}")
    if skipped:
        why.append("Skipped higher-ranked topics: " + "; ".join(f"{n}× {r}" for r, n in skipped.items()))
    return c, why, skipped


__all__ = ["pick_topic", "similarity", "angle_text", "recent", "RECENT_VIDEOS"]
