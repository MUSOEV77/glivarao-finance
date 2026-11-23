"""Variety: no video repeats the previous video's structure, hook type, opening or ending line, backgrounds, Max's
opening pose, thumbnail layout or music. Brand colours, Max and the Charon voice stay the same everywhere.

How:
* A 7-video ROTATION (per format: long videos rotate among themselves, Shorts among themselves). Every slot differs
  from the next one in every dimension, so consecutive videos never match. Each script carries its slot
  (`Script.variety_slot`, saved in script.json, so a remake looks the same).
* The structure (explainer, myth vs fact, case study, ...) comes from formats.choose_format, which never picks the
  previous video's format; Shorts rotate angles (number / myth / mistake).
* After each video is made its fingerprint is recorded; the next video is checked against it. Script-level repeats
  (hook type, opening line, ending line, structure) are errors that Claude fixes before rendering; visual repeats
  are prevented by construction (rotation + backgrounds the previous video didn't use) and verified.
"""
from __future__ import annotations

import json
import re

HOOK_TYPES = ("number", "mistake", "question", "myth", "story", "comparison", "warning")
HOOK_HOW = {
    "number": "open with the shocking real number from the fact sheet, said to 'you'",
    "mistake": "open with the costly mistake 'you' are probably making (with what it costs, from the fact sheet)",
    "question": "open with a direct question to 'you' that contains the real number or the costly mistake",
    "myth": "open by naming a belief 'you' probably hold and say it costs you (the fact-sheet number proves it)",
    "story": "open with one concrete person-like moment ('You check your statement and see ...') with the real number",
    "comparison": "open with a stark two-sided comparison for 'you' (this vs that) built on the fact-sheet number",
    "warning": "open with a direct warning to 'you' ('Don't ...' / 'Stop ...') and the real cost from the fact sheet",
}
# (hook type, music variant, thumbnail layout, Max's opening pose). Adjacent slots (incl. 7 -> 1) differ in all four.
ROTATION = [
    {"hook": "number", "music": 0, "layout": "max_right", "pose": "shocked"},
    {"hook": "mistake", "music": 1, "layout": "max_left", "pose": "worried"},
    {"hook": "question", "music": 2, "layout": "panel_top", "pose": "thinking"},
    {"hook": "myth", "music": 3, "layout": "max_right", "pose": "pointing"},
    {"hook": "story", "music": 4, "layout": "max_left", "pose": "explaining"},
    {"hook": "comparison", "music": 5, "layout": "panel_top", "pose": "happy"},
    {"hook": "warning", "music": 6, "layout": "max_left", "pose": "sad"},
]
# music variants: (seed -> chord progression / pattern, tempo). Adjacent variants differ in both.
MUSIC = [(0, 84), (1, 96), (2, 76), (3, 90), (4, 72), (5, 100), (6, 80)]
THUMB_EMOTIONS = ("shocked", "worried", "pointing", "thinking", "happy", "sad", "explaining")

_RX = {
    "question": None,
    "myth": re.compile(r"\b(?:myth|you'?ve been told|everyone says|people (?:think|say|believe)|you (?:probably )?"
                       r"(?:think|believe)|they say|it'?s a lie|not true)\b", re.I),
    "story": re.compile(r"\b(?:imagine|picture this|meet|you (?:open|check|look at|get|swipe)|last (?:year|month|"
                        r"week),? you|one day)\b", re.I),
    "comparison": re.compile(r"\b(?:vs\.?|versus|instead of|compared (?:to|with)|than|twice as|half as)\b", re.I),
    "warning": re.compile(r"^(?:don'?t|stop|never|before you|careful|warning)\b|\b(?:don'?t|stop) (?:pay|use|let|"
                          r"make|ignore|sign|swipe)", re.I),
    "mistake": re.compile(r"\b(?:mistake|wrong|costing you|costs you|you'?re losing|you lose|overpay|trap|"
                          r"wasting|throwing away)\b", re.I),
}
NUMBER = re.compile(r"\$\s?\d|\d[\d,.]*\s?(?:%|percent|dollars|billion|trillion|million)|\b\d{2,}\b", re.I)


def slot(n: int) -> dict:
    return ROTATION[n % len(ROTATION)]


def next_slot(store, fmt: str, offset: int = 0) -> int:
    """The rotation slot for the next video of this format (offset = how many more are being written now)."""
    return (int(store.kv_get(f"variety_count:{fmt}", "0")) + offset) % len(ROTATION)


