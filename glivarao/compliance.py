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

# Sponsor-friendly rules (advertisers avoid profanity, panic clickbait and political sides).
PROFANITY = r"\b(?:damn(?:ed|n)?|hell|crap(?:py)?|sucks?|shit\w*|f+u+c+k\w*|ass(?:hole)?|bitch\w*|bastard|wtf|pissed)\b"
PANIC_PATTERNS = [
    r"\b(?:market|stock|housing|economic|bank) (?:crash|collapse) (?:is )?coming\b",
    r"\b(?:collapse|crash) is (?:coming|here|imminent)\b",
    r"\byou(?:'re| are) doomed\b",
    r"\bwipe out your (?:savings|money|retirement)\b",
    r"\bbefore it'?s too late\b",
    r"\bthey don'?t want you to know\b",
    r"\bthe end of (?:america|the dollar|the economy|money)\b",
    r"\b(?:total|financial) (?:apocalypse|armageddon|meltdown)\b",
]
POLITICAL_SIDES = (r"\b(?:democrats?|republicans?|gop|maga|liberals?|conservatives?|left-wing|right-wing|"
                   r"(?:biden|trump|obama|harris|vance)(?:'s)?|the (?:democratic|republican) party)\b")
WHAT_TO_DO = re.compile(r"^what to do", re.I)


INTRO_RE = re.compile(r"\b(?:welcome|hey (?:guys|everyone|there|folks)|hi (?:guys|everyone|there|folks)|in this video|"
                      r"today (?:we|we're|we are|i|i'm)|let'?s talk about|before we (?:start|begin)|"
                      r"don'?t forget to (?:like|subscribe)|glivarao)\b", re.I)
LOOP_RE = re.compile(r"\b(?:but here'?s|here'?s the (?:part|thing|catch|twist|kicker)|most people miss|stick with me|"
                     r"wait\b|but wait|the catch|the twist|plot twist|in a (?:minute|second|moment)|we'?ll get to|"
                     r"keep that in mind|remember that number|here'?s why|which brings us|now here'?s|"
                     r"but (?:that'?s not|there'?s more)|surprising|the real (?:problem|cost|reason)|you might think)\b",
                     re.I)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
WPM_SPOKEN = 158


def _sentences_of(text: str) -> list[str]:
    return [s for s in SENT_SPLIT.split(" ".join(text.replace("*", "").split())) if s.strip()]


def retention_issues(script: Script) -> list[str]:
    """Hook in the first seconds, no intro, short sentences to 'you', open loops every 45-60 s (long videos)."""
    out = []
    first_scene = script.scenes[0].narration if script.scenes else ""
    sents = _sentences_of(first_scene)
    hook = sents[0] if sents else ""
    limit = 10 if script.format == "short" else 20
    if INTRO_RE.search(hook) or INTRO_RE.search(" ".join(sents[:2])):
        out.append(f"opens with an intro instead of the hook: \"{hook[:80]}\"")
    if len(hook.split()) > limit:
        out.append(f"first sentence has {len(hook.split())} words (hook must land in "
                   f"{'2' if script.format == 'short' else '5'} seconds: max {limit})")
    if not (re.search(r"\d|percent|dollar|million|billion|trillion", hook, re.I) or
            re.search(r"\byou(?:r|'re|'ll|'d)?\b", hook, re.I)):
        out.append(f"first sentence is not a concrete hook (no real number, not a mistake 'you' make): \"{hook[:80]}\"")
    body = [s for sc in script.scenes for s in _sentences_of(sc.narration)]
    words = [len(s.split()) for s in body]
    if words and sum(words) / len(words) > 16:
        out.append(f"sentences too long for the ear (average {sum(words) / len(words):.0f} words; aim for 8-14)")
    long_ones = [s for s in body if len(s.split()) > 30]
    if long_ones:
        out.append(f"{len(long_ones)} sentence(s) over 30 words, e.g. \"{long_ones[0][:70]}...\"")
    total = sum(words)
    yous = len(re.findall(r"\byou(?:r|rs|'re|'ll|'d|'ve)?\b", script.full_narration, re.I))
    if total and yous < total / 80:
        out.append(f"talks to 'you' only {yous} times in {total} words")
    if script.format == "long":
        gap, max_gap, pos, last = int(WPM_SPOKEN * 1.1), 0, 0, 0   # about 66 s of narration at most between interrupts
        for s in body:
            pos += len(s.split())
            if LOOP_RE.search(s) or s.rstrip().endswith("?"):
                max_gap, last = max(max_gap, pos - last), pos
        max_gap = max(max_gap, pos - last)
        if max_gap > gap:
            out.append(f"{max_gap / WPM_SPOKEN * 60:.0f} s without a pattern interrupt or open loop (max ~60 s)")
    return out


