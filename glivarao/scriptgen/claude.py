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

from ..config import Settings
from ..models import Script
from .prompts import (SCRIPT_SCHEMA, SYSTEM_PROMPT, WORDS_PER_MINUTE, normalize_direction, originality_prompt, sources_prompt,
                      revise_prompt, user_prompt)

log = logging.getLogger(__name__)

DEFAULT_MINUTES = {"long": 16.5, "short": 0.6}   # Shorts: ~100 words at 170 wpm (hard cap 110 words, 60 s)
# spoken-word targets used for the revision step (kept in step with compliance.LENGTH_RULES)
from ..compliance import LENGTH_RULES as TARGET_WORDS  # noqa: E402  same ranges as the compliance check
# worst-case output tokens assumed by the pre-flight budget check (thinking + JSON)
EST_OUTPUT_TOKENS = {"long": 24000, "short": 6000}
MAX_TOKENS = 64000


class ScriptGenerationError(RuntimeError):
    pass


class ClaudeUnavailable(ScriptGenerationError):
    """Claude can't write right now (quota, outage, key, cap, refusal) and no fallback writer is allowed:
    production is held and retried hourly."""


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
        from ..studio import costs

        costs.record("claude", usd, self.path.parent)   # per-video spend (cost-report)


def usage_cost(usage, price_in: float, price_out: float) -> tuple[float, int, int]:
    """USD for one response. Cache writes bill at 1.25x input, cache reads at 0.1x."""
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    cw = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cr = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    usd = (inp + 1.25 * cw + 0.1 * cr) * price_in / 1e6 + out * price_out / 1e6
    return usd, inp + cw + cr, out


def _check_budget(settings: Settings, ledger: ClaudeSpendLedger, prompt_chars: int, fmt: str,
                  price_in: float, price_out: float) -> None:
    est = (prompt_chars / 3.5 + len(SYSTEM_PROMPT) / 3.5) * price_in / 1e6 + EST_OUTPUT_TOKENS[fmt] * price_out / 1e6
    spent = ledger.spent()
    if spent + est > settings.claude_monthly_budget_usd:
        raise ClaudeBudgetExceeded(f"Claude monthly budget: ${spent:.2f} spent + ~${est:.2f} for this request "
                                   f"would exceed ${settings.claude_monthly_budget_usd:.2f}")


