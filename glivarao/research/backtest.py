"""Historical replay of the research run (accelerated validation).

Runs the same research as of past dates and measures ranking stability. This is a HISTORICAL TEST, not a
real daily observation:
  - CFPB windows and Wikipedia pageviews are replayed exactly as they were on each date.
  - Stack Exchange questions are limited to those that existed on the date, but their view counts are
    TODAY's (the API has no historical view counts), which slightly favours older questions.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .run import run_research


def overlap(a: list[str], b: list[str]) -> float:
    return len(set(a) & set(b)) / max(1, len(set(a) | set(b)))


def backtest(dates: list[date], out_dir: Path, top: int = 10) -> dict:
    runs = {}
    for d in dates:
        rep = run_research(d, out_dir / d.isoformat())
        runs[d.isoformat()] = {
            "top": [t["key"] for t in rep["ranked"][:top]],
            "labels": [t["topic"] for t in rep["ranked"][:top]],
            "recommended": rep.get("recommended"),
            "sources_ok": [s["name"] for s in rep["sources"] if s["ok"]],
            "rejected": len(rep["rejected_off_topic"]),
            "off_topic_reasons": sorted({r["reason"].split(" (")[0] for r in rep["rejected_off_topic"]}),
        }
    keys = sorted(runs)
    pairs = [{"from": a, "to": b, "top_overlap_jaccard": round(overlap(runs[a]["top"], runs[b]["top"]), 2)}
             for a, b in zip(keys, keys[1:])]
    always = set.intersection(*(set(runs[k]["top"]) for k in keys)) if keys else set()
    summary = {"kind": "HISTORICAL REPLAY (not real daily observations)", "dates": keys, "runs": runs,
               "consecutive_overlap": pairs, "in_top_every_time": sorted(always),
               "distinct_recommendations": sorted({r["recommended"] for r in runs.values() if r["recommended"]})}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "backtest_summary.json").write_text(json.dumps(summary, indent=2))
    return summary
