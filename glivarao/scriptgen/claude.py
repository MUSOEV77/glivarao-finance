"""Generate a structured script with the Claude API (Anthropic Python SDK).

Cost control (paid API; used only when ALLOW_PAID_APIS=true):
- a monthly USD cap (CLAUDE_MONTHLY_BUDGET_USD) is checked BEFORE every request against a worst-case estimate,
  and actual usage from the API response is recorded in data/claude_spend.json;
- a script outside the target length gets ONE revision request (expand or tighten) instead of being thrown
  away, so a paid draft is never wasted.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import anthropic

from ..config import Settings
from ..models import Script
from .prompts import (SCRIPT_SCHEMA, SYSTEM_PROMPT, WORDS_PER_MINUTE, normalize_direction, originality_prompt,
                      revise_prompt, user_prompt)

log = logging.getLogger(__name__)

DEFAULT_MINUTES = {"long": 16.5, "short": 0.85}
# spoken-word targets used for the revision step (kept in step with compliance.LENGTH_RULES)
TARGET_WORDS = {"long": (2200, 2800), "short": (90, 160)}
# worst-case output tokens assumed by the pre-flight budget check (thinking + JSON)
EST_OUTPUT_TOKENS = {"long": 24000, "short": 6000}
MAX_TOKENS = 64000


class ScriptGenerationError(RuntimeError):
    pass


class ClaudeBudgetExceeded(ScriptGenerationError):
    pass


class ClaudeSpendLedger:
    """USD spent per calendar month on Claude script writing (JSON file)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def spent(self, month: str | None = None) -> float:
        return float(self._load().get(month or date.today().strftime("%Y-%m"), {}).get("usd", 0.0))

    def add(self, usd: float, input_tokens: int, output_tokens: int, month: str | None = None) -> None:
        data = self._load()
        m = month or date.today().strftime("%Y-%m")
        row = data.setdefault(m, {"usd": 0.0, "input_tokens": 0, "output_tokens": 0, "requests": 0})
        row["usd"] = round(row["usd"] + usd, 6)
        row["input_tokens"] += input_tokens
        row["output_tokens"] += output_tokens
        row["requests"] += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))


def usage_cost(usage, price_in: float, price_out: float) -> tuple[float, int, int]:
    """USD for one response. Cache writes bill at 1.25x input, cache reads at 0.1x."""
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    cw = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cr = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    usd = (inp + 1.25 * cw + 0.1 * cr) * price_in / 1e6 + out * price_out / 1e6
    return usd, inp + cw + cr, out


def _check_budget(settings: Settings, ledger: ClaudeSpendLedger, prompt_chars: int, fmt: str) -> None:
    est = (prompt_chars / 3.5 + len(SYSTEM_PROMPT) / 3.5) * settings.claude_price_in / 1e6 + \
        EST_OUTPUT_TOKENS[fmt] * settings.claude_price_out / 1e6
    spent = ledger.spent()
    if spent + est > settings.claude_monthly_budget_usd:
        raise ClaudeBudgetExceeded(f"Claude monthly budget: ${spent:.2f} spent + ~${est:.2f} for this request "
                                   f"would exceed ${settings.claude_monthly_budget_usd:.2f}")


def _request(client, settings: Settings, ledger: ClaudeSpendLedger, prompt: str, fmt: str) -> dict:
    _check_budget(settings, ledger, len(prompt), fmt)
    # Streaming avoids HTTP timeouts on long outputs. Server-side fallback re-runs the request on
    # another model if the primary declines (e.g. a finance topic tripping a classifier).
    with client.beta.messages.stream(
        model=settings.script_model,
        max_tokens=MAX_TOKENS,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCRIPT_SCHEMA}},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    usd, tin, tout = usage_cost(message.usage, settings.claude_price_in, settings.claude_price_out)
    ledger.add(usd, tin, tout)  # billed even when the output is unusable
    log.info("Claude usage: in=%s out=%s cost=$%.3f (month: $%.2f of $%.2f)", tin, tout, usd, ledger.spent(),
             settings.claude_monthly_budget_usd)
    if message.stop_reason == "refusal":
        raise ScriptGenerationError(f"Model declined: {getattr(message, 'stop_details', None)}")
    if message.stop_reason == "max_tokens":
        raise ScriptGenerationError("Script truncated at max_tokens")
    text = next((b.text for b in message.content if getattr(b, "type", "") == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScriptGenerationError(f"Invalid JSON from model: {exc}") from exc


def _to_script(data: dict, fmt: str, topic: str) -> Script:
    data = {**data, "scenes": [normalize_direction(s) for s in data.get("scenes", [])]}
    return Script.model_validate({**data, "format": fmt, "topic": topic})


def generate_with_claude(topic: str, fmt: str, settings: Settings, minutes: float | None = None,
                         angle: str = "", client=None, ledger: ClaudeSpendLedger | None = None,
                         max_revisions: int = 1) -> Script:
    minutes = minutes or DEFAULT_MINUTES[fmt]
    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    ledger = ledger or ClaudeSpendLedger(Path(settings.claude_spend_ledger_path))
    script = _to_script(_request(client, settings, ledger, user_prompt(topic, fmt, minutes, angle), fmt), fmt, topic)
    lo, hi = TARGET_WORDS[fmt]
    for attempt in range(max_revisions):
        n = script.word_count
        if lo <= n <= hi:
            break
        target = int(minutes * WORDS_PER_MINUTE)
        log.info("Claude draft has %d words (target %d-%d); requesting revision %d", n, lo, hi, attempt + 1)
        try:
            revised = _to_script(_request(client, settings, ledger,
                                          revise_prompt(script.model_dump_json(), fmt, n, target, lo, hi, angle),
                                          fmt), fmt, topic)
        except ClaudeBudgetExceeded:
            log.warning("no budget left for a length revision; keeping the draft")
            break
        # keep whichever draft is closer to the target range
        if abs(revised.word_count - target) < abs(n - target):
            script = revised
    return script


def rewrite_for_originality(script: Script, reasons: list[str], phrases: list[str], settings: Settings,
                            client=None, ledger: ClaudeSpendLedger | None = None) -> Script:
    """One paid rewrite of a draft that the anti-repetition check flagged."""
    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    ledger = ledger or ClaudeSpendLedger(Path(settings.claude_spend_ledger_path))
    data = _request(client, settings, ledger, originality_prompt(script.model_dump_json(), reasons, phrases,
                                                                 script.format), script.format)
    out = _to_script(data, script.format, script.topic)
    return out.model_copy(update={"style": script.style})