def sponsor_issues(script: Script) -> list[str]:
    """Profanity, panic clickbait and political-side language in the narration, title, description or thumbnail."""
    text = " ".join([script.title, script.description, script.thumbnail_text or "", script.full_narration])
    out = [f"profanity: '{m.group(0)}'" for m in re.finditer(PROFANITY, text, flags=re.I)]
    for pat in PANIC_PATTERNS:
        out += [f"panic clickbait: '{m.group(0)}'" for m in re.finditer(pat, text, flags=re.I)]
    out += [f"political side: '{m.group(0)}'" for m in re.finditer(POLITICAL_SIDES, text, flags=re.I)]
    return list(dict.fromkeys(out))


MONTHS = r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
TIME_WORDS = (r"\b(?:this week|last week|next week|this month|last month|next month|yesterday|tomorrow|earlier today|"
              r"just announced|breaking(?: news)?|as we speak|this morning|tonight)\b")


def evergreen_issues(script: Script, today_year: int | None = None) -> list[str]:
    """Evergreen videos must stay correct for years: no dates or time-bound words in the title or thumbnail, and no
    "this week"-style wording in the script (current numbers go in as "as of <Month Year>")."""
    from datetime import date

    year = today_year or date.today().year
    out = []
    head = f"{script.title} {script.thumbnail_text or ''}"
    for m in re.finditer(r"\b(?:19|20)\d\d\b", head):
        if int(m.group(0)) >= year - 3:       # recent years date the video; history (2008) is fine
            out.append(f"date in the title: '{m.group(0)}'")
    for m in re.finditer(rf"\b{MONTHS}\b", head, flags=re.I):
        out.append(f"month in the title: '{m.group(0)}'")
    for m in re.finditer(TIME_WORDS, head + " " + script.full_narration, flags=re.I):
        out.append(f"time-bound wording: '{m.group(0)}'")
    for m in re.finditer(r"\b(?:right now|currently)\b[^.]{0,40}?(?:\d+(?:\.\d+)?\s?%|\$\d)", script.full_narration,
                         flags=re.I):
        out.append(f"current number without 'as of <Month Year>': '{m.group(0)[:50]}'")
    return list(dict.fromkeys(out))


def has_what_to_do(script: Script) -> bool:
    """Long videos end with a practical "What to do" section (Shorts: a one-line takeaway is enough)."""
    if script.format != "long":
        return True
    return any(WHAT_TO_DO.match(s.heading.strip()) for s in script.scenes[-4:])


LENGTH_RULES = {  # spoken words at ≈170 wpm (the energetic narrator pace)
    "long": (2550, 3100),   # ~15-18 minutes
    "short": (75, 120),     # 30-55 seconds after voicing (SHORT_MAX_WORDS=120; real length measured before rendering)
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
                 previous_scripts: list[str] | None = None, evergreen: bool = False,
                 retention: bool = False) -> ComplianceReport:
    r = ComplianceReport()
    if retention:
        for issue in retention_issues(script):
            (r.errors if enforce_length else r.warnings).append(f"Won't hold viewers: {issue}")
    if evergreen:
        for issue in evergreen_issues(script):
            (r.errors if enforce_length else r.warnings).append(f"Not evergreen: {issue}")
    text = script.full_narration

    for pat in BANNED_PATTERNS:
        for m in re.finditer(pat, text, flags=re.I):
            r.errors.append(f"Prohibited claim language: '{m.group(0)}'")

    for issue in sponsor_issues(script):
        r.errors.append(f"Not sponsor-friendly: {issue}")
    if not has_what_to_do(script):
        (r.errors if enforce_length else r.warnings).append(
            "Missing the closing \"What to do\" section (practical steps for a US household)")

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
            if c.source.strip().lower() not in ("illustrative example", "calculated example") \
                    and not c.source.startswith("FRED, "):
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
