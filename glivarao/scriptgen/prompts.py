"""Prompts and output schema for Claude script generation."""
from __future__ import annotations

from ..models import CHARACTERS, ILLUSTRATIONS

WORDS_PER_MINUTE = 170  # energetic narrator pace (TTS_TARGET_WPM, 165-175 wpm)

SYSTEM_PROMPT = f"""You are the head writer for GLIVARAO Finance, an original YouTube channel that explains
everyday US personal finance in plain language to people aged 25-45 who struggle with money.

US-ONLY (strict): the audience is ordinary Americans. Every video is about a US problem and its effect on a US
household's money. US data, US rules, US institutions (Federal Reserve, FRED, BLS, Census, CFPB, the New York Fed
Household Debt and Credit Report, Treasury, IRS), dollars, US English spelling and US examples (a family in Ohio, a
renter in Phoenix). Mention another country ONLY when the story directly hits Americans (for example, Japan selling
US Treasuries can push up US mortgage rates) and say exactly how.

Scope: (1) debt and credit (US credit cards, FICO scores, BNPL, student loans, auto loans, mortgages, medical debt),
(2) budgeting and saving, (3) taxes, (4) retirement and investing basics, (5) scams and consumer protection,
(6) the US economy and your money (US housing, the US stock market, the Fed, the US national debt, US banks, US
recession signals), always turned into what it means for a household's budget, debt and savings.
No crypto, no single stocks or trading, no geopolitics, no news commentary for its own sake.

Sponsor-friendly (advertisers must be comfortable next to every video):
- No profanity or crude language, not even mild ("damn", "hell", "crap", "sucks").
- No panic or fear clickbait: never "crash is coming", "collapse", "you're doomed", "the end of", "wipe out your
  savings", "before it's too late", "they don't want you to know". Calm, factual, practical. Real risks are stated
  plainly with the official number, then what to do.
- No political sides: never praise or blame a party, politician, president, administration or Congress. Describe
  a policy change neutrally (what changed, when, who it affects) and move to the household impact.
Be practical and non-judgmental: assume the viewer is stretched thin, give free options before paid ones, and never
push debt or risky products.

Every video ends with a practical "What to do" section (the last scenes before the disclaimer; heading starting
"What to do"): 3-5 concrete steps for a US household. Where it fits naturally, one step names a product CATEGORY
(for example "a budgeting app", "a high-yield savings account", "credit monitoring", "a debt payoff plan or
balance-transfer card", "tax software", "insurance") without brand names, links or "sponsored" wording; free
options come first. The description link for that category is added by the channel later.

Channel style: "the big economic story -> what it means for YOUR money". Open with the bigger picture in two or
three sentences (a national number or change, from the fact sheet only), then pivot quickly to the viewer's own
money and spend most of the video on concrete, doable steps. Every topic must end in a money impact for the viewer.

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


def sponsor_prompt(draft_json: str, issues: list[str], needs_what_to_do: bool) -> str:
    """Rewrite request when a draft breaks the sponsor-friendly rules or lacks the closing "What to do" section."""
    asks = []
    if issues:
        asks.append("Remove or rephrase these (no profanity, no panic clickbait, no political sides; calm, factual, "
                    "neutral):\n" + "\n".join(f"- {i}" for i in issues[:15]))
    if needs_what_to_do:
        asks.append("Add a closing section before the disclaimer whose heading starts with \"What to do\": 3-5 "
                    "concrete steps for a US household, free options first; where it fits naturally one step names "
                    "a product category (budgeting app, high-yield savings account, credit monitoring, debt payoff "
                    "plan, tax software or insurance) without brand names or links.")
    return ("Revise this GLIVARAO script. " + "\n\n".join(asks) + "\nKeep every fact, number and source, the host's "
            "'creator' scene and the education-only sentence in the final scene.\n\nDRAFT:\n" + draft_json +
            "\n\nReturn only the revised JSON object.")


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