def _request(client, settings: Settings, ledger: ClaudeSpendLedger, prompt: str, fmt: str,
             platform: str = "api", model: str | None = None, prices: tuple[float, float] | None = None) -> dict:
    price_in, price_out = prices or (settings.claude_price_in, settings.claude_price_out)
    _check_budget(settings, ledger, len(prompt), fmt, price_in, price_out)
    kwargs = dict(model=model or settings.script_model, max_tokens=MAX_TOKENS,
                  output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCRIPT_SCHEMA}},
                  system=SYSTEM_PROMPT, messages=[{"role": "user", "content": prompt}])
    # Streaming avoids HTTP timeouts on long outputs. On the Claude API, server-side fallback re-runs a declined
    # request on another Claude model; Vertex has no server-side fallbacks, so there a refusal holds production.
    if platform == "api":
        stream = client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    else:
        stream = client.messages.stream(**kwargs)
    with stream as st:
        message = st.get_final_message()

    usd, tin, tout = usage_cost(message.usage, price_in, price_out)
    ledger.add(usd, tin, tout)  # billed even when the output is unusable
    log.info("Claude (%s) usage: in=%s out=%s cost=$%.3f (month: $%.2f of $%.2f)", platform, tin, tout, usd,
             ledger.spent(), settings.claude_monthly_budget_usd)
    if message.stop_reason == "refusal":
        raise ScriptGenerationError(f"Model declined: {getattr(message, 'stop_details', None)}")
    if message.stop_reason == "max_tokens":
        raise ScriptGenerationError("Script truncated at max_tokens")
    text = next((b.text for b in message.content if getattr(b, "type", "") == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScriptGenerationError(f"Invalid JSON from model: {exc}") from exc


LAST_WRITER: dict = {"name": "", "note": ""}   # which backend wrote the most recent script (shown in the review)


def _parse_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):  # tolerate a fenced answer
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    try:
        return json.loads(t)
    except json.JSONDecodeError as exc:
        raise ScriptGenerationError(f"Invalid JSON from model: {exc}") from exc


def _request_openrouter(settings: Settings, ledger: ClaudeSpendLedger, prompt: str, fmt: str, session=None) -> dict:
    """Same prompts, schema and rules as the other Claude backends, through OpenRouter."""
    from .backends import openrouter_chat

    p_in, p_out = settings.openrouter_price_in, settings.openrouter_price_out
    _check_budget(settings, ledger, len(prompt), fmt, p_in, p_out)
    text, u = openrouter_chat(settings, SYSTEM_PROMPT, prompt, MAX_TOKENS, schema=SCRIPT_SCHEMA,
                              effort=settings.openrouter_effort or None, session=session)
    tin, tout = u["prompt_tokens"], u["completion_tokens"]
    usd = float(u["cost"]) if u.get("cost") is not None else tin * p_in / 1e6 + tout * p_out / 1e6
    ledger.add(usd, tin, tout)  # billed even when the output is unusable
    log.info("Claude (OpenRouter %s) usage: in=%s out=%s cost=$%.3f (month: $%.2f of $%.2f)", u.get("model"), tin,
             tout, usd, ledger.spent(), settings.claude_monthly_budget_usd)
    if u.get("finish_reason") in ("refusal", "content_filter"):
        raise ScriptGenerationError("Model declined the request")
    if u.get("finish_reason") in ("length", "max_tokens"):
        raise ScriptGenerationError("Script truncated at max_tokens")
    return _parse_json(text)


def _ask(settings: Settings, prompt: str, fmt: str, client=None, ledger: ClaudeSpendLedger | None = None) -> dict:
    """Claude only (OpenRouter, Vertex or Anthropic API, per WRITER). Any failure raises ClaudeUnavailable:
    production is held and retried hourly; no other writer is ever used."""
    import anthropic

    from .backends import WriterUnavailable, claude_client

    ledger = ledger or ClaudeSpendLedger(Path(settings.claude_spend_ledger_path))
    try:
        if settings.writer == "claude_openrouter":  # `client` (tests) is the HTTP session
            data = _request_openrouter(settings, ledger, prompt, fmt, session=client)
            LAST_WRITER.update(name=f"Claude {settings.openrouter_model} (OpenRouter)", note="")
            return data
        if client is not None:  # injected (tests): treat as the configured platform
            platform = "vertex" if settings.writer == "claude_vertex" else "api"
            model = settings.vertex_model if platform == "vertex" else settings.script_model
            prices = ((settings.vertex_price_in, settings.vertex_price_out) if platform == "vertex"
                      else (settings.claude_price_in, settings.claude_price_out))
        else:
            client, platform, model, p_in, p_out = claude_client(settings)
            prices = (p_in, p_out)
        data = _request(client, settings, ledger, prompt, fmt, platform, model, prices)
        LAST_WRITER.update(name=f"Claude {model} ({'Vertex AI' if platform == 'vertex' else 'Anthropic API'})",
                           note="")
        return data
    except (ScriptGenerationError, WriterUnavailable) as exc:  # includes the monthly cap
        why = str(exc)
    except anthropic.APIError as exc:  # auth, quota, outage after the SDK's own retries
        why = f"{type(exc).__name__}: {getattr(exc, 'status_code', '')}".strip()
    except Exception as exc:  # noqa: BLE001  e.g. google-auth token refresh failures
        why = f"{type(exc).__name__}"
    log.warning("Claude writer failed (%s); Claude only: holding production", why)
    raise ClaudeUnavailable(why)


def _to_script(data: dict, fmt: str, topic: str) -> Script:
    data = {**data, "scenes": [normalize_direction(s) for s in data.get("scenes", [])]}
    return Script.model_validate({**data, "format": fmt, "topic": topic})


def generate_with_claude(topic: str, fmt: str, settings: Settings, minutes: float | None = None,
                         angle: str = "", client=None, ledger: ClaudeSpendLedger | None = None,
                         max_revisions: int = 1) -> Script:
    minutes = minutes or DEFAULT_MINUTES[fmt]
    ledger = ledger or ClaudeSpendLedger(Path(settings.claude_spend_ledger_path))
    script = _to_script(_ask(settings, user_prompt(topic, fmt, minutes, angle), fmt, client, ledger), fmt, topic)
    lo, hi = TARGET_WORDS[fmt]
    for attempt in range(max_revisions):
        n = script.word_count
        if lo <= n <= hi:
            break
        target = int(minutes * WORDS_PER_MINUTE)
        log.info("Claude draft has %d words (target %d-%d); requesting revision %d", n, lo, hi, attempt + 1)
        try:
            revised = _to_script(_ask(settings, revise_prompt(script.model_dump_json(), fmt, n, target, lo, hi, angle),
                                      fmt, client, ledger), fmt, topic)
        except ScriptGenerationError:
            log.warning("no writer available for a length revision; keeping the draft")
            break
        # keep whichever draft is closer to the target range
        if abs(revised.word_count - target) < abs(n - target):
            script = revised
    return script


def rewrite_for_originality(script: Script, reasons: list[str], phrases: list[str], settings: Settings,
                            client=None, ledger: ClaudeSpendLedger | None = None) -> Script:
    """One paid rewrite of a draft that the anti-repetition check flagged."""
    data = _ask(settings, originality_prompt(script.model_dump_json(), reasons, phrases, script.format),
                script.format, client, ledger)
    out = _to_script(data, script.format, script.topic)
    return out.model_copy(update={"style": script.style})


def rewrite_for_compliance(script: Script, errors: list[str], facts: list[str], settings: Settings, client=None,
                           ledger: ClaudeSpendLedger | None = None) -> Script:
    """One paid fix-up after a compliance rejection, with the rejection reasons and the fact sheet."""
    from .prompts import compliance_prompt

    data = _ask(settings, compliance_prompt(script.model_dump_json(), errors, facts), script.format, client, ledger)
    return _to_script(data, script.format, script.topic).model_copy(update={"style": script.style})


def rewrite_for_sponsor(script: Script, issues: list[str], needs_what_to_do: bool, settings: Settings,
                        client=None, ledger: ClaudeSpendLedger | None = None,
                        evergreen_issues: list[str] | None = None,
                        retention_issues: list[str] | None = None) -> Script:
    """One paid rewrite that removes profanity/panic/political-side wording and adds the "What to do" section."""
    from .prompts import sponsor_prompt

    data = _ask(settings, sponsor_prompt(script.model_dump_json(), issues, needs_what_to_do, evergreen_issues,
                                         retention_issues),
                script.format, client, ledger)
    return _to_script(data, script.format, script.topic).model_copy(update={"style": script.style})


def rewrite_for_sources(script: Script, unsourced: list[str], settings: Settings, client=None,
                        ledger: ClaudeSpendLedger | None = None) -> Script:
    """One paid rewrite that removes or replaces claims without a source on the fact sheet."""
    data = _ask(settings, sources_prompt(script.model_dump_json(), unsourced), script.format, client, ledger)
    return _to_script(data, script.format, script.topic).model_copy(update={"style": script.style})
