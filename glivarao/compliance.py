"""Automated pre-render checks for finance-content compliance, length and originality.

This is a safety net, not a substitute for the human approval step in Telegram.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import ILLUSTRATIONS, Script

DISCLAIMER = "isn't financial advice"

# Phrases that imply guarantees or personalized advice. Matched case-insensitively.
BANNED_PATTERNS = [
    r"\bguarantee[sd]?\b(?! (?:that )?you'll learn)",
    r"\brisk[- ]free\b",
    r"\bget rich quick\b",
    r"\bcan'?t lose\b",
    r"\bsure thing\b",
    r"\b100% (?:safe|return)\b",
    r"\byou should (?:buy|sell)\b",
    r"\bthis stock will\b",
    r"\bdouble your money\b",
]

LENGTH_RULES = {  # spoken words (≈150 wpm)
    "long": (2200, 2800),   # ~15-18.5 minutes
    "short": (90, 160),     # ~35-60 seconds
}


@dataclass
class ComplianceReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fact_check: list[str] = field(default_factory=list)  # items a human must verify

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        parts = [f"errors={len(self.errors)} warnings={len(self.warnings)} fact_check={len(self.fact_check)}"]
        parts += [f"ERROR: {e}" for e in self.errors]
        parts += [f"WARN: {w}" for w in self.warnings]
        parts += [f"CHECK: {c}" for c in self.fact_check]
        return "\n".join(parts)


def _shingles(text: str, n: int = 8) -> set[str]:
    words = re.findall(r"[a-z']+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def overlap_ratio(a: str, b: str, n: int = 8) -> float:
    sa, sb = _shingles(a, n), _shingles(b, n)
    return len(sa & sb) / len(sa) if sa else 0.0


def check_script(script: Script, enforce_length: bool = True,
                 previous_scripts: list[str] | None = None) -> ComplianceReport:
    r = ComplianceReport()
    text = script.full_narration

    for pat in BANNED_PATTERNS:
        for m in re.finditer(pat, text, flags=re.I):
            r.errors.append(f"Prohibited claim language: '{m.group(0)}'")

    if DISCLAIMER not in script.scenes[-1].narration.replace("’", "'"):
        r.errors.append("Final scene is missing the education-only disclaimer")

    lo, hi = LENGTH_RULES[script.format]
    if not (lo <= script.word_count <= hi):
        msg = f"Word count {script.word_count} outside target {lo}-{hi} for {script.format}"
        (r.errors if enforce_length else r.warnings).append(msg)

    if len(script.title) > 100:
        r.errors.append("Title exceeds YouTube's 100-character limit")
    if script.title.isupper():
        r.warnings.append("Title is all caps")
    if len(script.description) > 5000:
        r.errors.append("Description exceeds 5000 characters")

    for i, s in enumerate(script.scenes):
        if s.illustration not in ILLUSTRATIONS:
            r.warnings.append(f"Scene {i}: unknown illustration '{s.illustration}', a default will be used")
        c = s.chart
        if c.kind in {"bar_compare", "line_series", "pie_split"}:
            if c.source.upper().startswith("FRED:"):
                r.errors.append(f"Scene {i}: FRED chart '{c.title}' was not filled with data")
            elif not c.values or (c.labels and len(c.labels) != len(c.values)):
                r.errors.append(f"Scene {i}: chart '{c.title}' has mismatched labels/values")
            if c.source.strip().lower() != "illustrative example" and not c.source.startswith("FRED, "):
                r.fact_check.append(f"Scene {i}: chart '{c.title}' cites '{c.source}' — verify numbers")
        if c.kind == "compound_growth" and not c.params.get("years"):
            r.errors.append(f"Scene {i}: compound_growth chart needs params.years")
        for num in re.findall(r"\b(?:19|20)\d\d\b", s.narration):
            r.fact_check.append(f"Scene {i}: year-specific claim ({num}) — confirm figure is current")

    # A script must not pad itself with repeated narration (also catches offline placeholder filler).
    seen: dict[str, int] = {}
    repeats = 0
    for sc in script.scenes:
        key = " ".join(sc.narration.lower().split())
        repeats += key in seen
        seen[key] = 1
    if repeats:
        msg = f"{repeats} scene(s) repeat narration already used earlier in this script"
        (r.errors if enforce_length else r.warnings).append(msg)

    for prev in previous_scripts or []:
        ratio = overlap_ratio(text, prev)
        if ratio > 0.15:
            r.errors.append(f"Narration overlaps {ratio:.0%} with a previous script (8-word shingles)")
    return r
