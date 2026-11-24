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
LOOP_RE = re.compile(r"\b(?:but here'?s|here'?s the (?:part|thing|catch|twist|kicker)|easy to miss|stick with me|"
                     r"wait\b|but wait|the catch|the twist|plot twist|in a (?:minute|second|moment)|we'?ll get to|"
                     r"keep that in mind|remember that number|here'?s why|which brings us|now here'?s|"
                     r"but (?:that'?s not|there'?s more)|surprising|the real (?:problem|cost|reason)|you might think)\b",
                     re.I)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
WPM_SPOKEN = 158


def _sentences_of(text: str) -> list[str]:
    return [s for s in SENT_SPLIT.split(" ".join(text.replace("*", "").split())) if s.strip()]


YOU_RE = re.compile(r"\byou(?:r|rs|'re|'ll|'d|'ve)?\b", re.I)
NUM_RE = re.compile(r"\$\s?\d|\d[\d,.]*\s?(?:%|percent)|\d[\d,.]*\s(?:dollars|billion|trillion|million|years|months)|"
                    r"\b\d[\d,.]*\b", re.I)
MISTAKE_RE = re.compile(r"\b(?:mistake|wrong|costing|costs?|losing|lose|lost|overpay\w*|trap|wasting|throwing away|"
                        r"penalt\w+|fees?|late|interest|paying|owe)\b", re.I)
COST_RE = re.compile(r"\b(?:costs?|costing|pay|paying|paid|lose|losing|extra|interest|fees?|dollars?|years?|months?|"
                     r"owe|price|bill|every (?:month|year))\b|\$|%|\d", re.I)
PROMISE_RE = re.compile(r"\b(?:by the end|i'?ll show you|you'?ll (?:know|see|learn|have|get|find out)|here'?s how|"
                        r"the fix|(?:one|two|three|3|2) (?:simple |easy |quick )?(?:moves?|steps?|ways?|fixes)|"
                        r"how to (?:fix|stop|beat|get out|avoid|cut|lower)|we'?ll (?:fix|cover|walk)|"
                        r"stay (?:with me|until)|you can (?:fix|stop|beat|avoid|cut|lower))\b", re.I)
WPS = WPM_SPOKEN / 60            # spoken words per second (2.63)
TITLE_STOP = set("the a an and or of to in on for is are your you what how why this that it its with from at by be "
                 "as now still really most new vs explained guide here's heres".split())


def _content_stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z0-9$%]+", text.lower()) if len(w) >= 3 and w not in TITLE_STOP}


def opening_issues(script: Script) -> list[str]:
    """The first 30 seconds. Long: 0-5 s a shocking real number or costly mistake said to 'you'; 5-15 s what it
    costs 'you'; 15-30 s a promise and an open loop. Short: the hook lands in 1.5 s. Both: the first line matches
    the title and the thumbnail text."""
    out = []
    words = " ".join(script.full_narration.replace("*", "").split()).split()
    first = _sentences_of(script.scenes[0].narration)[0] if script.scenes and \
        _sentences_of(script.scenes[0].narration) else ""

    def span(a: float, b: float) -> str:
        return " ".join(words[int(a * WPS):int(b * WPS) + 1])

    def hooky(t: str) -> bool:      # a hook passes with ANY ONE of: a real number, a costly mistake, "you"
        return bool(NUM_RE.search(t) or MISTAKE_RE.search(t) or YOU_RE.search(t))

    if script.format == "short":
        head = span(0, 1.5)                                            # ~4 words
        if not hooky(head) and not hooky(first):
            out.append(f"hook doesn't land in 1.5 s: \"{first[:80]}\" has no real number, no costly mistake and "
                       "no 'you'")
    else:
        a, b, c = span(0, 5), span(5, 15), span(15, 32)
        if not hooky(a):
            out.append(f"0-5 s needs a real number, a costly mistake or 'you': \"{a[:90]}\"")
        if not (YOU_RE.search(b) and COST_RE.search(b)):
            out.append(f"5-15 s must say what it costs 'you' (money, interest, years): \"{b[:90]}\"")
        if not PROMISE_RE.search(c):
            out.append(f"15-30 s needs a promise of what 'you' get by the end: \"{c[:90]}\"")
        if not (LOOP_RE.search(c) or "?" in c or PROMISE_RE.search(c) and re.search(r"\bby the end\b", c, re.I)):
            out.append(f"15-30 s needs an open loop (something answered later): \"{c[:90]}\"")
    title_k = _content_stems(script.title.replace("#Shorts", ""))
    first_k = _content_stems(first)
    if title_k and not (title_k & first_k):
        out.append(f"first line doesn't match the title (no shared key word): \"{first[:60]}\" vs \"{script.title[:60]}\"")
    thumb = (script.thumbnail_text or "").replace("#Shorts", "")
    thumb_k = _content_stems(thumb)
    if thumb_k and not (thumb_k & (first_k | _content_stems(span(0, 5)))):
        out.append(f"first line doesn't match the thumbnail text \"{thumb[:40]}\"")
    return out


