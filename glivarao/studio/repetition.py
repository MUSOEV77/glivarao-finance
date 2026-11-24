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


def example_numbers(script) -> set[str]:
    """Numbers used in the script's worked examples (labeled sentences)."""
    from .factcheck import EXAMPLE_RE

    out = set()
    for sc in script.scenes:
        for s in re.split(r"(?<=[.!?])\s+", sc.narration):
            if EXAMPLE_RE.search(s):
                out |= {_norm(m.group(0)) for m in NUM.finditer(s)}
    return out


def recent_examples(store, day: date, days: int = 30) -> set[str]:
    cut = (day - timedelta(days=days)).isoformat()
    return {n for d, n in json.loads(store.kv_get("example_numbers", "[]")) if d >= cut}


def record_examples(store, script, day: date) -> None:
    rows = json.loads(store.kv_get("example_numbers", "[]")) + [[day.isoformat(), n]
                                                                 for n in sorted(example_numbers(script))]
    store.kv_set("example_numbers", json.dumps(rows[-2000:]))


def example_issues(script, store, day: date) -> list[str]:
    again = sorted(example_numbers(script) & recent_examples(store, day))
    return [f"worked-example number(s) used in the last 30 days: {', '.join(again)}"] if again else []


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
