"""Anti-repetition check: compares a new script with the channel's previous scripts on three axes.

* topic     - same topic in the same format within TOPIC_DAYS
* structure - the sequence of scene beats/headings (difflib ratio) vs previous scripts of the same format
* phrases   - share of the script's 8-word phrases already used in any previous script
              (the education-only disclaimer and the host's own words are excluded)
plus an exact/near-exact match on the opening line.

History lives in the job store (kv "script_history"), capped at the last 80 scripts.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..models import Script

DISCLAIMER = "this video is for education only and isn't financial advice"
TOPIC_DAYS = 60
HISTORY_MAX = 80
N = 8


def _norm(text: str) -> list[str]:
    t = text.lower().replace("’", "'").replace("*", "")
    t = t.replace(DISCLAIMER, " ")
    return re.findall(r"[a-z0-9$%']+", t)


def shingles(text: str, n: int = N) -> set[str]:
    w = _norm(text)
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def narration_for_check(script: Script) -> str:
    return " ".join(s.narration for s in script.scenes if s.beat != "creator")


def structure_of(script: Script) -> list[str]:
    return [s.beat or re.sub(r"\d+", "#", s.heading.lower()) for s in script.scenes]


@dataclass
class Similarity:
    ok: bool
    phrase_overlap: float = 0.0
    structure_ratio: float = 0.0
    reasons: list[str] = field(default_factory=list)
    repeated_phrases: list[str] = field(default_factory=list)

    def summary(self) -> str:
        head = "Originality: OK" if self.ok else "Originality: TOO SIMILAR"
        return (f"{head} (phrase overlap {self.phrase_overlap:.0%}, structure similarity {self.structure_ratio:.0%})"
                + ("".join(f"\n- {r}" for r in self.reasons)))


def load_history(store) -> list[dict]:
    return json.loads(store.kv_get("script_history", "[]"))


def entry(script: Script, topic_key: str, day: date) -> dict:
    return {"date": day.isoformat(), "topic_key": topic_key, "format": script.format, "style": script.style,
            "structure": structure_of(script), "intro": script.hook,
            "outro": script.scenes[-1].narration, "text": narration_for_check(script)[:30000]}


def record(store, script: Script, topic_key: str, day: date) -> None:
    hist = load_history(store)
    hist.append(entry(script, topic_key, day))
    store.kv_set("script_history", json.dumps(hist[-HISTORY_MAX:]))


def used_lines(store, last: int = 30) -> list[str]:
    """Openings and closings used recently (so templates rotate)."""
    out = []
    for h in load_history(store)[-last:]:
        out += [h.get("intro", ""), h.get("outro", "")]
    return [x for x in out if x]


def check(script: Script, topic_key: str, history: list[dict], day: date, max_phrase: float = 0.25,
          max_structure: float = 0.85) -> Similarity:
    sim = Similarity(ok=True)
    mine = shingles(narration_for_check(script))
    cutoff = (day - timedelta(days=TOPIC_DAYS)).isoformat()
    seen: set[str] = set()
    for h in history:
        seen |= shingles(h.get("text", ""))
        if h["format"] != script.format:
            continue
        if h["topic_key"] == topic_key and h.get("style") == script.style and h["date"] >= cutoff:
            sim.reasons.append(f"same topic in the same format on {h['date']}")
        if h.get("style") == script.style:
            r = difflib.SequenceMatcher(None, structure_of(script), h.get("structure", [])).ratio()
            sim.structure_ratio = max(sim.structure_ratio, r)
        if script.hook and h.get("intro") and \
                difflib.SequenceMatcher(None, script.hook.lower(), h["intro"].lower()).ratio() > 0.9:
            sim.reasons.append(f"opening line nearly identical to the video of {h['date']}")
    if mine:
        common = mine & seen
        sim.phrase_overlap = len(common) / len(mine)
        sim.repeated_phrases = sorted(common)[:12]
    if sim.phrase_overlap > max_phrase:
        sim.reasons.append(f"{sim.phrase_overlap:.0%} of its phrases were already used in earlier videos")
    if sim.structure_ratio > max_structure:
        sim.reasons.append(f"structure {sim.structure_ratio:.0%} identical to an earlier {script.style} video")
    sim.ok = not sim.reasons
    return sim


__all__ = ["check", "record", "entry", "load_history", "used_lines", "Similarity", "shingles"]
