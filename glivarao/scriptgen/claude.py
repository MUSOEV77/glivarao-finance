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
    # request on another model; Vertex has no server-side fallbacks, so there a refusal goes to the Gemini writer.
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


def _ask(settings: Settings, prompt: str, fmt: str, client=None, ledger: ClaudeSpendLedger | None = None) -> dict:
    """Claude first (Vertex or Anthropic API, per WRITER); Gemini Pro automatically if Claude fails."""
    import anthropic

    from .backends import WriterUnavailable, claude_client, gemini_write

    ledger = ledger or ClaudeSpendLedger(Path(settings.claude_spend_ledger_path))
    why = ""
    try:
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
    except ClaudeBudgetExceeded as exc:
        why = str(exc)
    except (ScriptGenerationError, WriterUnavailable) as exc:
        why = str(exc)
    except anthropic.APIError as exc:  # auth, quota, outage after the SDK's own retries
        why = f"{type(exc).__name__}: {getattr(exc, 'status_code', '')}".strip()
    except Exception as exc:  # noqa: BLE001  e.g. google-auth token refresh failures
        why = f"{type(exc).__name__}"
    log.warning("Claude writer failed (%s); using the Gemini Pro fallback", why)
    try:
        data = gemini_write(settings, SYSTEM_PROMPT, prompt, SCRIPT_SCHEMA, fmt)
    except WriterUnavailable as exc:
        raise ScriptGenerationError(f"Claude failed ({why}) and the Gemini fallback failed ({exc})") from None
    LAST_WRITER.update(name=f"Gemini {settings.gemini_writer_model} (fallback)", note=why)
    _fallback_alert(settings, why)
    return data


def _fallback_alert(settings: Settings, why: str) -> None:
    """One Telegram alert per day when the fallback writer had to step in."""
    try:
        from ..publish.telegram import notify
        from ..storage import JobStore

        store = JobStore(settings.db_path)
        key = f"writer_fallback_alert:{date.today().isoformat()}"
        if store.kv_get(key):
            return
        store.kv_set(key, "1")
        notify(settings, f"✍️ GLIVARAO: the Claude writer failed ({why[:200]}); Gemini Pro wrote today's script "
                         "instead. Check: python -m glivarao doctor --live")
    except Exception:  # noqa: BLE001  an alert must never break production
        log.exception("could not send the writer fallback alert")


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


def rewrite_for_sources(script: Script, unsourced: list[str], settings: Settings, client=None,
                        ledger: ClaudeSpendLedger | None = None) -> Script:
    """One paid rewrite that removes or replaces claims without a source on the fact sheet."""
    data = _ask(settings, sources_prompt(script.model_dump_json(), unsourced), script.format, client, ledger)
    return _to_script(data, script.format, script.topic).model_copy(update={"style": script.style})
