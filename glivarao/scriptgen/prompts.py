"""Prompts and output schema for Claude script generation."""
from __future__ import annotations

from ..models import CHARACTERS, ILLUSTRATIONS

WORDS_PER_MINUTE = 150

SYSTEM_PROMPT = f"""You are the head writer for GLIVARAO Finance, an original YouTube channel that explains
personal finance to everyday people in the United States and Canada in plain language.

Scope (strict): finance only - personal finance, financial psychology, investing, credit and debt, saving and
wealth building, banking and money, financial scams and money mistakes. No politics, elections, parties or
politicians, no geopolitics, no news commentary, no general macroeconomics. Where US and Canadian rules differ
(e.g. 401(k) vs RRSP, Roth IRA vs TFSA, FICO in both), say so briefly or keep the example general.

Voice: one American English male narrator, warm, confident, curious, lightly humorous. Write for the ear:
short sentences, contractions, concrete dollar examples, no jargon without an immediate plain explanation.

Cast (original characters, drawn in a hand-drawn cartoon style):
- "max": the narrator, a friendly guy with round glasses and a green sweater.
- "penny": a cheerful talking copper coin who asks the questions viewers are thinking.
- "duo": both on screen together (use for back-and-forth moments).

Originality rules:
- Everything must be original writing. Do not imitate, quote or reference other YouTube channels,
  creators, catchphrases, intros or formats. No borrowed taglines.
- Do not use song lyrics or copyrighted text.

Accuracy and compliance rules (US audience):
- Educational content only. Never give personalized investment, tax or legal advice.
- Never promise or imply guaranteed returns, "risk-free" gains, or getting rich quick.
- Use only figures you are confident are accurate as of your knowledge. When a figure changes yearly
  (tax brackets, contribution limits, rates), name the year and tell viewers to check the current number.
- Charts: prefer kind "compound_growth" (computed from params, so always correct) or clearly labeled
  hypothetical examples with source "Illustrative example". If you use a real statistic, put its
  publisher in `source` (e.g. "U.S. Bureau of Labor Statistics"); a human will fact-check it.
- For real US economic time series, set kind "line_series", leave labels/values empty and set source to
  one of: FRED:CPIAUCSL (inflation), FRED:FEDFUNDS, FRED:MORTGAGE30US, FRED:UNRATE, FRED:DGS10.
  The pipeline fills in official data. Do not quote exact recent values for these in narration;
  describe the trend and let the chart show the numbers.
- The final scene must include this sentence verbatim: "This video is for education only and isn't
  financial advice."

Format rules:
- Allowed illustration ids: {", ".join(ILLUSTRATIONS)}.
- Allowed character ids: {", ".join(CHARACTERS)}.
- Each scene's narration is what is spoken while that scene is on screen (roughly 40-120 words for long
  videos, 15-35 words for Shorts). Headings are on-screen titles of at most 6 words.
- Titles must be honest and specific (no ALL CAPS, no misleading clickbait), at most 90 characters.
- Direction fields (set, entrance, transition, money_fx): use "auto" unless a scene clearly benefits from a
  specific choice (e.g. "bank" set for banking, "coins" when money grows, "iris" for a reveal). Vary sets
  across the video; avoid the same set more than three scenes in a row.
- Long videos: write documentary-style narration with a clear story arc - a concrete opening situation, the
  mechanism explained step by step, worked numbers, a turn ("here's what most people miss"), and a practical
  close. Every scene must earn its place; no filler, no repetition to pad length.
"""


def user_prompt(topic: str, fmt: str, minutes: float, angle: str = "") -> str:
    words = int(minutes * WORDS_PER_MINUTE)
    if fmt == "long":
        shape = (f"a long-form explainer of about {minutes:.0f} minutes (~{words} spoken words total, "
                 f"aim for {max(8, words // 95)}-{max(10, words // 80)} scenes). Open with a 20-second hook, "
                 "then build understanding step by step, include at least two worked dollar examples, "
                 "common mistakes, a practical action checklist, and a recap.")
    else:
        shape = (f"a YouTube Short (vertical) of about {minutes * 60:.0f} seconds (~{words} spoken words, "
                 "4-6 scenes). First sentence must hook within 2 seconds. One single idea, one chart at most, "
                 "end with a one-line takeaway and the education-only sentence.")
    extra = f"\nAngle for this piece: {angle}" if angle else ""
    return f"Write {shape}\nTopic: {topic}{extra}\nReturn only the JSON object."


