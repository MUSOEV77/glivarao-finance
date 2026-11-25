"""Less repetition across videos:
* worked-example numbers ($5,000 balance, $200 a month, ...) are not reused within 30 days: the writer is told
  which ones to avoid, and a reuse that slips through is a warning in the review (never a paid rewrite);
* research-picked topics are not repeated within 14 days (long videos and Shorts; batch parts are planned);
* Short formats rotate, so consecutive Shorts never use the same format.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

NUM = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?%")
SHORT_FORMATS = (
    "ONE surprising number from the fact sheet, with its own hook in the first two seconds",
    "ONE common myth and the fact that corrects it, with its own hook",
    "ONE mistake people make and what to do instead, with its own hook",
    "ONE quick tip the viewer can do in under five minutes today, with its own hook",
    "ONE side-by-side comparison (this vs that) built on a fact-sheet number, with its own hook",
    "ONE short story moment ('You open your statement and see ...') built on a fact-sheet number, with its own hook",
)


def _norm(n: str) -> str:
    return n.replace(" ", "").replace(",", "")


def example_numbers(script, facts: list[str] | None = None) -> set[str]:
    """The script's own example numbers: every $ amount or % in the narration that is NOT on the fact
    sheet (fact-sheet numbers may repeat; invented example inputs and results may not)."""
    sheet = {_norm(m.group(0)) for f in (facts or []) for m in NUM.finditer(f)}
    text = " ".join(sc.narration for sc in script.scenes)     # charts are checked against the fact sheet
    return {_norm(m.group(0)) for m in NUM.finditer(text)} - sheet


def recent_examples(store, day: date, days: int = 30) -> set[str]:
    cut = (day - timedelta(days=days)).isoformat()
    return {n for d, n in json.loads(store.kv_get("example_numbers", "[]")) if d >= cut}


def record_examples(store, script, day: date, facts: list[str] | None = None) -> None:
    rows = json.loads(store.kv_get("example_numbers", "[]")) + [[day.isoformat(), n]
                                                                 for n in sorted(example_numbers(script, facts))]
    store.kv_set("example_numbers", json.dumps(rows[-2000:]))


def example_issues(script, store, day: date, facts: list[str] | None = None) -> list[str]:
    """Two or more example numbers that another video used in the last 30 days = the same example again."""
    again = sorted(example_numbers(script, facts) & recent_examples(store, day))
    return ([f"reuses an example from the last 30 days ({', '.join(again)}): use a different worked example"]
            if len(again) >= 2 else [])


def topic_issues(script, brief) -> list[str]:
    """The script must be about its picked topic: the topic's key words appear in the title or the first scenes."""
    stop = set("the a an and or of to in on for is are your you how why what with from at by be as it this".split())
    want = {w[:5] for w in re.findall(r"[a-z]+", f"{brief.topic} {brief.topic_key.replace('_', ' ')}".lower())
            if len(w) > 3 and w not in stop}
    text = f"{script.title} " + " ".join(sc.narration for sc in script.scenes[:2])
    have = {w[:5] for w in re.findall(r"[a-z]+", text.lower())}
    return [] if not want or want & have else [f"not about its topic \"{brief.topic}\": say what it is about in the "
                                                "title and the first scene"]


def recent_topics(store, day: date, days: int = 14) -> set[str]:
    cut = (day - timedelta(days=days)).isoformat()
    keys = set()
    for k in ("used_topics", "used_short_topics"):
        keys |= {h[1] for h in json.loads(store.kv_get(k, "[]")) if h[0] >= cut}
    return keys


def next_short_formats(store, n: int) -> list[str]:
    """The next n Short formats in rotation (consecutive Shorts never share a format)."""
    i = int(store.kv_get("short_format_idx", "0"))
    store.kv_set("short_format_idx", str(i + n))
    return [SHORT_FORMATS[(i + k) % len(SHORT_FORMATS)] for k in range(n)]


__all__ = ["example_numbers", "recent_examples", "record_examples", "example_issues", "recent_topics",
           "next_short_formats", "SHORT_FORMATS"]