def hook_type(sentence: str) -> str:
    s = sentence.strip()
    if s.endswith("?"):
        return "question"
    for k in ("myth", "story", "comparison", "warning", "mistake"):
        if _RX[k].search(s):
            return k
    return "number" if NUMBER.search(s) else "statement"


def _sentences(text: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.!?])\s+", " ".join(text.replace("*", "").split())) if x.strip()]


DISCLAIMER = re.compile(r"education(?:al)? only|not financial advice|isn'?t financial advice", re.I)


def opening_line(script) -> str:
    s = _sentences(script.scenes[0].narration) if script.scenes else []
    return s[0] if s else ""


def ending_line(script) -> str:
    """The last spoken line that isn't the education-only sentence (Shorts: may be the loop line)."""
    s = [x for x in _sentences(script.scenes[-1].narration) if not DISCLAIMER.search(x)] if script.scenes else []
    return s[-1] if s else ""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9$% ]", "", s.lower()).strip()


def script_fingerprint(script) -> dict:
    return {"structure": script.style or "", "hook_type": hook_type(opening_line(script)),
            "opening": opening_line(script), "ending": ending_line(script),
            "slot": script.variety_slot}


def previous(store, fmt: str) -> dict | None:
    hist = json.loads(store.kv_get(f"variety_history:{fmt}", "[]"))
    return hist[-1] if hist else None


def history(store, fmt: str) -> list[dict]:
    return json.loads(store.kv_get(f"variety_history:{fmt}", "[]"))


def script_issues(script, prev: dict | None) -> list[str]:
    """What the script repeats from the previous video of the same format (errors Claude fixes before render)."""
    if not prev:
        return []
    fp, out = script_fingerprint(script), []
    if fp["structure"] and fp["structure"] == prev.get("structure") and script.format == "long":
        out.append(f"same structure as the previous video ({fp['structure']}): use a different format")
    if fp["hook_type"] == prev.get("hook_type") and fp["hook_type"] != "statement":
        want = HOOK_TYPES[(HOOK_TYPES.index(fp["hook_type"]) + 1) % len(HOOK_TYPES)] \
            if script.variety_slot is None else slot(script.variety_slot)["hook"]
        out.append(f"same hook type as the previous video ({fp['hook_type']}): {HOOK_HOW.get(want, want)}")
    if fp["opening"] and _norm(fp["opening"]) == _norm(prev.get("opening", "")):
        out.append(f"same opening line as the previous video: \"{fp['opening'][:80]}\"")
    if fp["ending"] and _norm(fp["ending"]) == _norm(prev.get("ending", "")):
        out.append(f"same ending line as the previous video: \"{fp['ending'][:80]}\"")
    return out


VISUAL_KEYS = ("backgrounds", "opening_pose", "thumb_layout", "music")


def visual_issues(fp: dict, prev: dict | None) -> list[str]:
    if not prev:
        return []
    out = []
    shared = set(fp.get("backgrounds") or []) & set(prev.get("backgrounds") or [])
    if shared:
        out.append(f"background(s) used by the previous video too: {', '.join(sorted(shared))}")
    for k in ("opening_pose", "thumb_layout", "music"):
        if fp.get(k) is not None and fp.get(k) == prev.get(k):
            out.append(f"same {k.replace('_', ' ')} as the previous video ({fp[k]})")
    return out


def record(store, fmt: str, fp: dict) -> list[str]:
    """Save this video's fingerprint (after it was made); returns any repeats versus the previous one."""
    prev = previous(store, fmt)
    issues = visual_issues(fp, prev) + ([] if not prev else
                                        [i for i in ("structure", "hook_type", "opening", "ending")
                                         if fp.get(i) and fp.get(i) == prev.get(i) and
                                         not (i == "structure" and fmt == "short")])
    hist = history(store, fmt) + [fp]
    store.kv_set(f"variety_history:{fmt}", json.dumps(hist[-30:]))
    store.kv_set(f"variety_count:{fmt}", str(int(store.kv_get(f"variety_count:{fmt}", "0")) + 1))
    return issues


def rotation_table() -> str:
    rows = ["slot  hook        music (tempo)  thumbnail  Max opening pose"]
    for k, r in enumerate(ROTATION, 1):
        rows.append(f"{k:<5} {r['hook']:<11} #{r['music'] + 1} ({MUSIC[r['music']][1]} bpm)   "
                    f"{r['layout']:<10} {r['pose']}")
    return "\n".join(rows)


__all__ = ["ROTATION", "HOOK_TYPES", "HOOK_HOW", "MUSIC", "slot", "next_slot", "hook_type", "script_fingerprint",
           "previous", "script_issues", "visual_issues", "record", "opening_line", "ending_line", "rotation_table"]