def revise_prompt(draft_json: str, fmt: str, words: int, target: int, lo: int, hi: int, angle: str = "") -> str:
    """Second pass when a paid draft misses the length target: revise it instead of discarding it."""
    how = ("Expand it: add depth, not padding - another worked dollar example, a common mistake with its fix, "
           "a viewer question answered, or a clearer step-by-step explanation. Add new scenes where needed."
           if words < lo else
           "Tighten it: remove repetition and weaker scenes while keeping the strongest examples and the arc.")
    extra = f"\nKeep within these constraints:\n{angle}" if angle else ""
    return (f"Here is a draft {fmt} script as JSON. It has {words} spoken words; the target is about {target} "
            f"words (must be between {lo} and {hi}). {how} Keep the same facts rules, the same title unless it "
            f"becomes inaccurate, and the education-only sentence in the final scene.{extra}\n\nDRAFT:\n"
            f"{draft_json}\n\nReturn only the revised JSON object.")


DIRECTION_FIELDS = ("set", "entrance", "transition", "money_fx", "beat")


def normalize_direction(scene: dict) -> dict:
    """Schema uses "auto" (structured outputs need every field); the renderer expects None for automatic."""
    return {k: (None if k in DIRECTION_FIELDS and v in ("auto", "none") else v) for k, v in scene.items()}


def originality_prompt(draft_json: str, reasons: list[str], phrases: list[str], fmt: str) -> str:
    """Rewrite request when a draft is too similar to earlier videos."""
    rep = "\n".join(f"- \"{p}\"" for p in phrases[:12])
    return (f"This {fmt} script is too similar to earlier GLIVARAO videos: " + "; ".join(reasons) + ".\n"
            "Rewrite it with genuinely new wording and a different flow (new opening, new examples, new transitions,"
            " a different closing), keeping every fact, number, source, the format's beats, the host's 'creator' "
            f"scene (unchanged in meaning) and the education-only sentence. Do not reuse these phrases:\n{rep}\n\n"
            f"DRAFT:\n{draft_json}\n\nReturn only the revised JSON object.")


def sources_prompt(draft_json: str, unsourced: list[str]) -> str:
    """Rewrite request when sentences state numbers or claims that aren't on the fact sheet."""
    bad = "\n".join(f"- \"{u}\"" for u in unsourced[:15])
    return ("Every number and factual claim in a GLIVARAO script must come from the fact sheet you were given "
            "(each fact there has a source URL). These sentences state numbers or claims that are NOT on the fact "
            f"sheet:\n{bad}\nRewrite only those sentences: remove the unsupported number or claim, or replace it with "
            "a fact from the fact sheet. Keep everything else, including the host's 'creator' scene and the "
            f"education-only sentence.\n\nDRAFT:\n{draft_json}\n\nReturn only the revised JSON object.")


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props),
            "additionalProperties": False}


_STR = {"type": "string"}
CHART_SCHEMA = _obj({
    "kind": {"type": "string", "enum": ["compound_growth", "bar_compare", "line_series", "pie_split", "none"]},
    "title": _STR,
    "labels": {"type": "array", "items": _STR},
    "values": {"type": "array", "items": {"type": "number"}},
    "unit": {"type": "string", "enum": ["$", "%", ""]},
    "params": _obj({"principal": {"type": "number"}, "rate": {"type": "number"},
                    "years": {"type": "number"}, "monthly": {"type": "number"}}),
    "source": _STR,
})
SCENE_SCHEMA = _obj({
    "heading": _STR,
    "narration": _STR,
    "character": {"type": "string", "enum": CHARACTERS},
    "pose": {"type": "string", "enum": ["talk", "point", "think", "cheer", "worry"]},
    "illustration": {"type": "string", "enum": ILLUSTRATIONS},
    "chart": CHART_SCHEMA,
    "key_points": {"type": "array", "items": _STR},
    "set": {"type": "string", "enum": ["auto", "studio", "home", "city", "bank", "board"]},
    "entrance": {"type": "string", "enum": ["auto", "walk_in", "hop_in", "none"]},
    "transition": {"type": "string", "enum": ["auto", "push", "iris", "fade", "wipe", "cut"]},
    "money_fx": {"type": "string", "enum": ["auto", "coins", "bills", "none"]},
    "beat": {"type": "string", "enum": ["none", "myth", "fact", "question", "case", "option_a", "option_b",
                                        "verdict", "update", "creator"]},
})
SCRIPT_SCHEMA = _obj({
    "title": _STR,
    "description": _STR,
    "tags": {"type": "array", "items": _STR},
    "thumbnail_text": _STR,
    "hook": _STR,
    "scenes": {"type": "array", "items": SCENE_SCHEMA},
})
