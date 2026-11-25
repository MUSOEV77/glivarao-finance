"""True documented money stories (official records only: SEC, FDIC, Federal Reserve, court records) for the
STORY format ("money story + what it means for your wallet"). Max narrates; no real people are drawn. A topic
gets the story format only when a story for it is on file here (never invented). Checked 2026-11-25."""
from __future__ import annotations

from .launch_plan import CRISIS_BANKS, INDYMAC, LaunchFact

STORIES: dict[str, list[LaunchFact]] = {
    "us_banks": [INDYMAC, CRISIS_BANKS],
    "deposit_insurance": [INDYMAC],
    "financial_crisis": [INDYMAC, CRISIS_BANKS],
    "hysa": [INDYMAC],
    "emergency_fund": [INDYMAC],
}


def add_to_brief(brief) -> None:
    from ..content.brief import Fact

    have = {f.text for f in brief.facts}
    for f in STORIES.get(brief.topic_key, []):
        if f.text not in have:
            brief.facts.append(Fact("STORY", f.text, f.source, f.url))


def has_story(brief) -> bool:
    return any(f.kind == "STORY" for f in brief.facts)


__all__ = ["STORIES", "add_to_brief", "has_story"]
