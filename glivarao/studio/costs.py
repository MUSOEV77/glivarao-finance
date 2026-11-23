"""Real spend per video: every paid call (Claude script writing, Gemini voice, Nano Banana images) is logged with
the video it was made for, so `python -m glivarao cost-report` shows what each long video and each Short really
cost.

How a cost finds its video:
* While a video is being made, the code runs inside `costs.tag(job_id)`. Every amount the spend ledgers record
  (the same amounts the monthly budget uses) is also appended to `cost_events.jsonl` next to the ledgers, with
  that tag.
* Scripts are written before the video has an id. Each draft gets its own `draft:...` tag, carried on the script
  (`Script.cost_tag`). When the video is created, `link(draft, job_id)` ties that writing cost to it.
* A video rejected and rewritten (auto-retry) is linked to its replacement, so the final video carries the cost of
  the attempts it took.
* Spend outside a video (voice test, research, health checks) is reported as "not tied to a video".
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import time
import uuid
from pathlib import Path

KINDS = ("claude", "voice", "images")
_TAG: contextvars.ContextVar[str] = contextvars.ContextVar("glivarao_cost_tag", default="")
FILE = "cost_events.jsonl"


def current() -> str:
    return _TAG.get()


@contextlib.contextmanager
def tag(name: str | None):
    """Attribute every paid call inside this block to `name` (a job id, a draft tag, 'voice-test', ...)."""
    if not name:
        yield
        return
    token = _TAG.set(name)
    try:
        yield
    finally:
        _TAG.reset(token)


def new_draft(fmt: str) -> str:
    return f"draft:{fmt}:{uuid.uuid4().hex[:10]}"


def _append(directory: Path, row: dict) -> None:
    try:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        with open(directory / FILE, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:   # cost logging must never break production
        pass


def record(kind: str, usd: float, directory: Path) -> None:
    """Called by the spend ledgers for every billed call."""
    _append(directory, {"ts": round(time.time(), 1), "tag": current(), "kind": kind, "usd": round(float(usd), 6)})


def link(source: str | None, target: str, directory: Path) -> None:
    """Costs logged under `source` (a draft, or a rejected attempt) belong to `target`."""
    if source and source != target:
        _append(directory, {"ts": round(time.time(), 1), "link": source, "to": target})


def load(directories) -> tuple[list[dict], dict[str, str]]:
    events, links, seen = [], {}, set()
    for d in directories:
        p = (Path(d) / FILE).resolve()
        if p in seen or not p.exists():
            continue
        seen.add(p)
        for line in p.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if "link" in row:
                links[row["link"]] = row["to"]
            elif row.get("kind") in KINDS:
                events.append(row)
    return events, links


def resolve(name: str, links: dict[str, str]) -> str:
    hops = 0
    while name in links and hops < 20:
        name, hops = links[name], hops + 1
    return name


def per_tag(events: list[dict], links: dict[str, str], since: float = 0.0) -> dict[str, dict[str, float]]:
    """{final tag: {'claude': usd, 'voice': usd, 'images': usd}} for events at or after `since`."""
    out: dict[str, dict[str, float]] = {}
    for e in events:
        if e.get("ts", 0) < since:
            continue
        row = out.setdefault(resolve(e.get("tag") or "", links), {k: 0.0 for k in KINDS})
        row[e["kind"]] += float(e["usd"])
    return out


__all__ = ["tag", "current", "new_draft", "record", "link", "load", "resolve", "per_tag", "KINDS", "FILE"]