ABSOLUTE = [   # (pattern, kind): claims that must be literally true for the viewer, or come from the fact sheet
    (r"\bmost (?:people|americans|borrowers|households|families|cardholders|consumers|folks|of us|of you|workers|"
     r"renters|homeowners|buyers|savers|enrollees|drivers)\b", "most people"),
    (r"\b(?:everyone|everybody|nobody|no one|all americans|every american)\b", "everyone"),
    (r"\byou will\b(?! (?:learn|know|see|find|get to|hear|understand))|\byou'?ll (?:lose|pay|owe|end up|start|go|"
     r"never|always|miss|get (?:denied|charged|hit|nothing)|be (?!able)\w+)", "you will"),
    (r"\byou(?:'re| are)? (?:always|never)\b", "always/never"),
    (r"\b(?:guaranteed|definitely|certainly|for sure|without exception|no matter what)\b", "guaranteed"),
    (r"\band you(?:'ll| will)? (?:start|lose|pay|owe|go|end up|are|get|won'?t|can'?t|have no|lose)\b", "consequence"),
]
HEDGE = re.compile(r"\b(?:could|might|may|can|usually|often|typically|in many cases|for many|for some|some of you|"
                   r"if you'?re|unless|in most states|chances are|likely)\b", re.I)
SUPPORT_WORDS = {"most people": r"\bmost\b", "everyone": r"\b(?:everyone|all|every)\b",
                 "you will": r"\bwill\b", "always/never": r"\b(?:always|never)\b",
                 "guaranteed": r"\bguarante", "consequence": r"\b(?:will|won'?t|must|required|deadline)\b"}


def absolute_claim_issues(script: Script, facts: list[str] | None = None) -> list[str]:
    """Hooks may be dramatic but must be literally true for the viewer they address. Absolute claims ('you will',
    'everyone', 'most people', 'always', 'guaranteed', 'miss X and you ...') are flagged unless a fact on the fact
    sheet states the same thing. Consequence-style claims are fine once hedged ('could', 'may', 'if you're ...')."""
    facts = facts or []
    texts = [script.title.replace("#Shorts", ""), script.thumbnail_text or ""] + \
        [s for sc in script.scenes for s in _sentences_of(sc.narration)]
    out = []
    for sent in texts:
        for pat, kind in ABSOLUTE:
            m = re.search(pat, sent, re.I)
            if not m:
                continue
            if kind != "most people" and kind != "everyone" and HEDGE.search(sent):
                continue
            stems = _content_stems(sent)
            if any(re.search(SUPPORT_WORDS[kind], f, re.I) and len(stems & _content_stems(f)) >= 2 for f in facts):
                continue
            out.append(f"absolute claim not supported by the fact sheet ({kind}): \"{sent[:90]}\": make it "
                       "literally true for the viewer it addresses (e.g. 'could', 'many', 'if you're ...') or use a "
                       "fact-sheet number")
            break
    return list(dict.fromkeys(out))


def retention_issues(script: Script, previous: dict | None = None) -> list[str]:
    """Hook in the first seconds, no intro, short sentences to 'you', open loops every 45-60 s (long videos), the
    0-30 s opening structure, and no repeats of the previous video (studio/variety.py)."""
    out = opening_issues(script)
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
            re.search(r"\byou(?:r|'re|'ll|'d)?\b", hook, re.I) or MISTAKE_RE.search(hook)):
        out.append(f"first sentence is not a hook (no real number, no costly mistake, no 'you'): \"{hook[:80]}\"")
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
    return [i for i in out if "pattern interrupt" not in i]


def pacing_warnings(script: Script) -> list[str]:
    """Long videos: gaps over ~60 s without an open loop. A warning in the review, never a rejection or rewrite."""
    if script.format != "long":
        return []
    body = [s for sc in script.scenes for s in _sentences_of(sc.narration)]
    max_gap, pos, last = 0, 0, 0
    for s in body:
        pos += len(s.split())
        if LOOP_RE.search(s) or s.rstrip().endswith("?"):
            max_gap, last = max(max_gap, pos - last), pos
    max_gap = max(max_gap, pos - last)
    if max_gap > int(WPM_SPOKEN * 1.1):
        return [f"{max_gap / WPM_SPOKEN * 60:.0f} s without a pattern interrupt or open loop (aim for ~60 s)"]
    return []


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
    "short": (75, 130),     # 30-55 seconds after voicing (SHORT_MAX_WORDS=130; real length measured before rendering)
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
                 retention: bool = False, previous_video: dict | None = None) -> ComplianceReport:
    r = ComplianceReport()
    if retention:
        for issue in retention_issues(script, previous_video):
            (r.errors if enforce_length else r.warnings).append(f"Won't hold viewers: {issue}")
        r.warnings += [f"⚠ PACING: {i}" for i in pacing_warnings(script)]
        if previous_video is not None:      # variety repeats: a warning in the review, never a rejection
            from .studio.variety import script_issues

            r.warnings += [f"⚠ VARIETY: {i}" for i in script_issues(script, previous_video)]
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
